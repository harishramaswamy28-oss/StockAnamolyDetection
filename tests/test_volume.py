"""Unit tests for volume ratio / volume baseline calculation
(analysis/indicators.py: calculate_volume_indicators).

volume_ratio = current_volume / historical_average_volume, where the
historical average excludes the current observation (shift(1)).
"""
import pandas as pd

from analysis.indicators import calculate_volume_indicators


def test_volume_average_excludes_current_observation():
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=5, freq="D"),
        "close": [100] * 5,
        "volume": [100, 100, 100, 500, 100],
    })
    result = calculate_volume_indicators(df, window=3)
    # Row index 3 (volume=500): average of previous 3 volumes (100,100,100) = 100
    assert result.iloc[3]["volume_average"] == 100.0
    assert result.iloc[3]["volume_ratio"] == 5.0


def test_volume_ratio_is_nan_without_enough_history():
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=2, freq="D"),
        "close": [100, 100],
        "volume": [100, 200],
    })
    result = calculate_volume_indicators(df, window=5)
    assert pd.isna(result.iloc[0]["volume_average"])
    assert pd.isna(result.iloc[1]["volume_average"])
