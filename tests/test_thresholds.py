from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pandas as pd

from analysis.indicators import rolling_iqr_bounds
from tests.conftest import FakeConnection


def test_rolling_fence_uses_prior_values_and_recalculates_with_distribution():
    values = pd.Series([0.01, -0.01, 0.02, -0.02, 0.015, -0.015, 0.01, -0.01, 0.1])
    low, high = rolling_iqr_bounds(values, window=8, min_samples=8)
    assert pd.isna(low.iloc[7])
    assert pd.notna(low.iloc[8])
    assert values.iloc[8] > high.iloc[8]


def test_threshold_snapshot_reports_latest_data_derived_bounds():
    from analysis.thresholds import get_threshold_snapshot

    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    close = 100.0
    for index in range(22):
        close *= 1.003 if index % 2 else 0.998
        rows.append((start + timedelta(days=index), close, 1000 + index * 3))
    connection = FakeConnection([
        {"fetchone": (7,)},
        {"fetchall": list(reversed(rows))},
    ])

    with patch("analysis.thresholds.get_connection", return_value=connection):
        snapshot = get_threshold_snapshot("AAPL", "day")

    assert snapshot["ready"] is True
    assert snapshot["method"] == "rolling_iqr_fences"
    assert snapshot["samples"] == 20
    assert snapshot["latest_timestamp"] == rows[-1][0]
    assert snapshot["based_on_timestamp"] == rows[-2][0]
    assert snapshot["price_return_lower"] < snapshot["price_return_upper"]
    assert snapshot["volume_ratio_lower"] < snapshot["volume_ratio_upper"]
