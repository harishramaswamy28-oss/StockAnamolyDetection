"""Orchestration layer tying together ingestion, historical analysis,
real-time anomaly detection, and alert/notification generation.

This module implements the conceptual pipeline described in the project
specification:

    historical ingestion -> PRICE_BAR
                          -> historical analysis -> baseline + historical ANOMALY

    real-time bar arrives -> store PRICE_BAR
                          -> recent analysis (uses historical context only)
                          -> anomaly detection -> store ANOMALY
                          -> anomaly notification logic
                          -> price-alert evaluation
                          -> NOTIFICATION

Both ``realtime/stream_processor.py`` (the live Alpaca WebSocket consumer)
and ``api/main.py`` (a manual "process latest bar" / demo endpoint used when
no live stream is running) call the SAME functions defined here. There is
exactly one implementation of the real-time workflow; nothing is duplicated
inside a FastAPI route or inside the stream processor.
"""
from datetime import datetime, timezone

from alerts.alert_checker import check_all_active_alerts
from alerts.anomaly_notifier import notify_users_for_realtime_anomaly
from analysis.realtime_detector import evaluate_current_bar
from config import REALTIME_WINDOW
from database.connection import get_connection

REALTIME_METHOD = f"realtime_1min_rolling_iqr_fences_{REALTIME_WINDOW}_v2"


def get_security_id(cursor, symbol: str) -> int:
    cursor.execute("SELECT security_id FROM security WHERE symbol = %s", (symbol.upper(),))
    row = cursor.fetchone()
    if row is None:
        raise ValueError(f"Security not found: {symbol.upper()}. Run metadata ingestion first.")
    return row[0]


def get_or_create_open_analysis_run(cursor, security_id: int, method: str = REALTIME_METHOD,
                                     observation_time=None) -> int:
    """Return the open real-time run, creating a constraint-safe run if needed.

    Alpaca timestamps are the end of a completed minute and can be slightly
    earlier than the machine clock that receives them. ``analysis_run`` has a
    database constraint requiring ``end_time >= start_time``; therefore a new
    run is anchored to the observation timestamp rather than ``now()``.
    """
    cursor.execute(
        """
        SELECT analysis_id FROM analysis_run
        WHERE security_id = %s AND method = %s AND status = 'running'
        ORDER BY analysis_id DESC
        LIMIT 1
        """,
        (security_id, method),
    )
    row = cursor.fetchone()
    if row is not None:
        return row[0]

    start_time = observation_time or datetime.now(timezone.utc)
    cursor.execute(
        """
        INSERT INTO analysis_run (security_id, start_time, end_time, method, status)
        VALUES (%s, %s, %s, %s, 'running')
        RETURNING analysis_id
        """,
        (security_id, start_time, start_time, method),
    )
    return cursor.fetchone()[0]


