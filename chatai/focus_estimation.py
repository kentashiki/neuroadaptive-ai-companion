import time
from collections import deque

import numpy as np
from scipy.signal import welch
from scipy.signal import butter, filtfilt, iirnotch


# ===== Parameters =====
WINDOW_SECONDS = 2.0
UPDATE_INTERVAL = 1.0
MOVING_AVG_SECONDS = 5.0
STABLE_SECONDS = 3.0

CALIBRATION_SECONDS = 30.0

ALPHA_BAND = (8, 13)
BETA_BAND = (13, 30)

# z-score based hysteresis
FOCUS_ON_Z = 0.3
FOCUS_OFF_Z = -0.3

MIN_STD = 1e-6


def create_filters(fs):
    # Bandpass: 1–40 Hz
    b_band, a_band = butter(
        N=4,
        Wn=[1/(fs/2), 40/(fs/2)],
        btype='band'
    )

    # Notch: 50 Hz
    b_notch, a_notch = iirnotch(
        w0=50,
        Q=30,
        fs=fs
    )

    return (b_band, a_band), (b_notch, a_notch)

def preprocess_signal(x, band_filter, notch_filter):
    b_band, a_band = band_filter
    b_notch, a_notch = notch_filter

    # DC除去
    x = x - np.mean(x)

    # Notch
    x = filtfilt(b_notch, a_notch, x)

    # Bandpass
    x = filtfilt(b_band, a_band, x)

    return x

def bandpower(data, fs, band):
    low, high = band

    freqs, psd = welch(
        data,
        fs=fs,
        nperseg=min(len(data), int(fs * 2))
    )

    idx = np.logical_and(freqs >= low, freqs <= high)

    if not np.any(idx):
        return 0.0

    return np.trapezoid(psd[idx], freqs[idx])


def compute_focus_score(window_data, fs, band_filter, notch_filter):
    alpha_powers = []
    beta_powers = []

    for ch in range(window_data.shape[1]):
        x = window_data[:, ch]

        # preprocess
        x = preprocess_signal(x, band_filter, notch_filter)

        alpha = bandpower(x, fs, ALPHA_BAND)
        beta = bandpower(x, fs, BETA_BAND)

        alpha_powers.append(alpha)
        beta_powers.append(beta)

    alpha_mean = np.mean(alpha_powers)
    beta_mean = np.mean(beta_powers)

    focus_score = beta_mean / (alpha_mean + 1e-8)

    return focus_score, alpha_mean, beta_mean


def estimate_state_with_hysteresis(current_state, z_score):
    if current_state == "Focused":
        if z_score <= FOCUS_OFF_Z:
            return "Distracted"
        return "Focused"

    if current_state == "Distracted":
        if z_score >= FOCUS_ON_Z:
            return "Focused"
        return "Distracted"

    # Initial decision
    if z_score >= 0:
        return "Focused"
    return "Distracted"


def main():
    from pylsl import StreamInlet, resolve_byprop

    print("Searching for EEG LSL stream...")

    streams = resolve_byprop("type", "EEG", timeout=10)

    if not streams:
        print("No EEG stream found.")
        return

    inlet = StreamInlet(streams[0])
    info = inlet.info()

    fs = int(info.nominal_srate())
    ch_count = info.channel_count()

    band_filter, notch_filter = create_filters(fs)

    print("Connected to EEG stream.")
    print(f"Name: {info.name()}")
    print(f"Channels: {ch_count}")
    print(f"Sampling rate: {fs} Hz")
    print()

    sample_buffer = deque(maxlen=int(WINDOW_SECONDS * fs))
    score_buffer = deque(maxlen=int(MOVING_AVG_SECONDS / UPDATE_INTERVAL))

    calibration_scores = []
    calibrated = False
    calibration_start_time = None
    baseline_mean = None
    baseline_std = None

    current_state = "Unknown"
    candidate_state = None
    candidate_start_time = None

    last_update_time = time.time()

    print("Starting calibration.")
    print(f"Please stay in a neutral / normal state for {CALIBRATION_SECONDS:.0f} seconds.")
    print()

    try:
        while True:
            samples, timestamps = inlet.pull_chunk(
                timeout=0.0,
                max_samples=64
            )

            if samples:
                for sample in samples:
                    sample_buffer.append(sample[:ch_count])

            now = time.time()

            if now - last_update_time >= UPDATE_INTERVAL:
                last_update_time = now

                if len(sample_buffer) < int(WINDOW_SECONDS * fs):
                    print("Collecting initial EEG buffer...")
                    continue

                window_data = np.array(sample_buffer)

                focus_score, alpha_power, beta_power = compute_focus_score(
                  window_data,
                  fs,
                  band_filter,
                  notch_filter
                )

                score_buffer.append(focus_score)
                smoothed_score = float(np.mean(score_buffer))

                # ===== Calibration phase =====
                if not calibrated:
                    if calibration_start_time is None:
                        calibration_start_time = now

                    elapsed = now - calibration_start_time
                    calibration_scores.append(smoothed_score)

                    print(
                        f"[Calibration] "
                        f"{elapsed:.1f}/{CALIBRATION_SECONDS:.0f}s | "
                        f"score={focus_score:.3f} | "
                        f"smoothed={smoothed_score:.3f} | "
                        f"alpha={alpha_power:.2f} | "
                        f"beta={beta_power:.2f}"
                    )

                    if elapsed >= CALIBRATION_SECONDS:
                        baseline_mean = float(np.mean(calibration_scores))
                        baseline_std = float(np.std(calibration_scores))

                        if baseline_std < MIN_STD:
                            baseline_std = MIN_STD

                        calibrated = True

                        print()
                        print("===== CALIBRATION COMPLETE =====")
                        print(f"baseline_mean = {baseline_mean:.3f}")
                        print(f"baseline_std  = {baseline_std:.3f}")
                        print(f"Focused if z >= {FOCUS_ON_Z}")
                        print(f"Distracted if z <= {FOCUS_OFF_Z}")
                        print("================================")
                        print()

                    continue

                # ===== Estimation phase =====
                z_score = (smoothed_score - baseline_mean) / baseline_std

                estimated_state = estimate_state_with_hysteresis(
                    current_state,
                    z_score
                )

                if estimated_state != candidate_state:
                    candidate_state = estimated_state
                    candidate_start_time = now

                stable_duration = now - candidate_start_time

                if (
                    estimated_state != current_state
                    and stable_duration >= STABLE_SECONDS
                ):
                    old_state = current_state
                    current_state = estimated_state

                    print()
                    print("===== STATE CHANGED =====")
                    print(f"{old_state} -> {current_state}")
                    print(f"smoothed_focus_score = {smoothed_score:.3f}")
                    print(f"z_score = {z_score:.3f}")
                    print("=========================")
                    print()

                print(
                    f"score={focus_score:.3f} | "
                    f"smoothed={smoothed_score:.3f} | "
                    f"z={z_score:.3f} | "
                    f"alpha={alpha_power:.2f} | "
                    f"beta={beta_power:.2f} | "
                    f"candidate={candidate_state} "
                    f"({stable_duration:.1f}s) | "
                    f"status={current_state}"
                )

            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
