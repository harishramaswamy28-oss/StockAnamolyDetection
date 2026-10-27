from contextlib import asynccontextmanager
import os
import re

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import psycopg

from api.auth import (
    SESSION_COOKIE,
    SESSION_DAYS,
    get_current_user,
    hash_password,
    issue_session,
    require_matching_user,
    revoke_session,
    verify_password,
)
from api.user_query_builder import router as user_query_builder_router
from alerts.alert_checker import check_all_active_alerts
from analysis.pipeline import process_latest_stored_bar, run_historical_analysis
from analysis.thresholds import get_threshold_snapshot
from config import SYMBOLS
from database.connection import get_connection
from realtime.automation import MarketAutomation

automation = MarketAutomation()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await automation.start()
    try:
        yield
    finally:
        await automation.stop()

app = FastAPI(
    title="Stock Anomaly Detection API",
    description="Historical and real-time stock anomaly detection, price alerts and notifications",
    version="2.0.0",
    lifespan=lifespan,
)

# The dashboard sends HTTP-only session cookies from a separate browser origin.
# Keep credentialed CORS restricted to explicitly configured dashboard origins.
allowed_dashboard_origins = [
    origin.strip()
    for origin in os.getenv(
        "DASHBOARD_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_dashboard_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(user_query_builder_router)


class WatchlistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class WatchlistStockAdd(BaseModel):
    symbol: str


class AlertCreate(BaseModel):
    symbol: str
    condition: str
    target_price: float = Field(gt=0, allow_inf_nan=False)


class UserPreferenceUpdate(BaseModel):
    price_alerts: bool
    anomaly_alerts: bool
    notification_mode: str


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=12, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


def set_session_cookie(response: Response, token: str):
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=os.getenv("AUTH_COOKIE_SECURE", "false").lower() in {"1", "true", "yes"},
        samesite="lax",
        path="/",
    )


@app.post("/auth/register")
def register_account(data: RegisterRequest, response: Response):
    name = data.name.strip()
    email = data.email.strip().lower()
    if not name or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(status_code=422, detail="Enter a name and valid email address.")
    if len(name) > 200:
        raise HTTPException(status_code=422, detail="Name must be 200 characters or fewer.")
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO app_user(name,email,password_hash) VALUES (%s,%s,%s) RETURNING user_id,name,email",
                    (name, email, hash_password(data.password)),
                )
                user = cursor.fetchone()
                cursor.execute(
                    "INSERT INTO user_preference(user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING",
                    (user[0],),
                )
            connection.commit()
    except psycopg.errors.UniqueViolation:
        raise HTTPException(status_code=409, detail="An account with that email already exists.") from None
    set_session_cookie(response, issue_session(user[0]))
    return {"user_id": user[0], "name": user[1], "email": user[2]}


@app.post("/auth/login")
def login_account(data: LoginRequest, response: Response):
    email = data.email.strip().lower()
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT user_id,name,email,password_hash FROM app_user WHERE lower(email)=%s", (email,))
            user = cursor.fetchone()
    if user is None or not verify_password(data.password, user[3]):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    set_session_cookie(response, issue_session(user[0]))
    return {"user_id": user[0], "name": user[1], "email": user[2]}


@app.post("/auth/logout")
def logout_account(request: Request, response: Response):
    revoke_session(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax")
    return {"message": "Signed out."}


@app.get("/auth/me")
def get_account(current_user=Depends(get_current_user)):
    return current_user


def api_error(message: str, status_code: int = 400):
    """Return a consistent JSON error body with an appropriate HTTP status."""
    return JSONResponse(status_code=status_code, content={"error": message})


@app.get("/")
def root():
    return {"message": "Stock Anomaly Detection API is running"}


@app.get("/health")
def health():
    connection = None
    try:
        connection = get_connection()
        return {"status": "healthy", "database": "connected", "automation": automation.status()}
    except Exception as exc:
        return {"status": "unhealthy", "database": "disconnected", "automation": automation.status()}
    finally:
        if connection is not None:
            connection.close()


@app.get("/automation/status")
def get_automation_status():
    return automation.status()


@app.get("/stocks")
def get_stocks():
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT security_id, symbol, name, asset_class, status, company_id
                FROM security ORDER BY symbol
                """
            )
            return [
                {"security_id": r[0], "symbol": r[1], "name": r[2],
                 "asset_class": r[3], "status": r[4], "company_id": r[5]}
                for r in cursor.fetchall()
            ]


@app.get("/stocks/{symbol}/prices")
def get_stock_prices(symbol: str, timeframe: str = "day", limit: int = 500):
    if timeframe not in {"day", "minute"}:
        return api_error("timeframe must be day or minute", 422)
    limit = max(1, min(limit, 5000))
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT pb.timestamp, pb.open, pb.high, pb.low, pb.close,
                       pb.volume, pb.trade_count, pb.vwap
                FROM price_bar pb
                JOIN security s ON s.security_id = pb.security_id
                WHERE s.symbol = %s AND pb.timeframe = %s
                ORDER BY pb.timestamp DESC
                LIMIT %s
                """,
                (symbol.upper(), timeframe, limit),
            )
            rows = list(reversed(cursor.fetchall()))
            return [
                {"timestamp": r[0], "open": float(r[1]), "high": float(r[2]),
                 "low": float(r[3]), "close": float(r[4]), "volume": r[5],
                 "trade_count": r[6], "vwap": float(r[7]) if r[7] is not None else None}
                for r in rows
            ]


