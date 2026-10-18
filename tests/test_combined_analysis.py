"""End-to-end unit test of the full indicator pipeline (no database):

    calculate_returns -> calculate_rolling_statistics -> calculate_z_score
        -> detect_anomalies -> calculate_volume_indicators
        -> classify_anomalies_with_volume

Verifies price anomalies and volume anomalies are classified independently
and that zero/undefined standard deviation never produces inf/NaN "anomaly"
records that would incorrectly flag as anomalous.
"""
import numpy as np
import pandas as pd

from analysis.indicators import (
    calculate_returns,
    calculate_rolling_statistics,
    calculate_z_score,
    detect_anomalies,
    calculate_volume_indicators,
    classify_anomalies_with_volume,
)


def _run_pipeline(closes, volumes, window=5, price_threshold=2.0):
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=len(closes), freq="D"),
        "close": closes,
        "volume": volumes,
    })
    df["close"] = df["close"].astype(float)
    df["volume"] = df["volume"].astype(float)
    df = calculate_returns(df)
    df = calculate_rolling_statistics(df, window)
    df = calculate_z_score(df)
    df = detect_anomalies(df, price_threshold)
    df = calculate_volume_indicators(df, window)
    df = classify_anomalies_with_volume(df, window=window)
    return df


def test_large_positive_return_is_flagged_as_positive_return_spike():
    closes = [100, 100.1, 99.9, 100.2, 99.8, 100.1, 100.0, 130.0]
    volumes = [1000] * 8
    df = _run_pipeline(closes, volumes, window=5)
    last = df.iloc[-1]
    assert bool(last["price_anomaly"]) is True
    assert last["z_score"] > 0


def test_large_negative_return_is_flagged_as_negative_return_spike():
    closes = [100, 100.1, 99.9, 100.2, 99.8, 100.1, 100.0, 70.0]
    volumes = [1000] * 8
    df = _run_pipeline(closes, volumes, window=5)
    last = df.iloc[-1]
    assert bool(last["price_anomaly"]) is True
    assert last["z_score"] < 0


def test_normal_movement_is_not_flagged():
    closes = [100, 100.1, 99.9, 100.2, 99.8, 100.1, 100.05]
    volumes = [1000] * 7
    df = _run_pipeline(closes, volumes, window=5)
    last = df.iloc[-1]
    assert bool(last["price_anomaly"]) is False


def test_zero_std_does_not_produce_inf_or_nan_anomaly_flag():
    # Constant returns -> rolling std of 0 -> z-score is defined as 0.0 by
    # calculate_z_score (never inf/NaN), so no anomaly is flagged.
    closes = [100 * (1.01 ** i) for i in range(8)]  # constant 1% daily return
    volumes = [1000] * 8
    df = _run_pipeline(closes, volumes, window=5)
    last = df.iloc[-1]
    assert not np.isinf(last["z_score"])
    assert not pd.isna(last["z_score"])
    assert last["z_score"] == pytest_approx_zero()
    assert bool(last["price_anomaly"]) is False


def pytest_approx_zero():
    import pytest
    return pytest.approx(0.0, abs=1e-6)


def test_price_and_volume_anomalies_are_independent_classifications():
    # Price move is small (not anomalous) but volume spikes heavily.
    closes = [100, 100.1, 99.9, 100.2, 99.8, 100.05]
    volumes = [1000, 1000, 1000, 1000, 1000, 5000]
    df = _run_pipeline(closes, volumes, window=5)
    last = df.iloc[-1]
    assert bool(last["price_anomaly"]) is False
    assert bool(last["volume_spike"]) is True
