from __future__ import annotations

import time
from collections import deque
from threading import Event, Lock, Thread
from typing import Any

from models.state import UserState


STATE_ATTENTION = {
    "focused": 0.84,
    "distracted": 0.32,
}


class MuseFocusReceiver:
    def __init__(self, initial_state: str = "distracted") -> None:
        self._lock = Lock()
        self._stop_event = Event()
        self._state = self._make_state(initial_state)
        self._status: dict[str, Any] = {
            "status": "searching",
            "phase": "starting",
            "message": "Searching for an EEG LSL stream.",
        }
        self._thread = Thread(target=self._run, name="muse-focus-receiver", daemon=True)
        self._thread.start()

    def _make_state(self, label: str, attention: float | None = None) -> UserState:
        normalized = label.lower()
        if normalized not in STATE_ATTENTION:
            normalized = "distracted"
        return UserState.create(
            attention=STATE_ATTENTION[normalized] if attention is None else attention,
            label=normalized,
        )

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=2.0)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "state": self._state,
                "muse": dict(self._status),
            }

    def _set_state(self, label: str, attention: float | None = None) -> None:
        with self._lock:
            self._state = self._make_state(label, attention)

    def _set_status(self, status: str, phase: str, message: str, **extra: Any) -> None:
        with self._lock:
            self._status = {
                "status": status,
                "phase": phase,
                "message": message,
                **extra,
            }

    def _run(self) -> None:
        try:
            import numpy as np
            from pylsl import StreamInlet, resolve_byprop
            from scipy.signal import butter, filtfilt, iirnotch, welch
        except ImportError as exc:
            self._set_status("unavailable", "unavailable", f"Muse EEG dependencies are not available: {exc}")
            return

        window_seconds = 2.0
        update_interval = 1.0
        moving_avg_seconds = 5.0
        stable_seconds = 3.0
        calibration_seconds = 30.0
        focus_on_z = 0.3
        focus_off_z = -0.3

        def create_filters(fs: int):
            band_filter = butter(N=4, Wn=[1 / (fs / 2), 40 / (fs / 2)], btype="band")
            notch_filter = iirnotch(w0=50, Q=30, fs=fs)
            return band_filter, notch_filter

        def bandpower(data: Any, fs: int, low: float, high: float) -> float:
            freqs, psd = welch(data, fs=fs, nperseg=min(len(data), int(fs * 2)))
            idx = np.logical_and(freqs >= low, freqs <= high)
            if not np.any(idx):
                return 0.0
            trapz = getattr(np, "trapezoid", np.trapz)
            return float(trapz(psd[idx], freqs[idx]))

        def compute_focus_score(window_data: Any, fs: int, band_filter: Any, notch_filter: Any):
            alpha_powers = []
            beta_powers = []
            b_band, a_band = band_filter
            b_notch, a_notch = notch_filter

            for ch in range(window_data.shape[1]):
                x = window_data[:, ch]
                x = x - np.mean(x)
                x = filtfilt(b_notch, a_notch, x)
                x = filtfilt(b_band, a_band, x)
                alpha_powers.append(bandpower(x, fs, 8, 13))
                beta_powers.append(bandpower(x, fs, 13, 30))

            alpha_mean = float(np.mean(alpha_powers))
            beta_mean = float(np.mean(beta_powers))
            return beta_mean / (alpha_mean + 1e-8), alpha_mean, beta_mean

        def estimate_state(current_state: str, z_score: float) -> str:
            if current_state == "focused":
                return "distracted" if z_score <= focus_off_z else "focused"
            if current_state == "distracted":
                return "focused" if z_score >= focus_on_z else "distracted"
            return "focused" if z_score >= 0 else "distracted"

        while not self._stop_event.is_set():
            self._set_status("searching", "searching", "Searching for an EEG LSL stream.")
            streams = resolve_byprop("type", "EEG", timeout=5)
            if not streams:
                self._set_status("searching", "no_stream", "No EEG LSL stream found. Continuing search.")
                time.sleep(2.0)
                continue

            try:
                inlet = StreamInlet(streams[0])
                info = inlet.info()
                fs = int(info.nominal_srate())
                ch_count = info.channel_count()
                band_filter, notch_filter = create_filters(fs)
            except Exception as exc:
                self._set_status("error", "connect_error", f"Failed to connect to EEG stream: {exc}")
                time.sleep(2.0)
                continue

            self._set_status(
                "connected",
                "calibrating",
                "Connected to Muse EEG stream. Calibrating.",
                calibration_elapsed=0.0,
                calibration_total=calibration_seconds,
                stream_name=info.name(),
                sampling_rate=fs,
                channels=ch_count,
            )

            sample_buffer: deque[Any] = deque(maxlen=int(window_seconds * fs))
            score_buffer: deque[float] = deque(maxlen=int(moving_avg_seconds / update_interval))
            calibration_scores: list[float] = []
            calibration_start_time: float | None = None
            baseline_mean: float | None = None
            baseline_std: float | None = None
            calibrated = False
            current_state = self.snapshot()["state"].label
            candidate_state: str | None = None
            candidate_start_time: float | None = None
            last_update_time = time.time()

            try:
                while not self._stop_event.is_set():
                    samples, _timestamps = inlet.pull_chunk(timeout=0.0, max_samples=64)
                    if samples:
                        for sample in samples:
                            sample_buffer.append(sample[:ch_count])

                    now = time.time()
                    if now - last_update_time < update_interval:
                        time.sleep(0.01)
                        continue

                    last_update_time = now
                    if len(sample_buffer) < int(window_seconds * fs):
                        self._set_status("connected", "buffering", "Collecting initial EEG buffer.")
                        continue

                    focus_score, alpha_power, beta_power = compute_focus_score(
                        np.array(sample_buffer),
                        fs,
                        band_filter,
                        notch_filter,
                    )
                    score_buffer.append(float(focus_score))
                    smoothed_score = float(np.mean(score_buffer))

                    if not calibrated:
                        if calibration_start_time is None:
                            calibration_start_time = now
                        elapsed = now - calibration_start_time
                        calibration_scores.append(smoothed_score)
                        self._set_status(
                            "connected",
                            "calibrating",
                            "Connected to Muse EEG stream. Calibrating.",
                            calibration_elapsed=min(elapsed, calibration_seconds),
                            calibration_total=calibration_seconds,
                            alpha_power=alpha_power,
                            beta_power=beta_power,
                        )
                        if elapsed >= calibration_seconds:
                            baseline_mean = float(np.mean(calibration_scores))
                            baseline_std = max(float(np.std(calibration_scores)), 1e-6)
                            calibrated = True
                        continue

                    if baseline_mean is None or baseline_std is None:
                        continue

                    z_score = (smoothed_score - baseline_mean) / baseline_std
                    estimated_state = estimate_state(current_state, z_score)
                    if estimated_state != candidate_state:
                        candidate_state = estimated_state
                        candidate_start_time = now

                    stable_duration = now - candidate_start_time if candidate_start_time else 0.0
                    if estimated_state != current_state and stable_duration >= stable_seconds:
                        current_state = estimated_state

                    concentration = max(0.0, min(1.0, 0.5 + (z_score / 4.0)))
                    self._set_state(current_state, concentration)
                    self._set_status(
                        "connected",
                        "estimating",
                        "Estimating concentration from Muse EEG.",
                        z_score=float(z_score),
                        focus_score=float(focus_score),
                        alpha_power=alpha_power,
                        beta_power=beta_power,
                    )
            except Exception as exc:
                self._set_status("error", "stream_error", f"EEG stream error: {exc}")
                time.sleep(2.0)
