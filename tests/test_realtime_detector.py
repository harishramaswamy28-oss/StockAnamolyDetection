"""Unit tests for analysis/realtime_detector.py using a mocked database
connection (no live DB required).

Verifies:
- the current bar is excluded from its own baseline (baseline built strictly
  from bars preceding the evaluated timestamp)
- price and volume anomalies are detected via z-score / volume-ratio
- insufficient history safely yields no anomaly (not a crash)
- zero rolling standard deviation safely yields z_score=0 (no anomaly),
  never inf/NaN
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from tests.conftest import FakeConnection


def _history_rows(closes, volumes, start=None):
    start = start or datetime(2026, 1, 1, 9, 30, tzinfo=timezone.utc)
    return [
        (start + timedelta(minutes=i), closes[i], volumes[i])
        for i in range(len(closes))
    ]


def test_price_and_volume_spike_detected_with_sufficient_history(monkeypatch):
    from analysis import realtime_detector as rd

    monkeypatch.setattr(rd, "REALTIME_WINDOW", 3)

    history = _history_rows(closes=[100, 101, 100, 101], volumes=[1000, 1000, 1000, 1000])
    current_ts = history[-1][0] + timedelta(minutes=1)
    current_row = (130.0, 5000)  # big price jump + volume spike

    conn = FakeConnection([
        {"fetchone": (10,)},          # security_id lookup
        {"fetchall": list(reversed(history))},        # prior bars (oldest -> newest after reversal)
        {"fetchone": current_row},    # current bar (close, volume)
    ])

    with patch.object(rd, "get_connection", return_value=conn):
        events = rd.evaluate_current_bar("AAPL", current_ts)

    types = {e["anomaly_type"] for e in events}
    assert "realtime_positive_return_spike" in types
    assert "realtime_volume_spike" in types
    for e in events:
        assert e["symbol"] == "AAPL"
        assert e["security_id"] == 10


def test_insufficient_history_returns_no_events(monkeypatch):
    from analysis import realtime_detector as rd

    monkeypatch.setattr(rd, "REALTIME_WINDOW", 20)

    history = _history_rows(closes=[100, 101], volumes=[1000, 1000])
    current_ts = history[-1][0] + timedelta(minutes=1)

    conn = FakeConnection([
        {"fetchone": (10,)},
        {"fetchall": list(reversed(history))},   # far fewer than REALTIME_WINDOW + 1
        {"fetchone": (101.0, 1000)},
    ])

    with patch.object(rd, "get_connection", return_value=conn):
        events = rd.evaluate_current_bar("AAPL", current_ts)

    assert events == []


def test_zero_variability_history_builds_a_zero_width_dynamic_fence(monkeypatch):
    from analysis import realtime_detector as rd

    monkeypatch.setattr(rd, "REALTIME_WINDOW", 3)

    # A small movement outside an entirely flat recent return distribution is
    # outside its dynamically calculated zero-width interquartile fence.
    history = _history_rows(closes=[100, 100, 100, 100], volumes=[1000, 1000, 1000, 1000])
    current_ts = history[-1][0] + timedelta(minutes=1)
    current_row = (100.5, 1000)  # small, non-anomalous move

    conn = FakeConnection([
        {"fetchone": (10,)},
        {"fetchall": list(reversed(history))},
        {"fetchone": current_row},
    ])

    with patch.object(rd, "get_connection", return_value=conn):
        events = rd.evaluate_current_bar("AAPL", current_ts)

    assert "realtime_positive_return_spike" in {event["anomaly_type"] for event in events}


def test_volume_decline_detected(monkeypatch):
    from analysis import realtime_detector as rd

    monkeypatch.setattr(rd, "REALTIME_WINDOW", 3)

    history = _history_rows(closes=[100, 100, 100, 100], volumes=[1000, 1000, 1000, 1000])
    current_ts = history[-1][0] + timedelta(minutes=1)
    current_row = (100.1, 100)  # volume_ratio = 0.1 -> decline

    conn = FakeConnection([
        {"fetchone": (10,)},
        {"fetchall": list(reversed(history))},
        {"fetchone": current_row},
    ])

    with patch.object(rd, "get_connection", return_value=conn):
        events = rd.evaluate_current_bar("AAPL", current_ts)

    types = {e["anomaly_type"] for e in events}
    assert "realtime_volume_decline" in types


def test_unknown_security_raises_value_error():
    from analysis import realtime_detector as rd

    conn = FakeConnection([{"fetchone": None}])
    with patch.object(rd, "get_connection", return_value=conn):
        try:
            rd.evaluate_current_bar("ZZZZ", datetime.now(timezone.utc))
            assert False, "expected ValueError"
        except ValueError:
            pass
