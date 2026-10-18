# TEST_GUIDE

All tests live in [`tests/`](tests/) and run with `pytest`. Tests are split
into **unit tests** (no external services required; fast; run by default in
any environment) and **integration tests** (require a live PostgreSQL +
TimescaleDB instance and/or real Alpaca credentials; marked
`@pytest.mark.integration` and auto-skip when their precondition environment
variables are missing).

```powershell
pip install -r requirements-dev.txt
pytest -m "not integration"   # unit tests only
pytest -m integration         # integration tests only (skip if unconfigured)
pytest                        # everything
```

`tests/conftest.py` provides `FakeConnection`/`FakeCursor` — lightweight
stand-ins for a psycopg connection/cursor driven by a scripted sequence of
`fetchone`/`fetchall` results. Every unit test that exercises SQL
orchestration logic patches `get_connection` with one of these instead of
talking to a real database, so the actual query/commit/rollback code paths
are exercised without any live service.

## Unit tests (no external services required)

| File | What it covers |
|---|---|
| `test_indicators.py` | Baseline sanity checks for `analysis/indicators.py`: shifted rolling stats exclude the current observation; volume ratio uses prior observations only. |
| `test_returns.py` | `calculate_returns`: `return_t = (close_t - close_(t-1))/close_(t-1)`, no return for the first row, correct sorting by timestamp. |
| `test_moving_average.py` | `calculate_rolling_statistics`: 20-window rolling mean/std, shift(1) semantics (no look-ahead), NaN until enough history. |
| `test_volume.py` | `calculate_volume_indicators`: rolling volume average excludes the current bar; NaN until enough history. |
| `test_volume_distribution.py` | `classify_anomalies_with_volume`: `volume_ratio > 2.0` → `volume_spike`; normal ratios are not flagged. |
| `test_volume_decline.py` | `volume_ratio < 0.5` → `volume_decline`; boundary case at exactly 0.5 is NOT flagged (strict `<`). |
| `test_combined_analysis.py` | Full indicator pipeline end-to-end (no DB): large +/- returns are classified as `positive_return_spike`/`negative_return_spike`; normal moves are not flagged; **zero rolling std never produces inf/NaN** (z-score safely falls back to 0.0); price and volume anomalies are classified independently. |
| `test_analysis.py` | `analysis/run_analysis.py` with a mocked DB: stores a price anomaly, creates a completed `analysis_run`, raises `ValueError` for an unknown symbol or missing price history, rolls back nothing incorrectly. |
| `test_realtime_detector.py` | `analysis/realtime_detector.py` with a mocked DB: detects a price+volume spike given sufficient history; returns no events with insufficient history; zero historical std does not falsely flag an anomaly; volume decline detection; unknown security raises `ValueError`. |
| `test_realtime_stream.py` | `realtime/stream_processor.py` with a mocked stream client: the live WebSocket uses the market feed configured in `config.py`. |
| `test_pipeline.py` | `analysis/pipeline.py` orchestration with mocked DB + mocked collaborators: real-time method naming follows `REALTIME_WINDOW`; `analysis_run` reuse vs. creation; `process_new_bar` stores the bar, stores detected anomalies, notifies watchers, and checks alerts; no anomalies still checks alerts; `run_alert_check=False` skips alert evaluation; `process_latest_stored_bar` re-processes the latest bar or raises when none exists; `run_historical_analysis` delegates correctly. |
| `test_alert_checker.py` | `alerts/alert_checker.py` with a mocked DB: alert triggers and creates a notification; alert not triggered when condition unmet; `user_preference.price_alerts=False` suppresses it; duplicate unread alerts are suppressed, including a concurrent-insert conflict; `below` condition triggers correctly. |
| `test_anomaly_notifier.py` | `alerts/anomaly_notifier.py` with a mocked DB: only watchlist-following users with `anomaly_alerts=True` are notified; disabled preference is skipped; duplicate anomaly notifications are skipped, including a concurrent-insert conflict; no watchers means no notifications. |
| `test_api.py` | FastAPI app via `TestClient` with a mocked DB (`api.main.get_connection` patched): root/health, stock listing/prices/anomalies/summary (including timeframe filtering), watchlist CRUD, alert CRUD + validation/evaluation with an existing unread notification, notification list + mark-read, preferences get/update + validation, and processing endpoints. |
| `test_metadata_ingestion.py` (partial) | `ingestion/metadata_ingestion.py` with a mocked Alpaca trading client and mocked DB: inserts sector/company/security/exchange_security rows; skips symbols not returned by Alpaca; rolls back cleanly on a simulated DB failure. |
| `test_price_ingestion.py` (partial) | `ingestion/price_ingestion.py` with mocked Alpaca clients/bar responses and mocked DB: configured market feed is used; inserts bars for known symbols and totals them correctly; skips symbols with no matching `security` row; `--days` defaults (365 for `day`, 5 for `minute`) are applied correctly. |
| `test_alpaca.py` (partial) | `ingestion/alpaca_client.py`: missing credentials raise `ValueError` (pure unit test, no network). |

## Integration tests (require real services; auto-skip otherwise)

These tests are also present in the files above where a module has both
unit and integration coverage, and in the following dedicated files. They
never run automatically in an environment without credentials — they report
as `SKIPPED`, not failed.

| File | Precondition to actually run | What it covers |
|---|---|---|
| `test_db_connection.py` | `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` set and DB reachable | Opens a real connection, runs `SELECT 1`, and checks the `timescaledb` extension is enabled. |
| `test_alpaca.py` | `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` set | Authenticates a real `TradingClient` and calls `get_account()` (read-only; never places trades). |
| `test_assets.py` | `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` set | Confirms every symbol in `config.SYMBOLS` exists as a real Alpaca asset. |
| `test_price_data.py` | `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` set | Fetches real daily and minute bars for the configured symbols from Alpaca's market-data API (read-only, no DB writes). |
| `test_metadata_ingestion.py::test_insert_metadata_against_real_services` | DB + Alpaca credentials set | Runs `insert_metadata()` end-to-end against the real database. **Writes to the configured database.** |
| `test_price_ingestion.py::test_insert_price_data_against_real_services` | DB + Alpaca credentials set **and** `RUN_LIVE_INGESTION_TESTS=1` | Runs `insert_price_data()` end-to-end against the real database. **Writes to the configured database** — gated behind an extra explicit opt-in environment variable so it never runs accidentally alongside a normal test run. |

## Latest validation

The current workspace completed `python -m pytest -q`: **93 passed, 1
skipped**. The run included local PostgreSQL/TimescaleDB checks and read-only
Alpaca account, asset, and market-data checks. The integration test that
writes price bars remains opt-in through `RUN_LIVE_INGESTION_TESTS=1`.
