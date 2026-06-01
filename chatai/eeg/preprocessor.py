def preprocess_eeg(raw, eeg_channel="EEGBITREV"):
    """
    生の Raw オブジェクトから EEG チャンネルを前処理して返す
    (ICAの実装は保留中)

    Parameters:
    -----------
    raw : mne.io.Raw
        元の生データ（Raw オブジェクト）
    eeg_channel : str
        前処理対象の EEG チャンネル名
    
    Returns:
    --------
    eeg_preprocessed : mne.io.Raw
        前処理済みの Raw オブジェクト（EEG チャンネルのみ）
    """

    # 1. チャネル抽出（既に単一チャンネルの場合はpickしない）
    if len(raw.ch_names) == 1:
        eeg_preprocessed = raw.copy()
    else:
        eeg_preprocessed = raw.copy().pick([eeg_channel])

    # 2. 50 Hz ノッチフィルタ
    eeg_preprocessed.notch_filter(
        freqs=50.0,
        method="iir",
        verbose=False
    )

    # 3. 1-40 Hz Butterworth band-pass filter
    eeg_preprocessed.filter(
        l_freq=1.0,
        h_freq=40.0,
        method="iir",
        iir_params={"order": 4, "ftype": "butter"},
        verbose=False
    )
    
    # 4. ICA（保留中）

    return eeg_preprocessed
