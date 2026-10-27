# Stock Anomaly Detection and Real-Time Monitoring System

A complete, end-to-end stock-market monitoring system: it ingests historical
market data from Alpaca, uses that history to establish each security's
normal statistical behaviour, evaluates new intraday observations against
that baseline to detect anomalies, evaluates independent user-defined price
alerts, and surfaces everything through a REST API and a React dashboard.

## 1. Project Objective

1. Collect and store historical stock market data (daily + minute OHLCV).
2. Use historical data to establish the normal statistical behaviour of each
   stock (rolling return and volume distributions, plus rolling average volume).
3. Receive/process recent intraday market data (Alpaca WebSocket minute bars).
4. Compare new intraday observations against the historical/rolling baseline.
5. Detect unusual price and volume movements using rolling, data-derived
   interquartile fences; numeric bounds change with recent observations.
6. Store detected anomalies with full traceability to the analysis run that
   produced them.
7. Let users define price alerts (independent of statistical anomalies).
8. Generate notifications for newly detected anomalies and triggered alerts,
   without flooding users with duplicates or historical noise.
9. Provide a REST API (FastAPI).
10. Provide a functional dashboard (React) for stocks, anomalies, alerts,
    watchlists, and notifications.

The central data flow:

```text
HISTORICAL DATA
      |
ESTABLISH NORMAL BEHAVIOR (rolling return/volume distributions)
      |
REAL-TIME / RECENT INTRADAY DATA (Alpaca minute bars)
      |
COMPARE AGAINST BASELINE (adaptive interquartile bounds)
      |
DETECT DEVIATION
      |
STORE ANOMALY (traceable to an ANALYSIS_RUN)
      |
CHECK USERS / WATCHLISTS / PREFERENCES
      |
NOTIFICATION (deduplicated)
```

### Two independent monitoring mechanisms

| | Statistical anomaly detection | User-defined price alert |
|---|---|---|
| Trigger | Current return/volume is outside its rolling data-derived bounds | Latest price crosses a fixed user-chosen target |
| Example | AAPL return is outside its latest rolling interquartile fence | "AAPL above 320" |
| Data used | Rolling distribution and volume average | Only the latest stored price |
| Table | `anomaly` (+ `notification` where `anomaly_id IS NOT NULL`) | `alert` (+ `notification` where `alert_no IS NOT NULL`) |

These are deliberately kept independent in both the schema (a `notification`
has exactly one source — see the `chk_notification_source` CHECK constraint)
and the code (`analysis/realtime_detector.py` vs. `alerts/alert_checker.py`).

## 2. Architecture

```text
                         ┌────────────────────────┐
                         │   Alpaca (IEX feed)     │
                         └───────┬─────────┬───────┘
                    historical   │         │  live minute bars
                        bars     │         │  (WebSocket, authenticated)
                                 v         v
                    ingestion/price_ingestion.py   realtime/stream_processor.py
                                 │                          │
                                 v                          v
                        ┌─────────────────────────────────────────┐
                        │      PostgreSQL + TimescaleDB            │
                        │  price_bar (hypertable), analysis_run,   │
                        │  anomaly, security, company, sector,     │
                        │  exchange, app_user, watchlist, alert,   │
                        │  notification, user_preference           │
                        └───────────────┬───────────────────────────┘
                                        │
                    analysis/run_analysis.py         analysis/pipeline.py
                    (historical daily baseline   (real-time orchestration:
                     + historical anomalies)      store bar -> recent
                                                    analysis -> anomaly ->
                                                    notify -> alert check)
                                        │
                                        v
                               alerts/alert_checker.py
                               alerts/anomaly_notifier.py
                                        │
                                        v
                              api/main.py (FastAPI)  <───── dashboard/ (React)
```

`analysis/pipeline.py` is the single orchestration module for the real-time
workflow. Both `realtime/stream_processor.py` (the live Alpaca WebSocket
consumer) and the API's manual trigger endpoints
(`POST /pipeline/process/{symbol}`) call the *same* `process_new_bar` /
`process_latest_stored_bar` functions — the real-time logic is implemented
exactly once, never duplicated inside a route handler.

## 3. Technology Stack

- **Backend:** Python, FastAPI, psycopg3, Pandas, NumPy, scikit-learn (where
  applicable), alpaca-py
