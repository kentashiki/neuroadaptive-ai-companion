from __future__ import annotations

import time
from collections import deque
from threading import Event, Lock, Thread
from typing import Any

import numpy as np

from chatai.focus_estimation import (
    CALIBRATION_SECONDS,
    FOCUS_OFF_Z,
    FOCUS_ON_Z,
    MIN_STD,
    MOVING_AVG_SECONDS,
    STABLE_SECONDS,
    UPDATE_INTERVAL,
    WINDOW_SECONDS,
    compute_focus_score,
    create_filters,
    estimate_state_with_hysteresis,
)
from chatai.models.state import UserState


STATE_ATTENTION = {
    "focused": 0.84,
    "distracted": 0.32,
}


class LSLFocusReceiver:
    """Background LSL EEG receiver that exposes the latest focused/distracted state."""

    def __init__(self, initial_state: str = "distracted") -> None:
        self._lock = Lock()
        self._stop_event = Event()
        self._state = self._make_state(initial_state)
        self._status: dict[str, float | str | None] = {
            "phase": "starting",
            "calibration_elapsed": None,
            "calibration_total": CALIBRATION_SECONDS,
        }
        self._thread = Thread(target=self._run, name="lsl-focus-receiver", daemon=True)
        self._thread.start()

    def _make_state(self, label: str, attention: float | None = None) -> UserState:
        normalized = label.lower()
        if normalized not in STATE_ATTENTION:
            valid = ", ".join(sorted(STATE_ATTENTION))
            raise ValueError(f"Unsupported state '{label}'. Valid states: {valid}.")
        return UserState.create(
            attention=STATE_ATTENTION[normalized] if attention is None else attention,
            label=normalized,
        )

    def _set_state(self, label: str, attention: float | None = None) -> UserState:
        with self._lock:
            self._state = self._make_state(label, attention)
            return self._state

    def get_state(self) -> UserState:
        with self._lock:
            return self._state

    def get_status(self) -> dict[str, float | str | None]:
        with self._lock:
            return dict(self._status)

    def _set_status(self, phase: str, calibration_elapsed: float | None = None) -> None:
        with self._lock:
            self._status = {
                "phase": phase,
                "calibration_elapsed": calibration_elapsed,
                "calibration_total": CALIBRATION_SECONDS,
            }

    def set_state(self, label: str) -> UserState:
        state = self._set_state(label)
        print(f"[Manual Override] state={state.label} | attention={state.attention:.2f}", flush=True)
        return state

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=2.0)

    def _run(self) -> None:
        try:
            from pylsl import StreamInlet, resolve_byprop
        except ImportError as exc:
            self._set_status("unavailable")
            print(f"pylsl is not available. LSL focus receiver stopped: {exc}", flush=True)
            return

        self._set_status("searching")
        print("Searching for EEG LSL stream...", flush=True)
        streams = resolve_byprop("type", "EEG", timeout=10)

        if not streams:
            self._set_status("no_stream")
            print("No EEG stream found. Keeping manual state controls available.", flush=True)
            return

        inlet = StreamInlet(streams[0])
        info = inlet.info()

        fs = int(info.nominal_srate())
        ch_count = info.channel_count()
        band_filter, notch_filter = create_filters(fs)

        print("Connected to EEG stream.", flush=True)
        print(f"Name: {info.name()}", flush=True)
        print(f"Channels: {ch_count}", flush=True)
        print(f"Sampling rate: {fs} Hz", flush=True)
        print(flush=True)

        sample_buffer: deque[Any] = deque(maxlen=int(WINDOW_SECONDS * fs))
        score_buffer: deque[float] = deque(maxlen=int(MOVING_AVG_SECONDS / UPDATE_INTERVAL))

        calibration_scores: list[float] = []
        calibrated = False
        calibration_start_time = None
        baseline_mean = None
        baseline_std = None

        current_state = self.get_state().label.capitalize()
        candidate_state = None
        candidate_start_time = None

        last_update_time = time.time()

        print("Starting calibration.", flush=True)
        print(
            f"Please stay in a neutral / normal state for {CALIBRATION_SECONDS:.0f} seconds.",
            flush=True,
        )
        print(flush=True)
        self._set_status("calibrating", 0.0)

        while not self._stop_event.is_set():
            samples, _timestamps = inlet.pull_chunk(timeout=0.0, max_samples=64)

            if samples:
                for sample in samples:
                    sample_buffer.append(sample[:ch_count])

            now = time.time()

            if now - last_update_time >= UPDATE_INTERVAL:
                last_update_time = now

                if len(sample_buffer) < int(WINDOW_SECONDS * fs):
                    print("Collecting initial EEG buffer...", flush=True)
                    time.sleep(0.01)
                    continue

                window_data = np.array(sample_buffer)
                focus_score, alpha_power, beta_power = compute_focus_score(
                    window_data,
                    fs,
                    band_filter,
                    notch_filter,
                )

                score_buffer.append(focus_score)
                smoothed_score = float(np.mean(score_buffer))

                if not calibrated:
                    if calibration_start_time is None:
                        calibration_start_time = now

                    elapsed = now - calibration_start_time
                    calibration_scores.append(smoothed_score)
                    self._set_status("calibrating", min(elapsed, CALIBRATION_SECONDS))

                    print(
                        f"[Calibration] "
                        f"{elapsed:.1f}/{CALIBRATION_SECONDS:.0f}s | "
                        f"score={focus_score:.3f} | "
                        f"smoothed={smoothed_score:.3f} | "
                        f"alpha={alpha_power:.2f} | "
                        f"beta={beta_power:.2f}",
                        flush=True,
                    )

                    if elapsed >= CALIBRATION_SECONDS:
                        baseline_mean = float(np.mean(calibration_scores))
                        baseline_std = float(np.std(calibration_scores))

                        if baseline_std < MIN_STD:
                            baseline_std = MIN_STD

                        calibrated = True
                        self._set_status("estimating", CALIBRATION_SECONDS)

                        print(flush=True)
                        print("===== CALIBRATION COMPLETE =====", flush=True)
                        print(f"baseline_mean = {baseline_mean:.3f}", flush=True)
                        print(f"baseline_std  = {baseline_std:.3f}", flush=True)
                        print(f"Focused if z >= {FOCUS_ON_Z}", flush=True)
                        print(f"Distracted if z <= {FOCUS_OFF_Z}", flush=True)
                        print("================================", flush=True)
                        print(flush=True)

                    time.sleep(0.01)
                    continue

                if baseline_mean is None or baseline_std is None:
                    time.sleep(0.01)
                    continue

                self._set_status("estimating", CALIBRATION_SECONDS)
                z_score = (smoothed_score - baseline_mean) / baseline_std
                estimated_state = estimate_state_with_hysteresis(current_state, z_score)

                if estimated_state != candidate_state:
                    candidate_state = estimated_state
                    candidate_start_time = now

                stable_duration = now - candidate_start_time if candidate_start_time else 0.0

                if estimated_state != current_state and stable_duration >= STABLE_SECONDS:
                    old_state = current_state
                    current_state = estimated_state
                    attention = max(0.0, min(1.0, 0.5 + (z_score / 4.0)))
                    self._set_state(current_state, attention)

                    print(flush=True)
                    print("===== STATE CHANGED =====", flush=True)
                    print(f"{old_state} -> {current_state}", flush=True)
                    print(f"smoothed_focus_score = {smoothed_score:.3f}", flush=True)
                    print(f"z_score = {z_score:.3f}", flush=True)
                    print("=========================", flush=True)
                    print(flush=True)
                else:
                    attention = max(0.0, min(1.0, 0.5 + (z_score / 4.0)))
                    self._set_state(current_state, attention)

                print(
                    f"score={focus_score:.3f} | "
                    f"smoothed={smoothed_score:.3f} | "
                    f"z={z_score:.3f} | "
                    f"alpha={alpha_power:.2f} | "
                    f"beta={beta_power:.2f} | "
                    f"candidate={candidate_state} "
                    f"({stable_duration:.1f}s) | "
                    f"status={current_state}",
                    flush=True,
                )

            time.sleep(0.01)

        self._set_status("stopped")
        print("LSL focus receiver stopped.", flush=True)
