# Delivery Notes

This file summarizes the state of the delivered project. See `README.md`
for full documentation, `RUNBOOK.md` for exact startup order, and
`TEST_GUIDE.md` for test details.

## What is included

1. Historical daily data establishes long-term/inter-day behaviour
   (`analysis/run_analysis.py`).
2. Historical 1-minute data establishes the intraday baseline.
3. Alpaca WebSocket minute bars provide the current real-time observation
   (`realtime/stream_processor.py`).
4. `analysis/pipeline.py` is the single orchestration module for the
   real-time workflow (store bar -> recent analysis -> anomaly detection ->
   store anomaly -> anomaly notification -> alert evaluation ->
   notification); both the live stream processor and the API's manual
   trigger endpoint call the same functions.
5. The current bar is excluded from its own adaptive baseline at both the
   historical and real-time layers.
6. Price and volume bounds are recalculated from prior rolling distributions
   using per-symbol Tukey fences; numeric thresholds are not preset.
7. Detected anomalies are stored in `anomaly`, tied to a traceable
   `analysis_run`, and can notify watching users (deduplicated).
8. Active user price alerts are evaluated independently of anomaly
   detection and can create notifications (deduplicated: at most one unread
   notification per alert at a time).
9. FastAPI exposes stock, watchlist, alert, notification, preference, and
   processing/pipeline endpoints.
10. API lifespan automation coordinates one Alpaca stream, periodic history
    refreshes, daily analysis when a new daily bar arrives, and recurring
    alert checks. `/automation/status` reports worker state.
11. A React + Vite dashboard consumes the API: stock overview, adaptive
    threshold explanation, price/volume
    charts with anomaly markers, watchlists, alerts, notifications,
    preferences, and polling-based refresh.
11. A modular pytest suite (unit tests with mocked DB/Alpaca + gated
    integration tests) covers ingestion, indicators, historical analysis,
    real-time detection, the pipeline, alerts, notifications, and the API.

## SQL to run

### Fresh database (required)

Run only `sql/01_schema.sql`, then run metadata ingestion.

### Existing database from an earlier single-timeframe version (instead of the above)

Run `sql/02_migrate_existing_database.sql`. This is required before loading
minute bars because the old schema used `(security_id, timestamp)` as the
price-bar key; the current schema needs `timeframe` in that key so daily and
minute bars can coexist without being mixed.

**Do NOT run both `01_schema.sql` and `02_migrate_existing_database.sql`
against the same database.**

### Optional demo data

`sql/03_optional_demo_data.sql` is optional. It creates a demo user,
preference, watchlist, and AAPL watchlist membership. It is not needed for
ingestion or anomaly detection.

## Credentials

`.env` is intentionally excluded from this delivery. Use `.env.example` (and
`dashboard/.env.example`) and fill in local credentials — never commit real
credentials.

## Validation performed in this delivery environment

- All Python source files compile without error.
- The complete suite (`python -m pytest -q`) passes: **93 passed, 1 skipped**.
  It includes local PostgreSQL/TimescaleDB and read-only Alpaca integration
  checks; the database-writing live price-ingestion test remains opt-in.
- The dashboard (`dashboard/`) was installed (`npm install`) and built
  (`npm run build`) successfully with no errors.
- Daily and minute price history was refreshed from the configured Alpaca
  feed, then historical daily anomaly analysis was run against the configured
  PostgreSQL/TimescaleDB database.