- **Database:** PostgreSQL + TimescaleDB (`price_bar` is a hypertable)
- **Frontend:** React + Vite, Chart.js (via `react-chartjs-2`)
- **Data source:** Alpaca Markets, IEX feed (works with the free/basic
  market-data subscription; not a consolidated all-exchange feed — see
  Known Limitations)

## 4. Database Design

### 4.1 Entities (conceptual, target 3NF)

| Entity | Purpose |
|---|---|
| `sector` | Sector classification (e.g. Technology) |
| `company` | Issuing company, belongs to one sector |
| `exchange` | Listing exchange (name, country, timezone) |
| `security` | A tradable instrument (symbol, asset class, status), belongs to one company |
| `exchange_security` | Associative table resolving the M:N security↔exchange relationship |
| `price_bar` | OHLCV observation for a security at a timestamp+timeframe (TimescaleDB hypertable) |
| `analysis_run` | One traceable execution of an anomaly-detection method |
| `anomaly` | A detected statistical anomaly, tied to the `analysis_run` that produced it and the exact `price_bar` it evaluates |
| `app_user` | Application user (conceptually `USER`; renamed because `USER` is a PostgreSQL reserved word) |
| `watchlist` | A named list of securities owned by a user (weak entity, identified by `user_id`) |
| `watchlist_security` | Associative table resolving the M:N user-watchlist↔security relationship |
| `alert` | A user-defined price alert (weak entity, identified by `user_id`) |
| `notification` | A message delivered to a user, sourced from exactly one of `alert` or `anomaly` |
| `user_preference` | Per-user notification preferences |

### 4.2 Keys and relationships

```text
sector (1) ───< company (1) ───< security (1) ───< price_bar
                                     │  \
                                     │   \___< exchange_security >___ exchange
                                     │
                                     └───< anomaly >─── analysis_run
                                     │
                                     └───< watchlist_security >─── watchlist ─── app_user
                                     │
                                     └───< alert ─── app_user
                                              │
                                     notification ─── app_user
                                     (sourced from EITHER alert OR anomaly)
                                     │
                                     user_preference ─── app_user (1:1)
```

- `price_bar` primary key: `(security_id, timestamp, timeframe)` — a
  composite key, because the same security can have both a `day` bar and a
  `minute` bar at overlapping/derived timestamps; `timeframe` disambiguates
  them so daily and minute observations are never mixed.
- `anomaly` has a **composite foreign key** `(security_id, timestamp,
  timeframe)` referencing `price_bar`, so every anomaly is provably tied to a
  real, specific stored bar (not just "a timestamp that happens to match").
- `anomaly.analysis_id` references `analysis_run`, giving full traceability
  from any anomaly back to the method/run that produced it.
- `watchlist` and `alert` are weak entities: `watchlist_no` / `alert_no` are
  only unique *within* a given `user_id` (`PRIMARY KEY (user_id, watchlist_no)`
  / `(user_id, alert_no)`).
- `notification` has a database **CHECK constraint**
  (`chk_notification_source`) enforcing that exactly one of `alert_no` /
  `anomaly_id` is set — a notification can never have both or neither source.
- `notification` also has `UNIQUE (user_id, anomaly_id)` so a user can never
  receive two notifications for the same anomaly.

See [`sql/01_schema.sql`](sql/01_schema.sql) for the full DDL.

## 5. Historical Analysis Methodology

Implemented in [`analysis/indicators.py`](analysis/indicators.py) and
[`analysis/run_analysis.py`](analysis/run_analysis.py), run against `day`
timeframe `price_bar` rows.

1. Calculate daily returns and a rolling volume average. The default sample
   size is 20 observations (`DAILY_WINDOW`); it controls available history,
   not a fixed trigger cutoff.
2. Calculate lower and upper Tukey fences from the prior rolling sample:
   `Q1 - 1.5 × IQR` and `Q3 + 1.5 × IQR`. These numeric return bounds are
   recalculated per symbol and per day. The current day is excluded.
3. Price returns outside those bounds are classified as positive or negative
   spikes. Volume bounds are calculated from prior raw volumes and expressed
   relative to rolling average volume.
4. Warm-up observations remain unclassified until eight baseline samples
   exist (or the configured window is smaller). The 1.5 multiplier is the
   conventional Tukey-fence rule; numeric cutoffs are learned from the
   changing distribution, not preset prices or ratios.
