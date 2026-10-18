"""Unit tests for analysis/pipeline.py using a mocked database connection and
mocked collaborators (evaluate_current_bar, notify_users_for_realtime_anomaly,
check_all_active_alerts). Verifies the orchestration logic itself: bar storage,
analysis-run reuse, anomaly persistence, anomaly notification dispatch, and
alert evaluation -- without touching a real database or the real detector.
"""
from datetime import datetime, timezone
from unittest.mock import patch

from tests.conftest import FakeConnection


def test_realtime_method_name_tracks_configured_baseline_window():
    from analysis import pipeline
    from config import REALTIME_WINDOW

    assert pipeline.REALTIME_METHOD == f"realtime_1min_rolling_iqr_fences_{REALTIME_WINDOW}_v2"


def test_get_or_create_open_analysis_run_reuses_existing_run():
    from analysis import pipeline

    conn = FakeConnection([{"fetchone": (55,)}])
    result = pipeline.get_or_create_open_analysis_run(conn.cursor(), security_id=10)
    assert result == 55
    executed_sql = " ".join(sql for sql, _ in conn.cursor_obj.queries)
    assert "INSERT INTO analysis_run" not in executed_sql


def test_get_or_create_open_analysis_run_creates_new_run_when_none_open():
    from analysis import pipeline

    conn = FakeConnection([{"fetchone": None}, {"fetchone": (77,)}])
    observation_time = datetime(2026, 1, 1, 9, 31, tzinfo=timezone.utc)
    result = pipeline.get_or_create_open_analysis_run(
        conn.cursor(), security_id=10, observation_time=observation_time
    )
    assert result == 77
    executed_sql = " ".join(sql for sql, _ in conn.cursor_obj.queries)
    assert "INSERT INTO analysis_run" in executed_sql
    insert_params = conn.cursor_obj.queries[1][1]
    assert insert_params[1] == observation_time
    assert insert_params[2] == observation_time


def test_process_new_bar_stores_anomaly_notifies_and_checks_alerts():
    from analysis import pipeline

    ts = datetime(2026, 1, 1, 9, 31, tzinfo=timezone.utc)

    # Connection #1: store bar (security lookup + insert + run lookup + run update)
    conn_store = FakeConnection([
        {"fetchone": (10,)},   # get_security_id
        {},                     # store_price_bar (INSERT ... ON CONFLICT, no RETURNING)
        {"fetchone": (55,)},   # get_or_create_open_analysis_run finds an open run
        {},                     # UPDATE analysis_run end_time
    ])
    # Connection #2: store the one detected anomaly (INSERT ... RETURNING anomaly_id)
    conn_anomaly = FakeConnection([{"fetchone": (900,)}])

    fake_event = {
        "security_id": 10, "symbol": "AAPL", "timestamp": ts,
        "anomaly_score": 3.1, "threshold": 2.0, "anomaly_type": "realtime_positive_return_spike",
    }

    with patch.object(pipeline, "get_connection", side_effect=[conn_store, conn_anomaly]), \
         patch.object(pipeline, "evaluate_current_bar", return_value=[fake_event]) as mock_eval, \
         patch.object(pipeline, "notify_users_for_realtime_anomaly") as mock_notify, \
         patch.object(pipeline, "check_all_active_alerts",
                       return_value={"alerts_checked": 1, "notifications_created": 1, "notifications": []}) as mock_alerts:
        result = pipeline.process_new_bar(
            "AAPL", ts, 100.0, 101.0, 99.0, 100.5, 5000, 20, 100.2, timeframe="minute",
        )

    mock_eval.assert_called_once_with("AAPL", ts)
    mock_notify.assert_called_once()
    mock_alerts.assert_called_once()
    assert result["symbol"] == "AAPL"
    assert result["analysis_id"] == 55
    assert result["anomalies_detected"] == 1
    assert result["anomaly_ids"] == [900]
    assert result["alert_notifications_created"] == 1
    update_sql, update_params = conn_store.cursor_obj.queries[3]
    assert "GREATEST(end_time" in update_sql
    assert update_params == (ts, 55)