@app.get("/stocks/{symbol}/anomalies")
def get_stock_anomalies(symbol: str, limit: int = 200, timeframe: str | None = None):
    if timeframe is not None and timeframe not in {"day", "minute"}:
        return api_error("timeframe must be day or minute", 422)

    query = """
        SELECT s.symbol, a.anomaly_id, a.timestamp, a.anomaly_type,
               a.anomaly_score, a.threshold, a.analysis_id
        FROM anomaly a
        JOIN security s ON s.security_id = a.security_id
        WHERE s.symbol = %s
    """
    params = [symbol.upper()]
    if timeframe is not None:
        query += " AND a.timeframe = %s"
        params.append(timeframe)
    query += " ORDER BY a.timestamp DESC LIMIT %s"
    params.append(max(1, min(limit, 2000)))

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, tuple(params))
            return [
                {"symbol": r[0], "anomaly_id": r[1], "timestamp": r[2],
                 "anomaly_type": r[3], "anomaly_score": float(r[4]),
                 "threshold": float(r[5]), "analysis_id": r[6]}
                for r in cursor.fetchall()
            ]


@app.get("/stocks/{symbol}/summary")
def get_stock_summary(symbol: str):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT s.security_id, s.symbol, c.name
                FROM security s JOIN company c ON c.company_id = s.company_id
                WHERE s.symbol = %s
                """,
                (symbol.upper(),),
            )
            stock = cursor.fetchone()
            if stock is None:
                return api_error(f"Stock not found: {symbol.upper()}", 404)
            cursor.execute(
                """
                SELECT timestamp, close FROM price_bar
                WHERE security_id = %s ORDER BY timestamp DESC LIMIT 1
                """,
                (stock[0],),
            )
            latest = cursor.fetchone()
            cursor.execute(
                """
                SELECT COUNT(*) FILTER (WHERE anomaly_type LIKE '%%return%%') AS price,
                       COUNT(*) FILTER (WHERE anomaly_type LIKE '%%volume_spike%%') AS spikes,
                       COUNT(*) FILTER (WHERE anomaly_type LIKE '%%volume_decline%%') AS declines,
                       COUNT(*) AS total
                FROM anomaly WHERE security_id = %s
                """,
                (stock[0],),
            )
            counts = cursor.fetchone()
            return {
                "symbol": stock[1], "company": stock[2],
                "latest_price": float(latest[1]) if latest else None,
                "latest_timestamp": latest[0] if latest else None,
                "price_anomalies": counts[0], "volume_spikes": counts[1],
                "volume_declines": counts[2], "total_anomalies": counts[3],
            }


@app.get("/stocks/{symbol}/thresholds")
def get_stock_thresholds(symbol: str, timeframe: str = "day"):
    try:
        return get_threshold_snapshot(symbol, timeframe)
    except ValueError as exc:
        return api_error(str(exc), 404 if "not found" in str(exc).lower() else 422)


@app.get("/users/{user_id}/watchlists")
def get_user_watchlists(user_id: int, current_user=Depends(require_matching_user)):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT w.watchlist_no, w.name, s.security_id, s.symbol, s.name
                FROM watchlist w
                LEFT JOIN watchlist_security ws
                  ON ws.user_id = w.user_id AND ws.watchlist_no = w.watchlist_no
                LEFT JOIN security s ON s.security_id = ws.security_id
                WHERE w.user_id = %s ORDER BY w.watchlist_no, s.symbol
                """,
                (user_id,),
            )
            result = {}
            for no, name, sid, symbol, secname in cursor.fetchall():
                result.setdefault(no, {"watchlist_no": no, "name": name, "stocks": []})
                if sid is not None:
                    result[no]["stocks"].append({"security_id": sid, "symbol": symbol, "name": secname})
            return list(result.values())