5. Each run records the method version and each anomaly stores the actual
   dynamic bound used, preserving traceability.

## 6. Intraday / Real-Time Analysis Methodology

Implemented in [`analysis/realtime_detector.py`](analysis/realtime_detector.py)
and orchestrated by [`analysis/pipeline.py`](analysis/pipeline.py), run
against `minute` timeframe `price_bar` rows.

For every newly received minute bar:

1. Fetch the prior `REALTIME_WINDOW + 1` (default 21) minute bars for the
   same security, strictly **before** the new bar's timestamp.
2. Compute minute-over-minute returns from that prior history only.
3. Calculate data-derived Tukey fences from those prior returns (the window,
   default 20 — `config.REALTIME_WINDOW`).
4. Compute the new bar's own return relative to the immediately preceding bar.
5. Compute its volume ratio against the prior-window average and compare it
   with dynamic fences learned from prior volumes.
6. Classify returns or volume outside their current bounds and persist the
   actual bound applied with each anomaly.
7. If insufficient history exists yet (`< REALTIME_WINDOW + 1` prior bars),
   no anomaly is evaluated (returns no events, not an error). At least eight
   samples are required when the configured window permits.

The current adaptive limits are available from
`GET /stocks/{symbol}/thresholds?timeframe=day|minute`; the dashboard also
shows the current limits and baseline sample count.

This means a stock can close a normal trading day (no daily anomaly) while
still triggering one or more **intraday** anomalies mid-session — the minute
bars are preserved and evaluated independently of the daily close.

### Time-of-day normalization: NOT implemented in this version

The current intraday baseline is a **pure rolling-minute baseline** (the
previous *N* minute bars, wherever they fall in the trading day) — it does
**not** compare "10:00 volume" specifically against historical 10:00 volumes.
This is explicitly called out here so it is not mistaken for a
time-of-day-aware baseline. The architecture supports adding this later
without a rewrite: `analysis/realtime_detector.py` already isolates baseline
retrieval behind `evaluate_current_bar`, so a time-of-day-bucketed baseline
query could be swapped in there without touching `analysis/pipeline.py`,
`realtime/stream_processor.py`, or the API.

### Real-time orchestration and ANALYSIS_RUN reuse

Because real-time monitoring is continuous (not a single batch job), the
real-time pipeline keeps **one open `analysis_run`** per security, using a
method name whose suffix follows `config.REALTIME_WINDOW`, and reuses that run
across incoming bars (`analysis.pipeline.get_or_create_open_analysis_run`)
instead of creating a new run per bar. Every stored real-time anomaly still carries a
valid `analysis_id`. This also means restarting the stream processor does not
create uncontrolled duplicate historical-style analysis rows — it re-attaches
to the still-open run (or opens a new one if none is running).

## 7. Price Alert Logic

Implemented in [`alerts/alert_checker.py`](alerts/alert_checker.py) —
entirely independent of the anomaly detector.

1. Load all `alert` rows with `status = 'active'`.
2. For each, fetch the security's most recently stored `price_bar` (any
   timeframe).
3. Evaluate: `condition = 'above'` → `current_price > target_price`;
   `condition = 'below'` → `current_price < target_price`.
4. If triggered, check `user_preference.price_alerts`; skip if disabled.
5. **Duplicate protection:** an alert may have at most one **unread**
   notification at a time. If an unread notification already exists for
   `(user_id, alert_no)`, no new one is created — this is what prevents
   hundreds of identical notifications while the price stays past the
   target across repeated `check_all_active_alerts()` calls. Once the user
   marks the notification read, the alert becomes eligible to fire again.
6. `check_all_active_alerts()` is invoked automatically after every
   processed real-time bar (via `analysis/pipeline.py`) and can also be
   triggered manually via `POST /alerts/check`.

## 8. Notification Logic

Implemented in [`alerts/anomaly_notifier.py`](alerts/anomaly_notifier.py)
(anomaly side) and `alerts/alert_checker.py` (price-alert side).

- **Anomaly notifications** are only sent to users who watch the affected
  security through a `watchlist_security` row (i.e. relevant subscribers
  only — never a global broadcast), and only if
  `user_preference.anomaly_alerts` is enabled.
- **Deduplication:** `UNIQUE (user_id, anomaly_id)` in the `notification`
  table plus an application-level existence check means a user is notified
  at most once per anomaly, ever.
