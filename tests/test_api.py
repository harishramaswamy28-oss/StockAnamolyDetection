"""Unit tests for the FastAPI application (api/main.py) using FastAPI's
TestClient and a mocked database connection -- no live PostgreSQL required.

Covers root/health, stock endpoints, watchlist CRUD, alert CRUD, notification
read/unread, preferences, and the processing/pipeline trigger endpoints. Each
test patches ``api.main.get_connection`` (and, where a route delegates to
another module, that module's own ``get_connection``) with a FakeConnection
returning scripted rows.
"""
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from tests.conftest import FakeConnection


def _client():
    from api.main import app
    return TestClient(app)


def test_root_and_health():
    client = _client()
    resp = client.get("/")
    assert resp.status_code == 200
    assert "message" in resp.json()

    conn = FakeConnection([])
    with patch("api.main.get_connection", return_value=conn):
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_health_reports_unhealthy_when_db_unreachable():
    client = _client()
    with patch("api.main.get_connection", side_effect=RuntimeError("connection refused")):
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "unhealthy"


def test_get_stocks_returns_security_list():
    client = _client()
    rows = [(1, "AAPL", "Apple Inc.", "us_equity", "active", 1)]
    conn = FakeConnection([{"fetchall": rows}])
    with patch("api.main.get_connection", return_value=conn):
        resp = client.get("/stocks")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["symbol"] == "AAPL"


def test_get_stock_prices_returns_ohlcv():
    client = _client()
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [(ts, 100.0, 101.0, 99.0, 100.5, 1000, 20, 100.2)]
    conn = FakeConnection([{"fetchall": rows}])
    with patch("api.main.get_connection", return_value=conn):
        resp = client.get("/stocks/aapl/prices?timeframe=day&limit=10")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["close"] == 100.5


def test_get_stock_prices_rejects_invalid_timeframe():
    client = _client()
    resp = client.get("/stocks/AAPL/prices?timeframe=hour")
    assert resp.status_code == 422
    assert resp.json() == {"error": "timeframe must be day or minute"}


def test_get_stock_anomalies():
    client = _client()
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [("AAPL", 1, ts, "positive_return_spike", 3.1, 2.0, 5)]
    conn = FakeConnection([{"fetchall": rows}])
    with patch("api.main.get_connection", return_value=conn):
        resp = client.get("/stocks/AAPL/anomalies")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["anomaly_type"] == "positive_return_spike"


def test_get_stock_anomalies_can_filter_by_timeframe():
    client = _client()
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [("AAPL", 1, ts, "realtime_positive_return_spike", 3.1, 2.0, 5)]
    conn = FakeConnection([{"fetchall": rows}])
    with patch("api.main.get_connection", return_value=conn):
        resp = client.get("/stocks/AAPL/anomalies?timeframe=minute")
    assert resp.status_code == 200
    assert resp.json()[0]["anomaly_type"] == "realtime_positive_return_spike"
    sql, params = conn.cursor_obj.queries[0]
    assert "a.timeframe = %s" in sql
    assert params == ("AAPL", "minute", 200)


def test_get_stock_anomalies_rejects_invalid_timeframe():
    client = _client()
    resp = client.get("/stocks/AAPL/anomalies?timeframe=hour")
    assert resp.status_code == 422
    assert resp.json() == {"error": "timeframe must be day or minute"}


def test_get_stock_summary_not_found():
    client = _client()
    conn = FakeConnection([{"fetchone": None}])
    with patch("api.main.get_connection", return_value=conn):
        resp = client.get("/stocks/ZZZZ/summary")
    assert resp.status_code == 404
    assert "error" in resp.json()


def test_get_stock_summary_found():
    client = _client()
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conn = FakeConnection([
        {"fetchone": (1, "AAPL", "Apple Inc.")},
        {"fetchone": (ts, 150.0)},
        {"fetchone": (2, 1, 0, 3)},
    ])
    with patch("api.main.get_connection", return_value=conn):
        resp = client.get("/stocks/AAPL/summary")
    body = resp.json()
    assert body["symbol"] == "AAPL"
    assert body["latest_price"] == 150.0
    assert body["total_anomalies"] == 3


def test_create_and_list_watchlist():
    client = _client()

    conn_create = FakeConnection([{"fetchone": (1,)}, {"fetchone": (1,)}])
    with patch("api.main.get_connection", return_value=conn_create):
        resp = client.post("/users/1/watchlists", json={"name": "Tech"})
    assert resp.status_code == 200
    assert resp.json()["watchlist_no"] == 1

    conn_list = FakeConnection([{"fetchall": [(1, "Tech", 10, "AAPL", "Apple Inc.")]}])
    with patch("api.main.get_connection", return_value=conn_list):
        resp = client.get("/users/1/watchlists")
    body = resp.json()
    assert body[0]["name"] == "Tech"
    assert body[0]["stocks"][0]["symbol"] == "AAPL"


def test_create_watchlist_missing_user():
    client = _client()
    conn = FakeConnection([{"fetchone": None}])
    with patch("api.main.get_connection", return_value=conn):
        resp = client.post("/users/999/watchlists", json={"name": "Tech"})
    assert resp.status_code == 404
    assert "error" in resp.json()


def test_add_and_remove_watchlist_stock():
    client = _client()
    conn_add = FakeConnection([{"fetchone": (1,)}, {"fetchone": (10, "AAPL", "Apple Inc.")}, {}])
    with patch("api.main.get_connection", return_value=conn_add):
        resp = client.post("/users/1/watchlists/1/stocks", json={"symbol": "aapl"})
    assert resp.json()["stock"]["symbol"] == "AAPL"

    conn_remove = FakeConnection([{"fetchone": (10,)}, {"fetchone": (10,)}])
    with patch("api.main.get_connection", return_value=conn_remove):
        resp = client.delete("/users/1/watchlists/1/stocks/AAPL")
    assert resp.json()["message"] == "Stock removed from watchlist"


