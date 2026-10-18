"""Active price-alert evaluation.

A price alert is a user-defined standing rule (e.g. "AAPL above 320") and is
evaluated independently of the statistical anomaly detector: the alert fires
whenever the condition is met by the latest stored price, regardless of
whether that price move is statistically unusual.

Duplicate-notification protection
----------------------------------
``check_all_active_alerts`` may be invoked repeatedly (once per incoming
real-time bar, or manually via the API). If the price remains above/below
the target for many consecutive observations, we must not create a new
notification every single time. The rule implemented here is:

    An alert may have at most one UNREAD notification at a time.

If an unread notification already exists for (user_id, alert_no), the alert
is considered "already flagged" and no new notification is created. Once the
user marks that notification as read (``PATCH .../notifications/{id}/read``),
the alert becomes eligible to fire again on the next observation that still
satisfies the condition. This avoids flooding the user while still allowing
alerts to re-trigger after being acknowledged, without requiring any change
to the documented NOTIFICATION schema.
"""
from database.connection import get_connection


def check_all_active_alerts(user_id=None, alert_no=None):
    connection = get_connection()
    notifications_created = []
    try:
        with connection.cursor() as cursor:
            query = """
                SELECT a.user_id, a.alert_no, a.security_id, s.symbol,
                       a.condition, a.target_price
                FROM alert a
                JOIN security s ON s.security_id = a.security_id
                WHERE a.status = 'active'
            """
            parameters = []
            if user_id is not None:
                query += " AND a.user_id = %s"
                parameters.append(user_id)
            if alert_no is not None:
                query += " AND a.alert_no = %s"
                parameters.append(alert_no)
            cursor.execute(query, tuple(parameters))
            alerts = cursor.fetchall()
            for user_id, alert_no, security_id, symbol, condition, target in alerts:
                target = float(target)
                cursor.execute(
                    """
                    SELECT timestamp, close
                    FROM price_bar
                    WHERE security_id = %s
                    ORDER BY timestamp DESC
                    LIMIT 1
                    """,
                    (security_id,),
                )
                latest = cursor.fetchone()
                if latest is None:
                    continue
                event_timestamp, current_price = latest
                current_price = float(current_price)
                triggered = (
                    current_price > target if condition == 'above'
                    else current_price < target if condition == 'below'
                    else False
                )
                if not triggered:
                    continue

                cursor.execute(
                    "SELECT price_alerts FROM user_preference WHERE user_id = %s",
                    (user_id,),
                )
                preference = cursor.fetchone()
                if preference is not None and not preference[0]:
                    continue

                # Do not create a new notification while an unread one for this
                # exact alert already exists. This is what prevents hundreds of
                # identical notifications while the price stays past the target.
                cursor.execute(
                    """
                    SELECT notification_id
                    FROM notification
                    WHERE user_id = %s AND alert_no = %s AND status = 'unread'
                    LIMIT 1
                    """,
                    (user_id, alert_no),
                )
                if cursor.fetchone() is not None:
                    continue

                message = (
                    f"{symbol} price alert triggered. Condition: {condition} {target:.2f}. "
                    f"Current price: {current_price:.2f}. Observation: {event_timestamp.isoformat()}."
                )
                cursor.execute(
                    """
                    INSERT INTO notification
                        (user_id, alert_no, anomaly_id, message, created_at, status)
                    VALUES (%s, %s, NULL, %s, CURRENT_TIMESTAMP, 'unread')
                    ON CONFLICT (user_id, alert_no)
                        WHERE alert_no IS NOT NULL AND status = 'unread'
                    DO NOTHING
                    RETURNING notification_id
                    """,
                    (user_id, alert_no, message),
                )
                inserted = cursor.fetchone()
                if inserted is None:
                    continue
                notifications_created.append({
                    "notification_id": inserted[0],
                    "user_id": user_id,
                    "alert_no": alert_no,
                    "symbol": symbol,
                    "current_price": current_price,
                    "target_price": target,
                    "timestamp": event_timestamp,
                })
        connection.commit()
        return {
            "alerts_checked": len(alerts),
            "notifications_created": len(notifications_created),
            "notifications": notifications_created,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
