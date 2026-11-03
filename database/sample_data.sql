-- OPTIONAL: only execute this if you need a local user for API/watchlist/alert testing.
-- It is NOT required for ingestion or anomaly detection.

INSERT INTO app_user(name, email)
VALUES ('Demo User', 'demo@example.com')
ON CONFLICT (email) DO NOTHING;

INSERT INTO user_preference(user_id, price_alerts, anomaly_alerts, notification_mode)
SELECT user_id, TRUE, TRUE, 'in_app'
FROM app_user
WHERE email = 'demo@example.com'
ON CONFLICT (user_id) DO NOTHING;

INSERT INTO watchlist(user_id, watchlist_no, name)
SELECT user_id, 1, 'Demo Watchlist'
FROM app_user
WHERE email = 'demo@example.com'
  AND NOT EXISTS (
      SELECT 1 FROM watchlist w
      WHERE w.user_id = app_user.user_id AND w.watchlist_no = 1
  );

INSERT INTO watchlist_security(user_id, watchlist_no, security_id)
SELECT u.user_id, 1, s.security_id
FROM app_user u
JOIN security s ON s.symbol = 'AAPL'
WHERE u.email = 'demo@example.com'
ON CONFLICT DO NOTHING;