- **Historical vs. real-time separation:** historical batch analysis
  (`analysis/run_analysis.py`) stores anomalies for dashboard/analysis use
  but **does not** call the notifier. Only the real-time pipeline
  (`analysis/pipeline.py::process_new_bar`) calls
  `notify_users_for_realtime_anomaly`, so re-running historical analysis
  never floods users with old anomalies.
- `notification_mode = 'email'` is accepted as a stored preference value
  only. **No email is actually sent** — this project intentionally keeps
  delivery in-app; `email` is a configuration placeholder for future
  integration, and this is not misrepresented as working email delivery
  anywhere in the code or docs.

## 9. API Documentation

Base URL (default): `http://127.0.0.1:8000`. Interactive docs at `/docs`
(Swagger UI) once the API is running.

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Liveness message |
| GET | `/health` | DB connectivity check (no credentials returned) |
| GET | `/automation/status` | Background refresh, stream, and alert-check status |
| GET | `/stocks` | List all securities |
| GET | `/stocks/{symbol}/prices?timeframe=day\|minute&limit=` | OHLCV history |
| GET | `/stocks/{symbol}/anomalies?timeframe=day\|minute&limit=` | Anomalies for a security and timeframe, newest first (omit timeframe for both) |
| GET | `/stocks/{symbol}/summary` | Latest price + anomaly counts |
| GET | `/stocks/{symbol}/thresholds?timeframe=day\|minute` | Current adaptive bounds and baseline sample size |
| GET | `/users/{user_id}/watchlists` | List a user's watchlists + members |
| POST | `/users/{user_id}/watchlists` | Create a watchlist (`{name}`) |
| POST | `/users/{user_id}/watchlists/{watchlist_no}/stocks` | Add a security (`{symbol}`) |
| DELETE | `/users/{user_id}/watchlists/{watchlist_no}/stocks/{symbol}` | Remove a security |
| DELETE | `/users/{user_id}/watchlists/{watchlist_no}` | Delete a watchlist |
| GET | `/users/{user_id}/alerts` | List a user's alerts |
| POST | `/users/{user_id}/alerts` | Create an alert (`{symbol, condition, target_price}`) |
| DELETE | `/users/{user_id}/alerts/{alert_no}` | Delete an alert |
| GET | `/users/{user_id}/alerts/{alert_no}/evaluate` | Evaluate one alert now |
| GET | `/users/{user_id}/notifications` | List a user's notifications |
| PATCH | `/users/{user_id}/notifications/{notification_id}/read` | Mark as read |
| GET | `/users/{user_id}/preferences` | Get notification preferences |
| PUT | `/users/{user_id}/preferences` | Update notification preferences |
| POST | `/alerts/check` | Manually evaluate all active alerts |
| POST | `/analysis/run/{symbol}` | Run historical daily analysis for one symbol |
| POST | `/analysis/run` | Run historical daily analysis for all configured symbols |
| POST | `/pipeline/process/{symbol}?timeframe=minute\|day` | Re-run the real-time pipeline against the latest stored bar (demo/manual trigger; same code path as the live stream) |

No endpoint returns database credentials, connection strings, or API keys.

## 10. Dashboard Documentation

React + Vite single-page app in [`dashboard/`](dashboard/), talking to the
FastAPI backend over `fetch` (see `dashboard/src/api/client.js`).

- **Monitoring tab:** stock overview tiles (symbol, company, latest price,
  latest timestamp, anomaly badge), a price chart (historical or intraday,
  selectable) with anomaly markers from the selected timeframe, a volume
  chart, and a recent-anomalies table (newest first). Includes manual trigger buttons: "Run historical
  analysis", "Process latest bar" (real-time pipeline demo), "Check alerts".
- **Watchlists tab:** create/delete watchlists and add/remove securities. Each
  list doubles as a focused market monitor, showing each member's latest
  stored price and timestamp, recorded anomaly count, and active price alerts.
  The Monitor action opens that symbol in the Monitoring tab; values refresh
  with the dashboard's 15-second polling cycle.
- **Price Alerts tab:** create/delete alerts, evaluate on demand, see
  active/inactive status.
