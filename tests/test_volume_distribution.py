"""Unit tests for dynamic volume bounds and volume anomaly classification."""
import pandas as pd

from analysis.indicators import calculate_volume_indicators, classify_anomalies_with_volume


def _with_z_score_columns(df):
    # classify_anomalies_with_volume expects an anomaly_score column to exist
    # from the price side of the pipeline; supply a harmless constant so we
    # can isolate the volume classification behaviour.
    df = df.copy()
    df["anomaly_score"] = 0.0
    return df


def test_volume_ratio_distribution_flags_spike_above_threshold():
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=4, freq="D"),
        "close": [100] * 4,
        "volume": [100, 100, 100, 250],  # ratio = 2.5 at final row
    })
    df = calculate_volume_indicators(df, window=3)
    df = _with_z_score_columns(df)
    df = classify_anomalies_with_volume(df, price_threshold=2.0, volume_spike_threshold=2.0,
                                         volume_decline_threshold=0.5)
    assert bool(df.iloc[3]["volume_spike"]) is True
    assert bool(df.iloc[3]["volume_decline"]) is False


def test_volume_ratio_distribution_flags_data_outside_flat_baseline_fence():
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=4, freq="D"),
        "close": [100] * 4,
        "volume": [100, 100, 100, 110],  # flat history yields a zero-width adaptive fence
    })
    df = calculate_volume_indicators(df, window=3)
    df = _with_z_score_columns(df)
    df = classify_anomalies_with_volume(df)
    assert bool(df.iloc[3]["volume_spike"]) is True
    assert bool(df.iloc[3]["volume_decline"]) is False
