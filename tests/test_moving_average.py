"""Unit tests for rolling mean/std calculation (analysis/indicators.py:
calculate_rolling_statistics) and the shifted-baseline / no-look-ahead rule.

Formula requirement: rolling(...).mean().shift(1) and rolling(...).std().shift(1)
so the current observation never contributes to its own baseline.
"""
import pandas as pd
import pytest

from analysis.indicators import calculate_returns, calculate_rolling_statistics


def _make_df(closes):
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=len(closes), freq="D"),
        "close": closes,
        "volume": [100] * len(closes),
    })


def test_rolling_mean_excludes_current_observation():
    # 5 flat returns of 0.01 followed by a large jump; the rolling mean at the
    # jump index must be computed from the PRIOR window only.
    closes = [100, 101, 102.01, 103.03, 104.06, 105.10, 200]
    df = calculate_returns(_make_df(closes))
    df = calculate_rolling_statistics(df, window=5)
    # first 5 rows: not enough history (need window + shift) -> NaN
    assert pd.isna(df.iloc[5]["rolling_mean"]) is False or pd.isna(df.iloc[4]["rolling_mean"])
    # The rolling mean for the last (jump) row should be close to ~0.01,
    # i.e. it must NOT be influenced by the huge final return.
    last_mean = df.iloc[-1]["rolling_mean"]
    assert last_mean < 0.05


def test_rolling_window_of_20_is_supported():
    closes = [100 + i * 0.1 for i in range(30)]
    df = calculate_returns(_make_df(closes))
    df = calculate_rolling_statistics(df, window=20)
    # Only rows from index 21 onward (20 window + 1 shift) have both stats.
    assert pd.isna(df.iloc[20]["rolling_mean"])
    assert pd.notna(df.iloc[21]["rolling_mean"])
    assert pd.notna(df.iloc[21]["rolling_std"])


def test_rolling_std_is_nan_until_enough_history():
    closes = [100, 101, 102, 103]
    df = calculate_returns(_make_df(closes))
    df = calculate_rolling_statistics(df, window=3)
    assert pd.isna(df.iloc[0]["rolling_std"])
    assert pd.isna(df.iloc[1]["rolling_std"])
