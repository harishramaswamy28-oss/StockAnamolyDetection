CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS sector (
    sector_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS company (
    company_id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    sector_id INTEGER NOT NULL REFERENCES sector(sector_id)
);

CREATE TABLE IF NOT EXISTS exchange (
    exchange_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    country VARCHAR(100),
    timezone VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS security (
    security_id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    asset_class VARCHAR(50),
    status VARCHAR(50),
    company_id INTEGER NOT NULL REFERENCES company(company_id)
);

CREATE TABLE IF NOT EXISTS exchange_security (
    exchange_id INTEGER NOT NULL REFERENCES exchange(exchange_id) ON DELETE CASCADE,
    security_id INTEGER NOT NULL REFERENCES security(security_id) ON DELETE CASCADE,
    PRIMARY KEY (exchange_id, security_id)
);

CREATE TABLE IF NOT EXISTS price_bar (
    security_id INTEGER NOT NULL REFERENCES security(security_id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL,
    timeframe VARCHAR(20) NOT NULL,
    open NUMERIC(18,6) NOT NULL,
    high NUMERIC(18,6) NOT NULL,
    low NUMERIC(18,6) NOT NULL,
    close NUMERIC(18,6) NOT NULL,
    volume BIGINT NOT NULL,
    trade_count INTEGER,
    vwap NUMERIC(18,6),
    PRIMARY KEY (security_id, timestamp, timeframe),
    CONSTRAINT chk_price_bar_timeframe CHECK (timeframe IN ('day', 'minute'))
);

SELECT create_hypertable('price_bar', by_range('timestamp'), if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_price_bar_security_time
    ON price_bar (security_id, timestamp DESC);

CREATE TABLE IF NOT EXISTS analysis_run (
    analysis_id SERIAL PRIMARY KEY,
    security_id INTEGER NOT NULL REFERENCES security(security_id) ON DELETE CASCADE,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    method VARCHAR(150) NOT NULL,
    status VARCHAR(50) NOT NULL,
    CONSTRAINT chk_analysis_time CHECK (end_time >= start_time)
);

CREATE TABLE IF NOT EXISTS anomaly (
    anomaly_id SERIAL PRIMARY KEY,
    security_id INTEGER NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    timeframe VARCHAR(20) NOT NULL,
    analysis_id INTEGER NOT NULL REFERENCES analysis_run(analysis_id) ON DELETE CASCADE,
    anomaly_score NUMERIC(18,6) NOT NULL,
    threshold NUMERIC(18,6) NOT NULL,
    anomaly_type VARCHAR(100) NOT NULL,
    CONSTRAINT fk_anomaly_price_bar
        FOREIGN KEY (security_id, timestamp, timeframe)
        REFERENCES price_bar(security_id, timestamp, timeframe)
        ON DELETE CASCADE,
    CONSTRAINT uq_anomaly_run_bar_type
        UNIQUE (analysis_id, security_id, timestamp, timeframe, anomaly_type)
);

CREATE INDEX IF NOT EXISTS idx_anomaly_security_time
    ON anomaly (security_id, timestamp DESC);

CREATE TABLE IF NOT EXISTS app_user (
    user_id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS watchlist (
    user_id INTEGER NOT NULL REFERENCES app_user(user_id) ON DELETE CASCADE,
    watchlist_no INTEGER NOT NULL,
    name VARCHAR(100) NOT NULL,
    PRIMARY KEY (user_id, watchlist_no)
);

CREATE TABLE IF NOT EXISTS watchlist_security (
    user_id INTEGER NOT NULL,
    watchlist_no INTEGER NOT NULL,
    security_id INTEGER NOT NULL REFERENCES security(security_id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, watchlist_no, security_id),
    FOREIGN KEY (user_id, watchlist_no)
        REFERENCES watchlist(user_id, watchlist_no)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS alert (
    user_id INTEGER NOT NULL REFERENCES app_user(user_id) ON DELETE CASCADE,
    alert_no INTEGER NOT NULL,
    security_id INTEGER NOT NULL REFERENCES security(security_id),
    condition VARCHAR(50) NOT NULL,
    target_price NUMERIC(18,6) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    PRIMARY KEY (user_id, alert_no),
    CONSTRAINT chk_alert_condition CHECK (condition IN ('above', 'below'))
);

CREATE TABLE IF NOT EXISTS notification (
    notification_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES app_user(user_id) ON DELETE CASCADE,
    alert_no INTEGER,
    anomaly_id INTEGER REFERENCES anomaly(anomaly_id) ON DELETE CASCADE,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50) NOT NULL DEFAULT 'unread',
    CONSTRAINT fk_notification_alert
        FOREIGN KEY (user_id, alert_no)
        REFERENCES alert(user_id, alert_no)
        ON DELETE CASCADE,
    CONSTRAINT chk_notification_source CHECK (
        (alert_no IS NOT NULL AND anomaly_id IS NULL)
        OR
        (alert_no IS NULL AND anomaly_id IS NOT NULL)
    ),
    CONSTRAINT uq_notification_user_anomaly UNIQUE (user_id, anomaly_id)
);

CREATE INDEX IF NOT EXISTS idx_notification_user_created
    ON notification (user_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_notification_unread_alert
    ON notification (user_id, alert_no)
    WHERE alert_no IS NOT NULL AND status = 'unread';

CREATE TABLE IF NOT EXISTS user_preference (
    user_id INTEGER PRIMARY KEY REFERENCES app_user(user_id) ON DELETE CASCADE,
    price_alerts BOOLEAN NOT NULL DEFAULT TRUE,
    anomaly_alerts BOOLEAN NOT NULL DEFAULT TRUE,
    notification_mode VARCHAR(50) NOT NULL DEFAULT 'in_app',
    CONSTRAINT chk_notification_mode CHECK (notification_mode IN ('in_app', 'email'))
);
