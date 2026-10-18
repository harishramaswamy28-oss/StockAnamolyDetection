import pandas as pd

from analysis.indicators import (
    calculate_returns,
    calculate_rolling_statistics,
    calculate_z_score,
    calculate_volume_indicators,
)


def test_rolling_baseline_excludes_current_observation():
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=8, freq="D"),
        "close": [100, 101, 100, 102, 101, 103, 104, 103],
        "volume": [100] * 8,
    })
    df = calculate_returns(df)
    df = calculate_rolling_statistics(df, window=3)
    df = calculate_z_score(df)
    assert pd.isna(df.iloc[3]["rolling_mean"])
    assert pd.notna(df.iloc[4]["rolling_mean"])


def test_volume_ratio_uses_previous_observations():
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=6, freq="min"),
        "close": [100] * 6,
        "volume": [100, 100, 100, 200, 100, 100],
    })
    result = calculate_volume_indicators(df, window=3)
    assert result.iloc[3]["volume_average"] == 100.0
    assert result.iloc[3]["volume_ratio"] == 2.0