def test_process_new_bar_with_no_anomalies_still_checks_alerts():
    from analysis import pipeline

    ts = datetime(2026, 1, 1, 9, 31, tzinfo=timezone.utc)
    conn_store = FakeConnection([
        {"fetchone": (10,)},
        {},
        {"fetchone": (55,)},
        {},
    ])

    with patch.object(pipeline, "get_connection", return_value=conn_store), \
         patch.object(pipeline, "evaluate_current_bar", return_value=[]), \
         patch.object(pipeline, "notify_users_for_realtime_anomaly") as mock_notify, \
         patch.object(pipeline, "check_all_active_alerts",
                       return_value={"alerts_checked": 0, "notifications_created": 0, "notifications": []}) as mock_alerts:
        result = pipeline.process_new_bar(
            "AAPL", ts, 100.0, 101.0, 99.0, 100.1, 1000, 10, 100.0,
        )

    mock_notify.assert_not_called()
    mock_alerts.assert_called_once()
    assert result["anomalies_detected"] == 0
    assert result["anomaly_ids"] == []


def test_process_new_bar_can_skip_alert_check():
    from analysis import pipeline

    ts = datetime(2026, 1, 1, 9, 31, tzinfo=timezone.utc)
    conn_store = FakeConnection([{"fetchone": (10,)}, {}, {"fetchone": (55,)}, {}])

    with patch.object(pipeline, "get_connection", return_value=conn_store), \
         patch.object(pipeline, "evaluate_current_bar", return_value=[]), \
         patch.object(pipeline, "check_all_active_alerts") as mock_alerts:
        result = pipeline.process_new_bar(
            "AAPL", ts, 100.0, 101.0, 99.0, 100.1, 1000, 10, 100.0, run_alert_check=False,
        )

    mock_alerts.assert_not_called()
    assert result["alert_notifications_created"] == 0


def test_process_latest_stored_bar_reprocesses_latest_bar():
    from analysis import pipeline

    ts = datetime(2026, 1, 1, 9, 31, tzinfo=timezone.utc)
    lookup_conn = FakeConnection([
        {"fetchone": (10,)},                                        # security_id
        {"fetchone": (ts, 100.0, 101.0, 99.0, 100.5, 5000, 20, 100.2)},  # latest bar
    ])

    with patch.object(pipeline, "get_connection", return_value=lookup_conn), \
         patch.object(pipeline, "process_new_bar", return_value={"ok": True}) as mock_process:
        result = pipeline.process_latest_stored_bar("AAPL", timeframe="minute")

    mock_process.assert_called_once()
    args = mock_process.call_args[0]
    assert args[0] == "AAPL"
    assert args[1] == ts
    assert result == {"ok": True}


def test_process_latest_stored_bar_raises_when_no_data():
    from analysis import pipeline

    conn = FakeConnection([{"fetchone": (10,)}, {"fetchone": None}])
    with patch.object(pipeline, "get_connection", return_value=conn):
        try:
            pipeline.process_latest_stored_bar("AAPL")
            assert False, "expected ValueError"
        except ValueError:
            pass


def test_run_historical_analysis_delegates_per_symbol():
    from analysis import pipeline

    with patch("analysis.run_analysis.run_analysis", return_value=42) as mock_run:
        result = pipeline.run_historical_analysis(["AAPL", "MSFT"])

    assert result == {"AAPL": 42, "MSFT": 42}
    assert mock_run.call_count == 2


def test_run_historical_analysis_defaults_to_all_symbols():
    from analysis import pipeline

    with patch("analysis.run_analysis.run_all_symbols", return_value={"AAPL": 1}) as mock_all:
        result = pipeline.run_historical_analysis()

    mock_all.assert_called_once()
    assert result == {"AAPL": 1}
