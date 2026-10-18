"""Integration test: verifies Alpaca asset metadata can be retrieved for the
project's configured symbols (config.SYMBOLS).

Skips automatically if ALPACA_API_KEY/ALPACA_SECRET_KEY are not configured.
"""
import os

import pytest

pytestmark = pytest.mark.integration


def _alpaca_configured():
    return bool(os.getenv("ALPACA_API_KEY")) and bool(os.getenv("ALPACA_SECRET_KEY"))


@pytest.mark.skipif(not _alpaca_configured(), reason="ALPACA_API_KEY/ALPACA_SECRET_KEY not configured")
def test_all_configured_symbols_exist_as_alpaca_assets():
    from config import SYMBOLS
    from ingestion.alpaca_client import get_alpaca_client

    client = get_alpaca_client()
    try:
        assets = client.get_all_assets()
    except Exception as exc:  # pragma: no cover - depends on live Alpaca service
        pytest.skip(f"Alpaca service error: {exc}")
        return

    symbols_found = {asset.symbol for asset in assets}
    missing = [s for s in SYMBOLS if s not in symbols_found]
    assert not missing, f"Symbols not found in Alpaca assets: {missing}"
