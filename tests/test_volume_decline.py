"""Unit tests for dynamically calculated volume decline bounds."""
import pandas as pd

from analysis.indicators import calculate_volume_indicators, classify_anomalies_with_volume


def test_volume_decline_flagged_below_threshold():
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=4, freq="D"),
        "close": [100] * 4,
        "volume": [100, 100, 100, 40],  # ratio = 0.4
    })
    df = calculate_volume_indicators(df, window=3)
    df["anomaly_score"] = 0.0
    df = classify_anomalies_with_volume(df, volume_decline_threshold=0.5)
    assert bool(df.iloc[3]["volume_decline"]) is True
    assert bool(df.iloc[3]["volume_spike"]) is False


def test_volume_decline_fence_is_derived_from_history_not_a_fixed_half_ratio():
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=4, freq="D"),
        "close": [100] * 4,
        "volume": [100, 100, 100, 50],  # ratio = 0.5 exactly, threshold is strict '<'
    })
    df = calculate_volume_indicators(df, window=3)
    df["anomaly_score"] = 0.0
    df = classify_anomalies_with_volume(df, volume_decline_threshold=0.5)
    assert bool(df.iloc[3]["volume_decline"]) is True
