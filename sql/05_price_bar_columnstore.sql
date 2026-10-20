-- Enable TimescaleDB Hypercore columnstore for older price bars.
-- Requires TimescaleDB 2.18 or newer.
-- The policy converts chunks older than 14 days in the background; newer
-- chunks remain rowstore for efficient ingestion and recent analysis.

ALTER TABLE public.price_bar SET (
    timescaledb.enable_columnstore = true,
    timescaledb.segmentby = 'security_id,timeframe',
    timescaledb.orderby = 'timestamp DESC'
);

CALL add_columnstore_policy(
    'public.price_bar',
    after => INTERVAL '14 days',
    if_not_exists => true
);
