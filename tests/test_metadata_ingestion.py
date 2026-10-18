"""Unit tests for ingestion/metadata_ingestion.py using a mocked Alpaca
trading client and a mocked database connection (no network, no real DB).

A small integration test at the bottom exercises the real insert_metadata()
against a live database, and is skipped unless credentials/DB are configured.
"""
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tests.conftest import FakeConnection


def _fake_asset(symbol, name, exchange_value, asset_class_value="us_equity", status_value="active"):
    return SimpleNamespace(
        symbol=symbol,
        name=name,
        exchange=SimpleNamespace(value=exchange_value),
        asset_class=SimpleNamespace(value=asset_class_value),
        status=SimpleNamespace(value=status_value),
    )


def test_insert_metadata_inserts_sector_company_security_and_exchange_security():
    from ingestion import metadata_ingestion

    fake_assets = [
        _fake_asset("AAPL", "Apple Inc.", "NASDAQ"),
        _fake_asset("MSFT", "Microsoft Corporation", "NASDAQ"),
        _fake_asset("TSLA", "Tesla, Inc.", "NASDAQ"),
        _fake_asset("NVDA", "NVIDIA Corporation", "NASDAQ"),
    ]

    fake_alpaca = SimpleNamespace(get_all_assets=lambda: fake_assets)

    # One fetchone() result per statement, in the order metadata_ingestion.py
    # executes them for a SINGLE symbol: sector, company(select), company(insert
    # only if not found), exchange, security. We give every step a usable
    # fetchone result; steps not needed for a given symbol are simply unused.
    steps = [{"fetchone": (1,)}] * 200
    fake_conn = FakeConnection(steps)

    with patch("ingestion.metadata_ingestion.get_alpaca_client", return_value=fake_alpaca), \
         patch("ingestion.metadata_ingestion.get_connection", return_value=fake_conn):
        metadata_ingestion.insert_metadata()

    assert fake_conn.committed is True
    assert fake_conn.rolled_back is False
    assert fake_conn.closed is True
    # At least one INSERT statement per conceptual entity should have been issued.
    executed_sql = " ".join(sql for sql, _ in fake_conn.cursor_obj.queries)
    assert "INSERT INTO sector" in executed_sql
    assert "INSERT INTO security" in executed_sql
    assert "INSERT INTO exchange_security" in executed_sql


def test_insert_metadata_skips_symbol_not_found_in_alpaca():
    from ingestion import metadata_ingestion

    # get_all_assets() returns no matching symbols at all.
    fake_alpaca = SimpleNamespace(get_all_assets=lambda: [])
    fake_conn = FakeConnection([{"fetchone": (1,)}] * 20)

    with patch("ingestion.metadata_ingestion.get_alpaca_client", return_value=fake_alpaca), \
         patch("ingestion.metadata_ingestion.get_connection", return_value=fake_conn):
        metadata_ingestion.insert_metadata()

    # Nothing should be inserted, but the transaction still commits cleanly.
    executed_sql = " ".join(sql for sql, _ in fake_conn.cursor_obj.queries)
    assert "INSERT INTO sector" not in executed_sql
    assert fake_conn.committed is True


def test_insert_metadata_rolls_back_on_error():
    from ingestion import metadata_ingestion

    fake_assets = [_fake_asset("AAPL", "Apple Inc.", "NASDAQ")]
    fake_alpaca = SimpleNamespace(get_all_assets=lambda: fake_assets)

    class ExplodingCursor:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, *a, **kw):
            raise RuntimeError("simulated DB failure")

    class ExplodingConnection:
        def cursor(self):
            return ExplodingCursor()

        def commit(self):
            raise AssertionError("commit should not be called after failure")

        def rollback(self):
            self.rolled_back = True

        def close(self):
            self.closed = True

    fake_conn = ExplodingConnection()

    with patch("ingestion.metadata_ingestion.get_alpaca_client", return_value=fake_alpaca), \
         patch("ingestion.metadata_ingestion.get_connection", return_value=fake_conn):
        with pytest.raises(RuntimeError):
            metadata_ingestion.insert_metadata()

    assert fake_conn.rolled_back is True
    assert fake_conn.closed is True


# ---------------------------------------------------------------------------
# Integration test (real Alpaca + real DB)
# ---------------------------------------------------------------------------

def _fully_configured():
    return all(
        os.getenv(v)
        for v in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD", "ALPACA_API_KEY", "ALPACA_SECRET_KEY")
    )


@pytest.mark.integration
@pytest.mark.skipif(not _fully_configured(), reason="DB and Alpaca credentials are not configured")
def test_insert_metadata_against_real_services():
    from ingestion.metadata_ingestion import insert_metadata

    insert_metadata()