def test_delete_watchlist():
    client = _client()
    conn = FakeConnection([{"fetchone": ("Tech",)}])
    with patch("api.main.get_connection", return_value=conn):
        resp = client.delete("/users/1/watchlists/1")
    assert resp.json()["message"] == "Watchlist deleted successfully"


def test_create_alert_and_list():
    client = _client()
    conn_create = FakeConnection([{"fetchone": (1,)}, {"fetchone": (10, "AAPL")}, {"fetchone": (1,)}])
    with patch("api.main.get_connection", return_value=conn_create):
        resp = client.post("/users/1/alerts", json={"symbol": "aapl", "condition": "above", "target_price": 300})
    assert resp.status_code == 200
    assert resp.json()["condition"] == "above"

    conn_list = FakeConnection([{"fetchall": [(1, 10, "AAPL", "Apple Inc.", "above", 300.0, "active")]}])
    with patch("api.main.get_connection", return_value=conn_list):
        resp = client.get("/users/1/alerts")
    assert resp.json()[0]["symbol"] == "AAPL"


def test_create_alert_rejects_invalid_condition():
    client = _client()
    resp = client.post("/users/1/alerts", json={"symbol": "AAPL", "condition": "sideways", "target_price": 1})
    assert resp.status_code == 422
    assert "error" in resp.json()


def test_create_alert_rejects_non_positive_target_price():
    client = _client()
    resp = client.post(
        "/users/1/alerts",
        json={"symbol": "AAPL", "condition": "below", "target_price": 0},
    )
    assert resp.status_code == 422


def test_delete_alert():
    client = _client()
    conn = FakeConnection([{"fetchone": (1,)}])
    with patch("api.main.get_connection", return_value=conn):
        resp = client.delete("/users/1/alerts/1")
    assert resp.json()["message"] == "Alert deleted successfully"


def test_get_notifications_and_mark_read():
    client = _client()
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [(1, 1, None, "AAPL", "Alert triggered", ts, "unread", "price_alert")]
    conn = FakeConnection([{"fetchall": rows}])
    with patch("api.main.get_connection", return_value=conn):
        resp = client.get("/users/1/notifications")
    assert resp.json()[0]["source"] == "price_alert"

    conn_read = FakeConnection([{"fetchone": (1, "read")}])
    with patch("api.main.get_connection", return_value=conn_read):
        resp = client.patch("/users/1/notifications/1/read")
    assert resp.json()["status"] == "read"


def test_preferences_get_and_update():
    client = _client()
    conn_get = FakeConnection([{"fetchone": (1, True, True, "in_app")}])
    with patch("api.main.get_connection", return_value=conn_get):
        resp = client.get("/users/1/preferences")
    assert resp.json()["notification_mode"] == "in_app"

    conn_put = FakeConnection([{"fetchone": (1,)}])
    with patch("api.main.get_connection", return_value=conn_put):
        resp = client.put(
            "/users/1/preferences",
            json={"price_alerts": True, "anomaly_alerts": False, "notification_mode": "in_app"},
        )
    assert resp.json()["anomaly_alerts"] is False


def test_preferences_reject_invalid_notification_mode():
    client = _client()
    resp = client.put(
        "/users/1/preferences",
        json={"price_alerts": True, "anomaly_alerts": True, "notification_mode": "sms"},
    )
    assert resp.status_code == 422
    assert "error" in resp.json()


def test_check_alerts_endpoint():
    client = _client()
    with patch("api.main.check_all_active_alerts",
               return_value={"alerts_checked": 2, "notifications_created": 0, "notifications": []}):
        resp = client.post("/alerts/check")
    assert resp.json()["alerts_checked"] == 2


def test_evaluate_alert_reports_triggered_when_unread_notification_exists():
    client = _client()
    ts = datetime(2026, 9, 17, 16, 41, tzinfo=timezone.utc)
    conn = FakeConnection([{"fetchone": ("below", 1000.0, "MSFT", ts, 495.55, "active", 1)}])
    with patch(
        "api.main.check_all_active_alerts",
        return_value={"notifications": []},
    ) as check_alerts, patch("api.main.get_connection", return_value=conn):
        resp = client.get("/users/1/alerts/1/evaluate")

    assert resp.status_code == 200
    assert resp.json()["triggered"] is True
    assert resp.json()["notification_created"] is False
    assert resp.json()["notification_id"] == 1
    check_alerts.assert_called_once_with(user_id=1, alert_no=1)


def test_run_analysis_for_symbol_endpoint():
    client = _client()
    with patch("api.main.run_historical_analysis", return_value={"AAPL": 42}):
        resp = client.post("/analysis/run/aapl")
    assert resp.json() == {"symbol": "AAPL", "analysis_id": 42}


def test_run_analysis_for_symbol_handles_unknown_symbol():
    client = _client()
    with patch("api.main.run_historical_analysis", side_effect=ValueError("Security not found: ZZZZ")):
        resp = client.post("/analysis/run/zzzz")
    assert resp.status_code == 404
    assert "error" in resp.json()


def test_pipeline_process_endpoint():
    client = _client()
    with patch("api.main.process_latest_stored_bar",
               return_value={"symbol": "AAPL", "anomalies_detected": 0, "alert_notifications_created": 0}):
        resp = client.post("/pipeline/process/AAPL")
    assert resp.json()["symbol"] == "AAPL"


def test_pipeline_process_endpoint_rejects_bad_timeframe():
    client = _client()
    resp = client.post("/pipeline/process/AAPL?timeframe=hour")
    assert resp.status_code == 422
    assert "error" in resp.json()
