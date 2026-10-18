"""Unit tests for alerts/anomaly_notifier.py using a mocked database
connection. Verifies that only watchlist-following users with anomaly_alerts
enabled are notified, and that a user is never notified twice for the same
anomaly_id (enforced both in application logic and by the DB unique
constraint uq_notification_user_anomaly).
"""
from datetime import datetime, timezone
from unittest.mock import patch

from tests.conftest import FakeConnection


def test_notifies_watchlist_users_with_anomaly_alerts_enabled():
    from alerts import anomaly_notifier

    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conn = FakeConnection([
        {"fetchall": [(1,), (2,)]},   # two users watch this security
        {"fetchone": None},           # user 1: no preference row -> default allowed
        {"fetchone": None},           # user 1: no existing notification for this anomaly
        {"fetchone": (900,)},         # user 1: INSERT ... RETURNING notification_id
        {"fetchone": (True,)},        # user 2: anomaly_alerts explicitly enabled
        {"fetchone": None},           # user 2: no existing notification
        {"fetchone": (901,)},         # user 2: INSERT ... RETURNING notification_id
    ])

    with patch.object(anomaly_notifier, "get_connection", return_value=conn):
        created = anomaly_notifier.notify_users_for_realtime_anomaly(
            anomaly_id=42, security_id=10, symbol="AAPL", timestamp=ts,
            anomaly_type="realtime_positive_return_spike", anomaly_score=3.2, threshold=2.0,
        )

    assert len(created) == 2
    assert {c["user_id"] for c in created} == {1, 2}
    assert conn.committed is True


def test_skips_users_with_anomaly_alerts_disabled():
    from alerts import anomaly_notifier

    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conn = FakeConnection([
        {"fetchall": [(1,)]},
        {"fetchone": (False,)},  # anomaly_alerts disabled
    ])

    with patch.object(anomaly_notifier, "get_connection", return_value=conn):
        created = anomaly_notifier.notify_users_for_realtime_anomaly(
            anomaly_id=42, security_id=10, symbol="AAPL", timestamp=ts,
            anomaly_type="realtime_positive_return_spike", anomaly_score=3.2, threshold=2.0,
        )

    assert created == []


def test_does_not_duplicate_notification_for_same_anomaly():
    from alerts import anomaly_notifier

    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conn = FakeConnection([
        {"fetchall": [(1,)]},
        {"fetchone": None},      # preference allows
        {"fetchone": (777,)},    # a notification for this (user, anomaly) already exists
    ])

    with patch.object(anomaly_notifier, "get_connection", return_value=conn):
        created = anomaly_notifier.notify_users_for_realtime_anomaly(
            anomaly_id=42, security_id=10, symbol="AAPL", timestamp=ts,
            anomaly_type="realtime_positive_return_spike", anomaly_score=3.2, threshold=2.0,
        )

    assert created == []
    executed_sql = " ".join(sql for sql, _ in conn.cursor_obj.queries)
    assert "INSERT INTO notification" not in executed_sql


def test_anomaly_insert_handles_concurrent_duplicate_safely():
    from alerts import anomaly_notifier

    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conn = FakeConnection([
        {"fetchall": [(1,)]},
        {"fetchone": None},
        {"fetchone": None},
        {"fetchone": None},  # another worker inserted the notification first
    ])

    with patch.object(anomaly_notifier, "get_connection", return_value=conn):
        created = anomaly_notifier.notify_users_for_realtime_anomaly(
            anomaly_id=42, security_id=10, symbol="AAPL", timestamp=ts,
            anomaly_type="realtime_positive_return_spike", anomaly_score=3.2, threshold=2.0,
        )

    assert created == []
    assert conn.committed is True
    insert_sql = next(sql for sql, _ in conn.cursor_obj.queries if "INSERT INTO notification" in sql)
    assert "ON CONFLICT (user_id, anomaly_id) DO NOTHING" in insert_sql


def test_no_watchers_means_no_notifications():
    from alerts import anomaly_notifier

    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conn = FakeConnection([{"fetchall": []}])

    with patch.object(anomaly_notifier, "get_connection", return_value=conn):
        created = anomaly_notifier.notify_users_for_realtime_anomaly(
            anomaly_id=42, security_id=10, symbol="AAPL", timestamp=ts,
            anomaly_type="realtime_volume_spike", anomaly_score=2.5, threshold=2.0,
        )

    assert created == []
