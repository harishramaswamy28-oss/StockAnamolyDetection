-- Enforce the documented rule that each alert can have at most one unread
-- notification, even when multiple workers evaluate the same alert at once.
-- Duplicate unread rows are redundant; retain the earliest notification.
BEGIN;

WITH ranked AS (
    SELECT notification_id,
           ROW_NUMBER() OVER (
               PARTITION BY user_id, alert_no
               ORDER BY created_at, notification_id
           ) AS duplicate_rank
    FROM notification
    WHERE alert_no IS NOT NULL AND status = 'unread'
)
DELETE FROM notification AS n
USING ranked AS r
WHERE n.notification_id = r.notification_id
  AND r.duplicate_rank > 1;

CREATE UNIQUE INDEX IF NOT EXISTS uq_notification_unread_alert
    ON notification (user_id, alert_no)
    WHERE alert_no IS NOT NULL AND status = 'unread';

COMMIT;