- **Notifications tab:** anomaly + price-alert notifications, mark as read.
- **Preferences tab:** toggle price/anomaly alerts, choose notification mode.
- **Real-time-ish updates:** the whole dashboard polls the API every 15s
  (`REFRESH_INTERVAL_MS` in `App.jsx`) so new bars/anomalies/notifications
  produced by the live stream processor appear without a manual reload. This
  is polling, not a WebSocket push — documented here rather than
  overstated as true push-based real-time.

## 11. Installation

```powershell
git clone <this-repository>
cd stock-anomaly-detection
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt   # only needed to run tests
```

## 12. Environment Configuration

Copy `.env.example` to `.env` and fill in real values. Never commit `.env`.

```text
DB_HOST=localhost
DB_PORT=5432
DB_NAME=stock_anomaly_db
DB_USER=postgres
DB_PASSWORD=<your postgres password>

ALPACA_API_KEY=<your alpaca api key>
ALPACA_SECRET_KEY=<your alpaca secret key>

AUTO_MONITORING_ENABLED=true
AUTO_ALERT_CHECK_SECONDS=60
AUTO_DATA_REFRESH_SECONDS=21600
AUTO_DAILY_REFRESH_DAYS=5
AUTO_MINUTE_REFRESH_DAYS=1

# Dashboard sign-in cookies and permitted browser origins.
AUTH_COOKIE_SECURE=false
DASHBOARD_ORIGINS=http://127.0.0.1:5173,http://localhost:5173
```

For the dashboard, copy `dashboard/.env.example` to `dashboard/.env` if the
API is not running at the default `http://127.0.0.1:8000`.

## 13. Database Setup

1. Create an empty PostgreSQL database (name must match `DB_NAME`), with the
   TimescaleDB extension available on the server.
2. **Fresh install — required:** run [`sql/01_schema.sql`](sql/01_schema.sql).
   This creates all tables, enables `timescaledb`, and converts `price_bar`
   into a hypertable.
3. **Upgrading an existing database from the earlier single-timeframe schema
   only:** run [`sql/02_migrate_existing_database.sql`](sql/02_migrate_existing_database.sql)
   **instead of** step 2. It safely migrates `price_bar`'s primary key from
   `(security_id, timestamp)` to `(security_id, timestamp, timeframe)`
   without dropping existing data. **Never run both 01 and 02 against the
   same database.**
4. Run [`sql/04_notification_deduplication.sql`](sql/04_notification_deduplication.sql)
   on an existing installation to enforce one unread price-alert notification
   per alert, including when multiple workers check alerts simultaneously.
   Fresh databases created with `01_schema.sql` already have this constraint.
5. **Optional:** run [`sql/03_optional_demo_data.sql`](sql/03_optional_demo_data.sql)
   to create a demo user/watchlist for API/dashboard testing. Not required
   for ingestion or anomaly detection.
6. Apply [`sql/05_user_authentication.sql`](sql/05_user_authentication.sql)
   after the base schema to add password sign-in and server-side sessions.

## 14. Historical Ingestion

```powershell
python -m ingestion.metadata_ingestion
python -m ingestion.price_ingestion --timeframe day --days 365
python -m ingestion.price_ingestion --timeframe minute --days 5
python -m analysis.run_analysis
```

Symbols are configured in [`config.py`](config.py) (`SYMBOLS`). Sector data
is **not** provided by Alpaca; it is a manually configured mapping in
`ingestion/metadata_ingestion.py::COMPANY_METADATA`, and is documented as
such rather than presented as Alpaca-sourced data.

## 15. Real-Time Processing

```powershell
python -m realtime.stream_processor
```

