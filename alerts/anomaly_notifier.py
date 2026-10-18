from database.connection import get_connection


def notify_users_for_realtime_anomaly(anomaly_id: int, security_id: int, symbol: str, timestamp,
                                      anomaly_type: str, anomaly_score: float, threshold: float):
    connection = get_connection()
    created = []
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT w.user_id
                FROM watchlist w
                JOIN watchlist_security ws
                  ON ws.user_id = w.user_id AND ws.watchlist_no = w.watchlist_no
                WHERE ws.security_id = %s
                """,
                (security_id,),
            )
            users = [r[0] for r in cursor.fetchall()]
            for user_id in users:
                cursor.execute("SELECT anomaly_alerts FROM user_preference WHERE user_id = %s", (user_id,))
                preference = cursor.fetchone()
                if preference is not None and not preference[0]:
                    continue
                cursor.execute(
                    """
                    SELECT n.notification_id
                    FROM notification n
                    WHERE n.user_id = %s AND n.anomaly_id = %s
                    LIMIT 1
                    """,
                    (user_id, anomaly_id),
                )
                if cursor.fetchone() is not None:
                    continue
                message = (
                    f"Real-time anomaly for {symbol}. Type: {anomaly_type}. "
                    f"Score: {anomaly_score:.2f}. Threshold: {threshold:.2f}."
                )
                cursor.execute(
                    """
                    INSERT INTO notification
                        (user_id, alert_no, anomaly_id, message, created_at, status)
                    VALUES (%s, NULL, %s, %s, CURRENT_TIMESTAMP, 'unread')
                    ON CONFLICT (user_id, anomaly_id) DO NOTHING
                    RETURNING notification_id
                    """,
                    (user_id, anomaly_id, message),
                )
                inserted = cursor.fetchone()
                if inserted is None:
                    continue
                created.append({
                    "notification_id": inserted[0],
                    "user_id": user_id,
                    "anomaly_id": anomaly_id,
                    "symbol": symbol,
                    "anomaly_type": anomaly_type,
                })
        connection.commit()
        return created
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
