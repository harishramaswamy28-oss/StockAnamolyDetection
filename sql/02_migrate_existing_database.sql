-- Run this ONLY if you are upgrading the existing database created by the earlier version.
-- If you are creating a fresh database, run only 01_schema.sql.
-- This migration distinguishes daily and 1-minute bars so both can coexist in PRICE_BAR.

BEGIN;

ALTER TABLE anomaly DROP CONSTRAINT IF EXISTS fk_anomaly_price_bar;
ALTER TABLE anomaly DROP CONSTRAINT IF EXISTS uq_anomaly_run_bar_type;
ALTER TABLE price_bar DROP CONSTRAINT IF EXISTS price_bar_pkey;

ALTER TABLE price_bar
    ADD COLUMN IF NOT EXISTS timeframe VARCHAR(20);

UPDATE price_bar
SET timeframe = 'day'
WHERE timeframe IS NULL;

ALTER TABLE price_bar
    ALTER COLUMN timeframe SET NOT NULL;

ALTER TABLE price_bar
    ADD CONSTRAINT chk_price_bar_timeframe
    CHECK (timeframe IN ('day', 'minute'));

ALTER TABLE price_bar
    ADD CONSTRAINT price_bar_pkey
    PRIMARY KEY (security_id, timestamp, timeframe);

ALTER TABLE anomaly
    ADD COLUMN IF NOT EXISTS timeframe VARCHAR(20);

UPDATE anomaly
SET timeframe = 'day'
WHERE timeframe IS NULL;

ALTER TABLE anomaly
    ALTER COLUMN timeframe SET NOT NULL;

ALTER TABLE anomaly
    ADD CONSTRAINT fk_anomaly_price_bar
    FOREIGN KEY (security_id, timestamp, timeframe)
    REFERENCES price_bar(security_id, timestamp, timeframe)
    ON DELETE CASCADE;

ALTER TABLE anomaly
    ADD CONSTRAINT uq_anomaly_run_bar_type
    UNIQUE (analysis_id, security_id, timestamp, timeframe, anomaly_type);

CREATE INDEX IF NOT EXISTS idx_price_bar_security_timeframe_time
    ON price_bar (security_id, timeframe, timestamp DESC);

COMMIT;
