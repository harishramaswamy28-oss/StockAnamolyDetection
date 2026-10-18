"""Tests for ingestion/price_ingestion.py.

insert_price_data() is exercised with a mocked Alpaca bar response and a
mocked database connection (unit test, no network/DB required). An
integration test at the bottom exercises real ingestion end-to-end and is
skipped unless DB + Alpaca credentials are configured.
"""
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tests.conftest import FakeConnection


def _fake_bar(ts, o, h, l, c, v, trade_count=10, vwap=None):
    return SimpleNamespace(
        timestamp=ts, open=o, high=h, low=l, close=c, volume=v,
        trade_count=trade_count, vwap=vwap if vwap is not None else c,
    )


def test_insert_price_data_inserts_bars_for_known_symbols():
    from alpaca.data.timeframe import TimeFrame

    from ingestion import price_ingestion

    fake_bars_by_symbol = {
        "AAPL": [_fake_bar("2026-01-01T00:00:00Z", 100, 101, 99, 100.5, 1000)],
        "MSFT": [_fake_bar("2026-01-01T00:00:00Z", 200, 201, 199, 200.5, 2000)],
        "TSLA": [],
        "NVDA": [],
    }
    fake_response = SimpleNamespace(data=fake_bars_by_symbol)

    # For each symbol: one fetchone() for the security_id lookup (security_id=1),
    # then N inserts (no fetch needed since ON CONFLICT ... DO UPDATE has no RETURNING).
    steps = [{"fetchone": (1,)}] * 50
    fake_conn = FakeConnection(steps)

    with patch("ingestion.price_ingestion.get_price_data", return_value=fake_response), \
         patch("ingestion.price_ingestion.get_connection", return_value=fake_conn):
        total = price_ingestion.insert_price_data(TimeFrame.Day, days=5)

    assert total == 2
    assert fake_conn.committed is True
    insert_calls = [call for call in fake_conn.cursor_obj.queries if "INSERT INTO price_bar" in call[0]]
    assert all(call[1][2] == "day" for call in insert_calls)


def test_timeframe_unit_mapping_handles_alpaca_day_and_minute():
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    assert TimeFrame.Day.unit == TimeFrameUnit.Day
    assert TimeFrame.Minute.unit == TimeFrameUnit.Minute
    assert ("day" if TimeFrame.Day.unit == TimeFrameUnit.Day else "minute") == "day"
    assert ("day" if TimeFrame.Minute.unit == TimeFrameUnit.Day else "minute") == "minute"


def test_historical_request_uses_configured_market_feed(monkeypatch):
    from alpaca.data.enums import DataFeed
    from alpaca.data.timeframe import TimeFrame

    from ingestion import price_ingestion

    monkeypatch.setenv("ALPACA_API_KEY", "test-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")
    monkeypatch.setattr(price_ingestion, "DATA_FEED", "sip")
    response = object()

    with patch.object(price_ingestion, "StockHistoricalDataClient") as client_class:
        client_class.return_value.get_stock_bars.return_value = response
        result = price_ingestion.get_price_data(TimeFrame.Day, days=1)

    assert result is response
    request = client_class.return_value.get_stock_bars.call_args.args[0]
    assert request.feed == DataFeed.SIP


def test_insert_price_data_maps_minute_bars_to_minute_timeframe():
    from alpaca.data.timeframe import TimeFrame

    from ingestion import price_ingestion

    fake_response = SimpleNamespace(
        data={"AAPL": [_fake_bar("2026-01-01T09:30:00Z", 100, 101, 99, 100.5, 1000)]}
    )
    fake_conn = FakeConnection([{"fetchone": (1,)}] * 50)

    with patch("ingestion.price_ingestion.get_price_data", return_value=fake_response), \
         patch("ingestion.price_ingestion.get_connection", return_value=fake_conn):
        total = price_ingestion.insert_price_data(TimeFrame.Minute, days=5)

    assert total == 1
    insert_calls = [call for call in fake_conn.cursor_obj.queries if "INSERT INTO price_bar" in call[0]]
    assert insert_calls[0][1][2] == "minute"


def test_insert_price_data_skips_unknown_security():
    from alpaca.data.timeframe import TimeFrame

    from ingestion import price_ingestion

    fake_response = SimpleNamespace(data={})
    # security_id lookup returns None for every symbol -> all skipped.
    fake_conn = FakeConnection([{"fetchone": None}] * 10)

    with patch("ingestion.price_ingestion.get_price_data", return_value=fake_response), \
         patch("ingestion.price_ingestion.get_connection", return_value=fake_conn):
        total = price_ingestion.insert_price_data(TimeFrame.Day, days=5)

    assert total == 0


def test_main_defaults_days_by_timeframe(monkeypatch):
    """--days should default to 365 for daily bars and 5 for minute bars."""
    from ingestion import price_ingestion

    captured = {}

    def fake_insert(timeframe, days):
        captured["timeframe"] = timeframe
        captured["days"] = days
        return 0

    monkeypatch.setattr(price_ingestion, "insert_price_data", fake_insert)
    monkeypatch.setattr("sys.argv", ["price_ingestion.py", "--timeframe", "day"])
    price_ingestion.main()
    assert captured["days"] == 365

    monkeypatch.setattr("sys.argv", ["price_ingestion.py", "--timeframe", "minute"])
    price_ingestion.main()
    assert captured["days"] == 5


# ---------------------------------------------------------------------------
# Integration test (real Alpaca + real DB); mutates the configured database.
# ---------------------------------------------------------------------------

def _fully_configured():
    return all(
        os.getenv(v)
        for v in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD", "ALPACA_API_KEY", "ALPACA_SECRET_KEY")
    ) and os.getenv("RUN_LIVE_INGESTION_TESTS") == "1"


@pytest.mark.integration
@pytest.mark.skipif(
    not _fully_configured(),
    reason="Requires DB + Alpaca credentials AND RUN_LIVE_INGESTION_TESTS=1 (writes to the real DB)",
)
def test_insert_price_data_against_real_services():
    from alpaca.data.timeframe import TimeFrame

    from ingestion.price_ingestion import insert_price_data

    total = insert_price_data(TimeFrame.Day, days=5)
    assert total >= 0