@app.post("/users/{user_id}/watchlists")
def create_watchlist(user_id: int, watchlist: WatchlistCreate, current_user=Depends(require_matching_user)):
    name = watchlist.name.strip()
    if not name:
        return api_error("name must not be blank", 422)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM app_user WHERE user_id = %s", (user_id,))
            if cursor.fetchone() is None:
                return api_error(f"User not found: {user_id}", 404)
            cursor.execute("SELECT COALESCE(MAX(watchlist_no), 0) + 1 FROM watchlist WHERE user_id = %s", (user_id,))
            no = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO watchlist(user_id, watchlist_no, name) VALUES (%s, %s, %s)",
                (user_id, no, name),
            )
        connection.commit()
        return {"user_id": user_id, "watchlist_no": no, "name": name, "stocks": []}


@app.post("/users/{user_id}/watchlists/{watchlist_no}/stocks")
def add_stock_to_watchlist(user_id: int, watchlist_no: int, stock: WatchlistStockAdd, current_user=Depends(require_matching_user)):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM watchlist WHERE user_id = %s AND watchlist_no = %s", (user_id, watchlist_no))
            if cursor.fetchone() is None:
                return api_error("Watchlist not found", 404)
            cursor.execute("SELECT security_id, symbol, name FROM security WHERE symbol = %s", (stock.symbol.upper(),))
            security = cursor.fetchone()
            if security is None:
                return api_error(f"Stock not found: {stock.symbol.upper()}", 404)
            cursor.execute(
                """
                INSERT INTO watchlist_security(user_id, watchlist_no, security_id)
                VALUES (%s, %s, %s) ON CONFLICT DO NOTHING
                """,
                (user_id, watchlist_no, security[0]),
            )
        connection.commit()
        return {"message": "Stock added to watchlist", "user_id": user_id,
                "watchlist_no": watchlist_no,
                "stock": {"security_id": security[0], "symbol": security[1], "name": security[2]}}


@app.delete("/users/{user_id}/watchlists/{watchlist_no}/stocks/{symbol}")
def remove_stock_from_watchlist(user_id: int, watchlist_no: int, symbol: str, current_user=Depends(require_matching_user)):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT security_id FROM security WHERE symbol = %s", (symbol.upper(),))
            security = cursor.fetchone()
            if security is None:
                return api_error(f"Stock not found: {symbol.upper()}", 404)
            cursor.execute(
                """
                DELETE FROM watchlist_security
                WHERE user_id = %s AND watchlist_no = %s AND security_id = %s
                RETURNING security_id
                """,
                (user_id, watchlist_no, security[0]),
            )
            if cursor.fetchone() is None:
                return api_error(f"{symbol.upper()} is not in the watchlist", 404)
        connection.commit()
        return {"message": "Stock removed from watchlist"}


@app.delete("/users/{user_id}/watchlists/{watchlist_no}")
def delete_watchlist(user_id: int, watchlist_no: int, current_user=Depends(require_matching_user)):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM watchlist WHERE user_id = %s AND watchlist_no = %s RETURNING name", (user_id, watchlist_no))
            row = cursor.fetchone()
            if row is None:
                return api_error("Watchlist not found", 404)
        connection.commit()
        return {"message": "Watchlist deleted successfully", "name": row[0]}


