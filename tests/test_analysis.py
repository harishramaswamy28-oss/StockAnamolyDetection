"""Unit test for analysis/run_analysis.py (historical daily analysis) using a
mocked database connection: verifies that price/volume anomalies computed
from stored daily bars are persisted with a traceable ANALYSIS_RUN, and that
the whole operation rolls back cleanly on error.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from tests.conftest import FakeConnection


def _daily_rows(n=25, jump_at=None, jump_close=None):
    """Generate n daily (timestamp, close, volume) rows with small alternating
    +/-0.5% returns (realistic non-zero historical variance), optionally with
    one row's close replaced by ``jump_close`` to create an anomalous return."""
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    close = 100.0
    for i in range(n):
        ts = start + timedelta(days=i)
        if jump_at is not None and i == jump_at:
            c = jump_close
        else:
            close = close * (1.005 if i % 2 == 0 else 1 / 1.005)
            c = close
        rows.append((ts, c, 1000))
    return rows


def test_run_analysis_stores_price_anomaly_and_completes_run():
    from analysis import run_analysis as run_analysis_module

    rows = _daily_rows(n=25, jump_at=24, jump_close=500.0)

    # First get_connection() call: SELECT security_id, then SELECT price_bar rows.
    read_conn = FakeConnection([
        {"fetchone": (1,)},
        {"fetchall": rows},
    ])
    # Second get_connection() call: INSERT analysis_run (RETURNING analysis_id),
    # then N anomaly inserts (no RETURNING used), then UPDATE analysis_run.
    write_conn = FakeConnection([{"fetchone": (99,)}] + [{}] * 50)

    with patch.object(run_analysis_module, "get_connection", side_effect=[read_conn, write_conn]):
        analysis_id = run_analysis_module.run_analysis("AAPL", window=20, threshold=2.0)

    assert analysis_id == 99
    assert write_conn.committed is True
    executed_sql = " ".join(sql for sql, _ in write_conn.cursor_obj.queries)
    assert "INSERT INTO analysis_run" in executed_sql
    assert "INSERT INTO anomaly" in executed_sql
    assert "UPDATE analysis_run SET status = 'completed'" in executed_sql


def test_run_analysis_raises_for_unknown_symbol():
    from analysis import run_analysis as run_analysis_module

    read_conn = FakeConnection([{"fetchone": None}])

    with patch.object(run_analysis_module, "get_connection", return_value=read_conn):
        with pytest.raises(ValueError):
            run_analysis_module.run_analysis("ZZZZ")


def test_run_analysis_raises_when_no_price_history():
    from analysis import run_analysis as run_analysis_module

    read_conn = FakeConnection([
        {"fetchone": (1,)},
        {"fetchall": []},
    ])

    with patch.object(run_analysis_module, "get_connection", return_value=read_conn):
        with pytest.raises(ValueError):
            run_analysis_module.run_analysis("AAPL")