Connects to Alpaca's authenticated IEX stock WebSocket, subscribes to minute
bars for the configured symbols, and for every bar: stores it, runs the
recent-anomaly detector, stores any anomalies, notifies watching users, and
evaluates active price alerts. Requires Alpaca market hours / an active
subscription actually publishing bars to see live activity; you can exercise
the exact same code path anytime via `POST /pipeline/process/{symbol}`
against the most recently stored bar (see the Dashboard's "Process latest
bar" button).

## 16. Running the API

```powershell
uvicorn api.main:app --reload
```

With `AUTO_MONITORING_ENABLED=true` (default), the API starts one background
owner using a PostgreSQL advisory lock. It checks price alerts every minute,
refreshes recent daily and minute bars every six hours, reruns daily analysis,
and starts the Alpaca minute stream when credentials are available. Other API
workers report that automation is managed by the lock owner. Temporary
database startup failures are retried every 30 seconds; a disconnected or
failed Alpaca stream reconnects automatically with a capped backoff. Inspect
`GET /automation/status` (also shown in the dashboard status bar) for last
completed work and recent errors. Set
`AUTO_MONITORING_ENABLED=false` to disable managed workers and run manual
commands instead.

Swagger UI: `http://127.0.0.1:8000/docs`

## 17. Running the Dashboard

```powershell
cd dashboard
npm install
npm run dev
```

Open the printed local URL (default `http://localhost:5173`). The API must
be running and reachable at `VITE_API_BASE_URL` (default
`http://127.0.0.1:8000`).

### Sign-in and My Data Queries

The dashboard supports account registration and password sign-in. Existing
accounts created before authentication was added have no password hash and
need credentials provisioned before they can sign in. The **My Data Queries**
tab offers a guided builder for `app_user`, `watchlist`, `watchlist_security`,
`alert`, `notification`, and `user_preference`. It displays a read-only SQL
preview but accepts no SQL text. Values are bound separately, and the API
enforces ownership from the session, an allowlist of columns/actions, a
100-row limit, and a three-second query timeout. Notification messages,
session tokens, and password hashes are not exposed by the builder.
For HTTPS deployments, set `AUTH_COOKIE_SECURE=true` and configure
`DASHBOARD_ORIGINS` to the exact frontend origin(s).

For temporary collaborator development, the API can remain on the owner's
computer while a Cloudflare Quick Tunnel exposes port 8000. On the owner's
computer, run `cloudflared tunnel --url http://127.0.0.1:8000` and share the
temporary URL with the collaborator. In their `dashboard/.env.local`, set
`API_PROXY_TARGET` to that URL and leave `VITE_API_BASE_URL` blank, then
restart Vite. The Vite proxy keeps browser requests same-origin so the current
session cookie policy continues to work. Quick Tunnels are temporary; anyone
with the URL can reach the API, so use this only for trusted development and
stop the tunnel when finished.

## 18. Running Tests

```powershell
pip install -r requirements-dev.txt
pytest -m "not integration"        # unit tests only — no DB/Alpaca required
pytest                              # everything; integration tests will
                                     # skip automatically if DB_*/ALPACA_*
                                     # environment variables are not set
```

See [`TEST_GUIDE.md`](TEST_GUIDE.md) for a description of every test file.

## 19. Known Limitations

- **IEX feed, not consolidated SIP data.** Alpaca's free/basic market-data
  subscription only provides the IEX feed. This project is therefore an
  IEX-feed prototype, not a full-market consolidated feed. `config.py` sets
  `DATA_FEED = "iex"` explicitly.
- **No time-of-day normalization yet.** The intraday baseline is a rolling
  window of the most recent N minute bars, not a "same time yesterday"
  baseline. See section 6 for why and how this can be added later.
- **Real-time "push" is polling in the dashboard.** The dashboard refreshes
  via periodic polling (every 15s), not a WebSocket subscription from
  browser to backend. The backend-to-Alpaca connection *is* a genuine
  authenticated WebSocket stream.
- **Email notifications are not implemented.** `notification_mode='email'`
  is stored as a preference value only; no email is actually sent by this
  system.
- **Sector data is a manual mapping**, not sourced from Alpaca (Alpaca's
  asset endpoint does not provide sector classification).
- **Existing accounts need credential provisioning.** Accounts from before
  password sign-in was added have a NULL password hash; register a new account
  or provision credentials for existing accounts before sign-in.
- **Recommended next analysis improvement: time-of-day volume normalization.**
  Minute volume has strong intraday patterns, so compare each minute with the
  same time-of-day across prior sessions before treating adaptive rolling
  volume bounds as a production trading signal.
- **Historical analysis re-runs are idempotent per run** (anomalies are
  keyed by `(analysis_id, security_id, timestamp, timeframe, anomaly_type)`),
  but running `analysis/run_analysis.py` twice will create two distinct
  `analysis_run` rows (by design, for traceability of each execution) even
  if the underlying anomalies are unchanged.
- **Integration checks may perform read-only external calls.** The default
  `pytest` run reads `.env` and exercises configured PostgreSQL/Alpaca
  connections; metadata-ingestion integration coverage upserts metadata.
  The live price-ingestion integration test requires the additional
  `RUN_LIVE_INGESTION_TESTS=1` opt-in because it writes market bars.
