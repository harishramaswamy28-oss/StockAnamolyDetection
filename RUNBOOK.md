# RUNBOOK

Exact order to bring the whole system up from a clean checkout. Run each
step from the project root unless stated otherwise.

## 0. Prerequisites

- PostgreSQL server reachable, with TimescaleDB extension installed on the
  server (not necessarily enabled in the target DB yet — the schema script
  does that).
- Python 3.10+ and Node.js 18+ available.
- An Alpaca account (paper or live) with API key/secret for market data.

## 1. Create the database

```sql
CREATE DATABASE stock_anomaly_db;
```

(Use whatever name you put in `.env` as `DB_NAME`.)

## 2. Configure credentials

```powershell
copy .env.example .env
notepad .env
```

Fill in `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`,
`ALPACA_API_KEY`, `ALPACA_SECRET_KEY`. Never commit this file.

Before running the `psql` commands below in PowerShell, load the database
settings from `.env` into the current terminal session:

```powershell
Get-Content .env | Where-Object { $_ -match '^DB_(HOST|PORT|NAME|USER|PASSWORD)=' } | ForEach-Object {
    $key, $value = $_ -split '=', 2
    Set-Item -Path "Env:$key" -Value $value
}
$env:PGPASSWORD = $env:DB_PASSWORD
```

## 3. Install backend dependencies

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## 4. Apply the database schema

Choose ONE:

- **Fresh database (required for a new setup):**
  ```powershell
  psql -h $env:DB_HOST -U $env:DB_USER -d $env:DB_NAME -f sql\01_schema.sql
  ```
- **Existing database from the earlier single-timeframe schema (instead of
  the step above):**
  ```powershell
  psql -h $env:DB_HOST -U $env:DB_USER -d $env:DB_NAME -f sql\02_migrate_existing_database.sql
  ```

Optional, any time after step 4:

```powershell
psql -h $env:DB_HOST -U $env:DB_USER -d $env:DB_NAME -f sql\03_optional_demo_data.sql
```

For an existing installation, also apply the idempotent notification
deduplication hardening migration:

```powershell
psql -h $env:DB_HOST -U $env:DB_USER -d $env:DB_NAME -f sql\04_notification_deduplication.sql
```

## 5. Load metadata (companies, sectors, exchanges, securities)

```powershell
python -m ingestion.metadata_ingestion
```

## 6. Load historical price data

```powershell
python -m ingestion.price_ingestion --timeframe day --days 365
python -m ingestion.price_ingestion --timeframe minute --days 5
```

## 7. Run historical analysis (establishes/records the historical baseline anomalies)

```powershell
python -m analysis.run_analysis
```

## 8. Start the API

In a dedicated terminal (keep running):

```powershell
venv\Scripts\activate
uvicorn api.main:app --reload
```

Verify: open `http://127.0.0.1:8000/health` — expect `{"status":"healthy", ...}`.

## 9. Automatic monitoring

With `AUTO_MONITORING_ENABLED=true` (default), the API owns the real-time
stream, scheduled recent-data refresh, daily analysis, and recurring price
alert checks. Check `http://127.0.0.1:8000/automation/status` for worker state.
The market stream needs Alpaca credentials and active market data. The API
will still refresh history and check alerts if the live stream is unavailable.
If Postgres is still starting, ownership acquisition retries every 30 seconds.
If the Alpaca connection ends, the stream worker reconnects with an increasing
delay capped at 60 seconds. Status includes the stream state, last refresh,
last analysis, last alert check, and the latest worker error.
To run a separate stream worker, disable API-managed automation first and
then run `python -m realtime.stream_processor`.

## 10. (Optional) Manually exercise the real-time pipeline on demand

```powershell
curl -X POST http://127.0.0.1:8000/pipeline/process/AAPL
curl -X POST http://127.0.0.1:8000/alerts/check
```

## 11. Start the dashboard

In a third dedicated terminal:

```powershell
cd dashboard
copy .env.example .env        REM only if the API is not at the default URL
npm install
npm run dev
```

Open the printed URL (default `http://localhost:5173`).

## 12. Create a user, watchlist, and alert (if you did not run the optional demo data script)

Use the dashboard UI, or:

```powershell
curl -X POST http://127.0.0.1:8000/users/1/watchlists -H "Content-Type: application/json" -d "{\"name\":\"Tech\"}"
curl -X POST http://127.0.0.1:8000/users/1/watchlists/1/stocks -H "Content-Type: application/json" -d "{\"symbol\":\"AAPL\"}"
curl -X POST http://127.0.0.1:8000/users/1/alerts -H "Content-Type: application/json" -d "{\"symbol\":\"AAPL\",\"condition\":\"above\",\"target_price\":100}"
```

(Note: `app_user` rows are not created by the API; insert one directly via
SQL or via `sql/03_optional_demo_data.sql` before creating watchlists/alerts
for that user.)

## Shutdown order

1. Stop the dashboard (`Ctrl+C` in its terminal).
2. Stop the real-time stream processor (`Ctrl+C`; it closes its open
   `analysis_run` rows cleanly on the way out).
3. Stop the API (`Ctrl+C`).
4. Leave PostgreSQL running, or stop it via your OS/service manager.

## Re-running after the first setup

Steps 5–7 (metadata, historical ingestion, historical analysis) can be
re-run at any time to refresh historical data; they are idempotent for
metadata/prices (upserted) and additive-but-deduplicated for anomalies
(each run creates a new traceable `analysis_run`, but duplicate anomaly rows
within a run are prevented by a unique constraint). Steps 8–11 are simply
restarted as needed.
