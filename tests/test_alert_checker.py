"""Unit tests for alerts/alert_checker.py using a mocked database connection.

Covers: alert triggers and creates a notification; alert not triggered;
respecting user_preference.price_alerts=False; and the duplicate-notification
guard (no second notification while an unread one already exists for the same
alert).
"""
from datetime import datetime, timezone
from unittest.mock import patch

from tests.conftest import FakeConnection


def _alert_row(user_id=1, alert_no=1, security_id=10, symbol="AAPL", condition="above", target=300.0):
    return (user_id, alert_no, security_id, symbol, condition, target)


def test_alert_triggers_and_creates_notification():
    from alerts import alert_checker

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conn = FakeConnection([
        {"fetchall": [_alert_row(condition="above", target=300.0)]},  # active alerts
        {"fetchone": (now, 321.0)},                                    # latest price_bar
        {"fetchone": None},                                            # user_preference (none -> allowed)
        {"fetchone": None},                                            # no existing unread notification
        {"fetchone": (555,)},                                          # INSERT ... RETURNING notification_id
    ])

    with patch.object(alert_checker, "get_connection", return_value=conn):
        result = alert_checker.check_all_active_alerts()

    assert result["alerts_checked"] == 1
    assert result["notifications_created"] == 1
    assert result["notifications"][0]["notification_id"] == 555
    assert conn.committed is True


def test_alert_not_triggered_when_condition_not_met():
    from alerts import alert_checker

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conn = FakeConnection([
        {"fetchall": [_alert_row(condition="above", target=300.0)]},
        {"fetchone": (now, 250.0)},  # price below target -> 'above' condition not triggered
    ])

    with patch.object(alert_checker, "get_connection", return_value=conn):
        result = alert_checker.check_all_active_alerts()

    assert result["notifications_created"] == 0


def test_alert_respects_disabled_price_alert_preference():
    from alerts import alert_checker

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conn = FakeConnection([
        {"fetchall": [_alert_row(condition="above", target=300.0)]},
        {"fetchone": (now, 321.0)},
        {"fetchone": (False,)},  # price_alerts disabled
    ])

    with patch.object(alert_checker, "get_connection", return_value=conn):
        result = alert_checker.check_all_active_alerts()

    assert result["notifications_created"] == 0


def test_alert_does_not_duplicate_notification_while_unread_exists():
    """If the price stays above the target across repeated alert-checker runs,
    only ONE unread notification should ever exist per alert."""
    from alerts import alert_checker

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conn = FakeConnection([
        {"fetchall": [_alert_row(condition="above", target=300.0)]},
        {"fetchone": (now, 321.0)},
        {"fetchone": None},        # preference allows alerts
        {"fetchone": (321,)},      # an unread notification ALREADY exists
    ])

    with patch.object(alert_checker, "get_connection", return_value=conn):
        result = alert_checker.check_all_active_alerts()

    assert result["notifications_created"] == 0
    executed_sql = " ".join(sql for sql, _ in conn.cursor_obj.queries)
    assert "INSERT INTO notification" not in executed_sql


def test_alert_insert_handles_concurrent_duplicate_safely():
    """The database uniqueness guard may win after the existence check."""
    from alerts import alert_checker

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conn = FakeConnection([
        {"fetchall": [_alert_row(condition="below", target=100.0)]},
        {"fetchone": (now, 95.0)},
        {"fetchone": None},
        {"fetchone": None},
        {"fetchone": None},  # concurrent worker inserted first
    ])

    with patch.object(alert_checker, "get_connection", return_value=conn):
        result = alert_checker.check_all_active_alerts()

    assert result["notifications_created"] == 0
    assert conn.committed is True
    insert_sql = next(sql for sql, _ in conn.cursor_obj.queries if "INSERT INTO notification" in sql)
    assert "ON CONFLICT (user_id, alert_no)" in insert_sql


def test_below_condition_triggers_correctly():
    from alerts import alert_checker

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conn = FakeConnection([
        {"fetchall": [_alert_row(condition="below", target=100.0)]},
        {"fetchone": (now, 95.0)},
        {"fetchone": None},
        {"fetchone": None},
        {"fetchone": (556,)},
    ])

    with patch.object(alert_checker, "get_connection", return_value=conn):
        result = alert_checker.check_all_active_alerts()

    assert result["notifications_created"] == 1
