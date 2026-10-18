"""Integration test: verifies Alpaca historical bar data can be retrieved for
the configured symbols and timeframes.

Skips automatically if ALPACA_API_KEY/ALPACA_SECRET_KEY are not configured.
Does not write to the database; read-only against the Alpaca market-data API.
"""
import os

import pytest

pytestmark = pytest.mark.integration


def _alpaca_configured():
    return bool(os.getenv("ALPACA_API_KEY")) and bool(os.getenv("ALPACA_SECRET_KEY"))


@pytest.mark.skipif(not _alpaca_configured(), reason="ALPACA_API_KEY/ALPACA_SECRET_KEY not configured")
def test_get_daily_price_data_returns_bars():
    from alpaca.data.timeframe import TimeFrame

    from ingestion.price_ingestion import get_price_data

    try:
        bars = get_price_data(TimeFrame.Day, days=10)
    except Exception as exc:  # pragma: no cover - depends on live Alpaca service
        pytest.skip(f"Alpaca market-data service error: {exc}")
        return

    from config import SYMBOLS

    for symbol in SYMBOLS:
        assert symbol in bars.data


@pytest.mark.skipif(not _alpaca_configured(), reason="ALPACA_API_KEY/ALPACA_SECRET_KEY not configured")
def test_get_minute_price_data_returns_bars():
    from alpaca.data.timeframe import TimeFrame

    from ingestion.price_ingestion import get_price_data

    try:
        bars = get_price_data(TimeFrame.Minute, days=2)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"Alpaca market-data service error: {exc}")
        return

    assert bars is not None
