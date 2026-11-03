-- 1. Latest stored price bars across the monitored securities
SELECT s.symbol, pb.timestamp, pb.timeframe, pb.close, pb.volume
FROM price_bar AS pb
JOIN security AS s ON s.security_id = pb.security_id
ORDER BY pb.timestamp DESC
LIMIT 20;

-- 2. Stored bar counts by symbol and timeframe
SELECT s.symbol, pb.timeframe, COUNT(*) AS bar_count
FROM price_bar AS pb
JOIN security AS s ON s.security_id = pb.security_id
GROUP BY s.symbol, pb.timeframe
ORDER BY s.symbol, pb.timeframe;

-- 3. Recent anomaly records and the threshold applied
SELECT s.symbol, a.timestamp, a.timeframe, a.anomaly_type,
       a.anomaly_score, a.threshold
FROM anomaly AS a
JOIN security AS s ON s.security_id = a.security_id
ORDER BY a.timestamp DESC
LIMIT 20;

-- 4. Recent analysis runs with their security symbols
SELECT s.symbol, r.analysis_id, r.method, r.status, r.start_time, r.end_time
FROM analysis_run AS r
JOIN security AS s ON s.security_id = r.security_id
ORDER BY r.analysis_id DESC
LIMIT 20;

-- 5. Anomaly totals by security and anomaly type
SELECT s.symbol, a.anomaly_type, COUNT(*) AS occurrence_count
FROM anomaly AS a
JOIN security AS s ON s.security_id = a.security_id
GROUP BY s.symbol, a.anomaly_type
ORDER BY s.symbol, occurrence_count DESC;
