"""Unit tests for return calculation (analysis/indicators.py: calculate_returns).

return_t = (close_t - close_(t-1)) / close_(t-1)
"""
import pandas as pd
import pytest

from analysis.indicators import calculate_returns


def test_first_observation_has_no_return():
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=3, freq="D"),
        "close": [100.0, 110.0, 121.0],
        "volume": [1, 1, 1],
    })
    result = calculate_returns(df)
    assert pd.isna(result.iloc[0]["return"])


def test_return_formula_matches_percentage_change():
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=3, freq="D"),
        "close": [100.0, 110.0, 99.0],
        "volume": [1, 1, 1],
    })
    result = calculate_returns(df)
    assert result.iloc[1]["return"] == pytest.approx(0.10)
    assert result.iloc[2]["return"] == pytest.approx(-0.10)


def test_returns_are_sorted_by_timestamp_even_if_input_is_unordered():
    df = pd.DataFrame({
        "timestamp": [
            pd.Timestamp("2026-01-03"),
            pd.Timestamp("2026-01-01"),
            pd.Timestamp("2026-01-02"),
        ],
        "close": [130.0, 100.0, 110.0],
        "volume": [1, 1, 1],
    })
    result = calculate_returns(df)
    assert list(result["timestamp"]) == sorted(df["timestamp"])
    # After sorting by date: 100 -> 110 -> 130
    assert result.iloc[1]["return"] == pytest.approx(0.10)
