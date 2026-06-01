import numpy as np
from scipy.signal import welch

WELCH_WINDOW_SEC = 5.0
WELCH_OVERLAP_RATIO = 0.5


def _empty_eeg_features():
    return {
        "eeg_alpha_power": np.nan,
        "eeg_beta_power": np.nan,
        "eeg_theta_power": np.nan,
        "eeg_lowbeta_power": np.nan,
        "eeg_highbeta_power": np.nan,
        "eeg_alpha_beta_ratio": np.nan,
        "eeg_theta_beta_ratio": np.nan,
        "eeg_theta_alpha_ratio": np.nan,
        "eeg_theta_plus_alpha_over_beta": np.nan
    }


def extract_eeg_features(eeg_preprocessed, sfreq=1000.0, eeg_channel="EEGBITREV"):
    """
    EEGチャンネルの特徴量を抽出する

    Parameters:
    -----------
    eeg_preprocessed : mne.io.Raw
        前処理済みのEEG信号を含むRawオブジェクト
    sfreq : float
        サンプリング周波数
    eeg_channel : str
        特徴量抽出の対象となるEEGチャンネル名

    Returns:
    --------
    dict
        特徴量
    """

    # 指定チャンネルのデータを1次元配列で取得
    if eeg_channel not in eeg_preprocessed.ch_names:
        raise ValueError(f"Channel '{eeg_channel}' not found in data.")

    data = eeg_preprocessed.copy().pick([eeg_channel]).get_data()  # shape (1, n_samples)
    data = data.flatten()

    if data.size < 2:
        return _empty_eeg_features()

    if not np.all(np.isfinite(data)):
        print("EEG feature extraction skipped: signal contains non-finite values")
        return _empty_eeg_features()

    window_samples = max(2, int(round(sfreq * WELCH_WINDOW_SEC)))
    nperseg = min(window_samples, len(data))
    noverlap = min(int(round(nperseg * WELCH_OVERLAP_RATIO)), nperseg - 1)

    # ------- PSD計算 -------
    freqs, psd = welch(data, fs=sfreq, nperseg=nperseg, noverlap=noverlap)
    if not np.all(np.isfinite(psd)):
        print("EEG feature extraction skipped: PSD contains non-finite values")
        return _empty_eeg_features()

    def band_power(f, p, fmin, fmax):
        mask = (f >= fmin) & (f <= fmax)
        if not np.any(mask):
            return np.nan
        return np.mean(p[mask])

    # バンドパワー
    alpha_power = band_power(freqs, psd, 8, 12)
    beta_power = band_power(freqs, psd, 13, 30)
    theta_power = band_power(freqs, psd, 4, 7)
    lowbeta_power  = band_power(freqs, psd, 13, 20)
    highbeta_power = band_power(freqs, psd, 20, 30)

    # 比
    alpha_beta_ratio = alpha_power / beta_power if beta_power > 0 else np.nan
    theta_beta_ratio = theta_power / beta_power if beta_power > 0 else np.nan
    theta_alpha_ratio = theta_power / alpha_power if alpha_power > 0 else np.nan
    theta_plus_alpha_over_beta = (theta_power + alpha_power) / beta_power if beta_power > 0 else np.nan

    return {
        # --- バンドパワー ---
        "eeg_alpha_power": alpha_power,
        "eeg_beta_power": beta_power,
        "eeg_theta_power": theta_power,
        "eeg_lowbeta_power": lowbeta_power,
        "eeg_highbeta_power": highbeta_power,
        
        # --- 比 ---
        "eeg_alpha_beta_ratio": alpha_beta_ratio,
        "eeg_theta_beta_ratio": theta_beta_ratio,
        "eeg_theta_alpha_ratio": theta_alpha_ratio,
        "eeg_theta_plus_alpha_over_beta": theta_plus_alpha_over_beta
    }