@app.get("/users/{user_id}/alerts")
def get_user_alerts(user_id: int, current_user=Depends(require_matching_user)):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT a.alert_no, a.security_id, s.symbol, s.name,
                       a.condition, a.target_price, a.status
                FROM alert a JOIN security s ON s.security_id = a.security_id
                WHERE a.user_id = %s ORDER BY a.alert_no
                """,
                (user_id,),
            )
            return [
                {"alert_no": r[0], "security_id": r[1], "symbol": r[2], "stock_name": r[3],
                 "condition": r[4], "target_price": float(r[5]), "status": r[6]}
                for r in cursor.fetchall()
            ]


@app.post("/users/{user_id}/alerts")
def create_alert(user_id: int, alert: AlertCreate, current_user=Depends(require_matching_user)):
    if alert.condition not in {"above", "below"}:
        return api_error("condition must be 'above' or 'below'", 422)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM app_user WHERE user_id = %s", (user_id,))
            if cursor.fetchone() is None:
                return api_error(f"User not found: {user_id}", 404)
            cursor.execute("SELECT security_id, symbol FROM security WHERE symbol = %s", (alert.symbol.upper(),))
            security = cursor.fetchone()
            if security is None:
                return api_error(f"Stock not found: {alert.symbol.upper()}", 404)
            cursor.execute("SELECT COALESCE(MAX(alert_no), 0) + 1 FROM alert WHERE user_id = %s", (user_id,))
            no = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO alert(user_id, alert_no, security_id, condition, target_price, status)
                VALUES (%s, %s, %s, %s, %s, 'active')
                """,
                (user_id, no, security[0], alert.condition, alert.target_price),
            )
        connection.commit()
        return {"user_id": user_id, "alert_no": no, "symbol": security[1],
                "condition": alert.condition, "target_price": alert.target_price, "status": "active"}


@app.delete("/users/{user_id}/alerts/{alert_no}")
def delete_alert(user_id: int, alert_no: int, current_user=Depends(require_matching_user)):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM alert WHERE user_id = %s AND alert_no = %s RETURNING alert_no", (user_id, alert_no))
            if cursor.fetchone() is None:
                return api_error("Alert not found", 404)
        connection.commit()
        return {"message": "Alert deleted successfully"}


@app.get("/users/{user_id}/alerts/{alert_no}/evaluate")
def evaluate_alert(user_id: int, alert_no: int, current_user=Depends(require_matching_user)):
    result = check_all_active_alerts(user_id=user_id, alert_no=alert_no)
    for notification in result["notifications"]:
        if notification["user_id"] == user_id and notification["alert_no"] == alert_no:
            return {"triggered": True, "notification_created": True, **notification}
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT a.condition, a.target_price, s.symbol, pb.timestamp, pb.close,
                       a.status, n.notification_id
                FROM alert a JOIN security s ON s.security_id = a.security_id
                LEFT JOIN LATERAL (
                    SELECT timestamp, close FROM price_bar
                    WHERE security_id = a.security_id ORDER BY timestamp DESC LIMIT 1
                ) pb ON TRUE
                LEFT JOIN LATERAL (
                    SELECT notification_id
                    FROM notification
                    WHERE user_id = a.user_id AND alert_no = a.alert_no AND status = 'unread'
                    ORDER BY created_at DESC LIMIT 1
                ) n ON TRUE
                WHERE a.user_id = %s AND a.alert_no = %s
                """,
                (user_id, alert_no),
            )
            row = cursor.fetchone()
            if row is None:
                return api_error("Alert not found", 404)
            current_price = float(row[4]) if row[4] is not None else None
            triggered = row[5] == "active" and current_price is not None and (
                current_price > float(row[1]) if row[0] == "above"
                else current_price < float(row[1]) if row[0] == "below"
                else False
            )
            return {"triggered": triggered, "notification_created": False,
                    "symbol": row[2], "condition": row[0], "target_price": float(row[1]),
                    "current_price": current_price, "timestamp": row[3],
                    "notification_id": row[6]}


@app.get("/users/{user_id}/notifications")
def get_user_notifications(user_id: int, current_user=Depends(require_matching_user)):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT n.notification_id, n.alert_no, n.anomaly_id,
                       COALESCE(s1.symbol, s2.symbol) AS symbol,
                       n.message, n.created_at, n.status,
                       CASE WHEN n.anomaly_id IS NULL THEN 'price_alert' ELSE 'anomaly' END AS source
                FROM notification n
                LEFT JOIN alert a ON a.user_id = n.user_id AND a.alert_no = n.alert_no
                LEFT JOIN security s1 ON s1.security_id = a.security_id
                LEFT JOIN anomaly an ON an.anomaly_id = n.anomaly_id
                LEFT JOIN security s2 ON s2.security_id = an.security_id
                WHERE n.user_id = %s
                ORDER BY n.created_at DESC
                """,
                (user_id,),
            )
            return [
                {"notification_id": r[0], "alert_no": r[1], "anomaly_id": r[2],
                 "symbol": r[3], "message": r[4], "created_at": r[5],
                 "status": r[6], "source": r[7]}
                for r in cursor.fetchall()
            ]


