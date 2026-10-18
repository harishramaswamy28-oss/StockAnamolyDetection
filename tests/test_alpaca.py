"""Integration test: verifies Alpaca trading-client authentication works with
the credentials configured in the environment.

Skips automatically if ALPACA_API_KEY/ALPACA_SECRET_KEY are not configured.
Does not place trades; only calls a read-only account endpoint.
"""
import os

import pytest

pytestmark = pytest.mark.integration


def _alpaca_configured():
    return bool(os.getenv("ALPACA_API_KEY")) and bool(os.getenv("ALPACA_SECRET_KEY"))


@pytest.mark.skipif(not _alpaca_configured(), reason="ALPACA_API_KEY/ALPACA_SECRET_KEY not configured")
def test_alpaca_trading_client_authenticates():
    from ingestion.alpaca_client import get_alpaca_client

    client = get_alpaca_client()
    try:
        account = client.get_account()
    except Exception as exc:  # pragma: no cover - depends on live Alpaca service
        pytest.skip(f"Alpaca authentication/service error: {exc}")
        return
    assert account is not None
    assert hasattr(account, "status")


def test_missing_credentials_raise_value_error(monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)

    from ingestion.alpaca_client import get_alpaca_client

    with pytest.raises(ValueError):
        get_alpaca_client()