def close_open_analysis_runs(symbols) -> None:
    """Mark any open real-time analysis runs for the given symbols as completed.

    Called when the real-time stream processor shuts down cleanly.
    """
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE analysis_run
                SET status = 'completed'
                WHERE method = %s AND status = 'running'
                  AND security_id IN (
                      SELECT security_id FROM security WHERE symbol = ANY(%s)
                  )
                """,
                (REALTIME_METHOD, [s.upper() for s in symbols]),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def store_price_bar(cursor, security_id, timestamp, timeframe, open_, high, low, close, volume,
                     trade_count, vwap) -> None:
    cursor.execute(
        """
        INSERT INTO price_bar
            (security_id, timestamp, timeframe, open, high, low, close, volume, trade_count, vwap)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (security_id, timestamp, timeframe) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            trade_count = EXCLUDED.trade_count,
            vwap = EXCLUDED.vwap
        """,
        (security_id, timestamp, timeframe, open_, high, low, close, volume, trade_count, vwap),
    )


def store_anomaly(cursor, security_id, timestamp, timeframe, analysis_id, anomaly_score, threshold,
                   anomaly_type) -> int:
    cursor.execute(
        """
        INSERT INTO anomaly
            (security_id, timestamp, timeframe, analysis_id, anomaly_score, threshold, anomaly_type)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (analysis_id, security_id, timestamp, timeframe, anomaly_type)
        DO UPDATE SET anomaly_score = EXCLUDED.anomaly_score,
                      threshold = EXCLUDED.threshold
        RETURNING anomaly_id
        """,
        (security_id, timestamp, timeframe, analysis_id, anomaly_score, threshold, anomaly_type),
    )
    return cursor.fetchone()[0]


def process_new_bar(symbol: str, timestamp, open_, high, low, close, volume, trade_count, vwap,
                     timeframe: str = "minute", run_alert_check: bool = True) -> dict:
    """Full real-time pipeline step for exactly one newly received bar.

        store PRICE_BAR
            -> recent analysis using historical context (evaluate_current_bar)
            -> store ANOMALY row(s) if any
            -> notify watching users for each new anomaly
            -> evaluate active price alerts
            -> create NOTIFICATION rows

    This is the single implementation used by both the live Alpaca stream and
    the manual/demo API trigger, so the real-time workflow is never duplicated.
    """
    symbol = symbol.upper()

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            security_id = get_security_id(cursor, symbol)
            store_price_bar(cursor, security_id, timestamp, timeframe, open_, high, low, close,
                             volume, trade_count, vwap)
            run_id = get_or_create_open_analysis_run(cursor, security_id, observation_time=timestamp)
            cursor.execute(
                "UPDATE analysis_run SET end_time = GREATEST(end_time, %s) WHERE analysis_id = %s",
                (timestamp, run_id),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    # Recent analysis: compares the just-stored bar against prior observations
    # only (the current bar never contributes to its own baseline).
    events = evaluate_current_bar(symbol, timestamp)

    stored_anomaly_ids = []
    for event in events:
        connection = get_connection()
        try:
            with connection.cursor() as cursor:
                anomaly_id = store_anomaly(
                    cursor, event["security_id"], event["timestamp"], timeframe, run_id,
                    event["anomaly_score"], event["threshold"], event["anomaly_type"],
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        stored_anomaly_ids.append(anomaly_id)
        notify_users_for_realtime_anomaly(
            anomaly_id,
            event["security_id"],
            event["symbol"],
            event["timestamp"],
            event["anomaly_type"],
            event["anomaly_score"],
            event["threshold"],
        )

    alert_result = {"alerts_checked": 0, "notifications_created": 0, "notifications": []}
    if run_alert_check:
        alert_result = check_all_active_alerts()

    return {
        "symbol": symbol,
        "timestamp": timestamp,
        "analysis_id": run_id,
        "anomalies_detected": len(events),
        "anomaly_ids": stored_anomaly_ids,
        "alert_notifications_created": alert_result["notifications_created"],
    }


def process_latest_stored_bar(symbol: str, timeframe: str = "minute") -> dict:
    """Re-run the real-time pipeline against the most recently stored bar for a
    symbol, without inserting a new bar.

    Intended for demoing/testing the real-time detection + alert + notification
    workflow through the API when no live Alpaca WebSocket session is running.
    Because `store_anomaly` upserts on the anomaly's natural key, re-running
    this against the same latest bar will not create duplicate anomaly rows.
    """
    symbol = symbol.upper()
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            security_id = get_security_id(cursor, symbol)
            cursor.execute(
                """
                SELECT timestamp, open, high, low, close, volume, trade_count, vwap
                FROM price_bar
                WHERE security_id = %s AND timeframe = %s
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                (security_id, timeframe),
            )
            row = cursor.fetchone()
    finally:
        connection.close()

    if row is None:
        raise ValueError(f"No {timeframe} price data stored for {symbol}")

    timestamp, open_, high, low, close, volume, trade_count, vwap = row
    return process_new_bar(
        symbol,
        timestamp,
        float(open_),
        float(high),
        float(low),
        float(close),
        int(volume),
        trade_count,
        float(vwap) if vwap is not None else None,
        timeframe=timeframe,
    )


def run_historical_analysis(symbols=None) -> dict:
    """Run the historical daily rolling-baseline analysis (see
    ``analysis/run_analysis.py``) for the given symbols, defaulting to
    ``config.SYMBOLS``.

    This is the historical side of the pipeline: it consumes already-ingested
    daily PRICE_BAR rows to build the 20-day rolling baseline and store
    historical ANOMALY rows tied to a completed ANALYSIS_RUN. It is distinct
    from ``process_new_bar``, which handles the current/real-time observation
    using recent minute bars as context.
    """
    from analysis.run_analysis import run_analysis, run_all_symbols

    if symbols is None:
        return run_all_symbols()
    return {symbol: run_analysis(symbol) for symbol in symbols}