@app.patch("/users/{user_id}/notifications/{notification_id}/read")
def mark_notification_read(user_id: int, notification_id: int, current_user=Depends(require_matching_user)):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE notification SET status = 'read'
                WHERE user_id = %s AND notification_id = %s
                RETURNING notification_id, status
                """,
                (user_id, notification_id),
            )
            row = cursor.fetchone()
            if row is None:
                return api_error("Notification not found", 404)
        connection.commit()
        return {"notification_id": row[0], "status": row[1]}


@app.get("/users/{user_id}/preferences")
def get_preferences(user_id: int, current_user=Depends(require_matching_user)):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT user_id, price_alerts, anomaly_alerts, notification_mode FROM user_preference WHERE user_id = %s",
                (user_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return api_error("Preferences not found", 404)
            return {"user_id": row[0], "price_alerts": row[1], "anomaly_alerts": row[2], "notification_mode": row[3]}


@app.put("/users/{user_id}/preferences")
def update_preferences(user_id: int, preference: UserPreferenceUpdate, current_user=Depends(require_matching_user)):
    if preference.notification_mode not in {"in_app", "email"}:
        return api_error("notification_mode must be 'in_app' or 'email'", 422)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM app_user WHERE user_id = %s", (user_id,))
            if cursor.fetchone() is None:
                return api_error("User not found", 404)
            cursor.execute(
                """
                INSERT INTO user_preference(user_id, price_alerts, anomaly_alerts, notification_mode)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    price_alerts = EXCLUDED.price_alerts,
                    anomaly_alerts = EXCLUDED.anomaly_alerts,
                    notification_mode = EXCLUDED.notification_mode
                """,
                (user_id, preference.price_alerts, preference.anomaly_alerts, preference.notification_mode),
            )
        connection.commit()
        return {"user_id": user_id, **preference.model_dump()}


@app.post("/alerts/check")
def check_alerts(current_user=Depends(get_current_user)):
    """Evaluate all active user-defined price alerts against the latest stored
    price for each security. Independent of statistical anomaly detection."""
    return check_all_active_alerts(user_id=current_user["user_id"])


@app.post("/analysis/run/{symbol}")
def run_analysis_for_symbol(symbol: str, current_user=Depends(get_current_user)):
    """Run the historical daily rolling-baseline analysis for one symbol.

    Reads already-ingested daily PRICE_BAR rows, computes rolling
    mean/std/volume-ratio baselines, and stores historical ANOMALY rows tied
    to a new completed ANALYSIS_RUN. Requires historical daily data to have
    been ingested first (see ingestion/price_ingestion.py --timeframe day).
    """
    try:
        result = run_historical_analysis([symbol.upper()])
    except ValueError as exc:
        return api_error(str(exc), 404)
    return {"symbol": symbol.upper(), "analysis_id": result[symbol.upper()]}


@app.post("/analysis/run")
def run_analysis_all(current_user=Depends(get_current_user)):
    """Run the historical daily rolling-baseline analysis for every configured
    symbol (config.SYMBOLS)."""
    results = {}
    errors = {}
    for symbol in SYMBOLS:
        try:
            results.update(run_historical_analysis([symbol]))
        except ValueError as exc:
            errors[symbol] = str(exc)
    return {"analysis_ids": results, "errors": errors}


@app.post("/pipeline/process/{symbol}")
def process_symbol_pipeline(symbol: str, timeframe: str = "minute", current_user=Depends(get_current_user)):
    """Manually re-run the real-time pipeline (recent anomaly detection +
    anomaly notification + price-alert evaluation) against the most recently
    stored bar for a symbol.

    This exercises the exact same code path used by the live Alpaca stream
    processor (``analysis.pipeline.process_new_bar``), without requiring a
    running WebSocket session. Useful for demos, manual testing, and grading
    environments where live streaming credentials/market hours are not
    available.
    """
    if timeframe not in {"day", "minute"}:
        return api_error("timeframe must be day or minute", 422)
    try:
        return process_latest_stored_bar(symbol.upper(), timeframe=timeframe)
    except ValueError as exc:
        return api_error(str(exc), 404)
