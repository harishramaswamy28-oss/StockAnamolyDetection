"""Explainable, current dynamic bounds for a symbol's latest stored bar."""
import pandas as pd

from analysis.indicators import rolling_iqr_bounds
from config import DAILY_WINDOW, MIN_BASELINE_SAMPLES, REALTIME_WINDOW
from database.connection import get_connection


def get_threshold_snapshot(symbol: str, timeframe: str = "day"):
    if timeframe not in {"day", "minute"}:
        raise ValueError("timeframe must be day or minute")
    window = DAILY_WINDOW if timeframe == "day" else REALTIME_WINDOW
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT security_id FROM security WHERE symbol = %s", (symbol.upper(),))
            security = cursor.fetchone()
            if security is None:
                raise ValueError(f"Stock not found: {symbol.upper()}")
            cursor.execute(
                """SELECT timestamp, close, volume FROM price_bar
                   WHERE security_id = %s AND timeframe = %s
                   ORDER BY timestamp DESC LIMIT %s""",
                (security[0], timeframe, window + 2),
            )
            rows = list(reversed(cursor.fetchall()))
    finally:
        connection.close()

    if len(rows) < window + 2:
        return {"symbol": symbol.upper(), "timeframe": timeframe,
                "method": "rolling_iqr_fences", "fence_rule": "Q1 - 1.5×IQR / Q3 + 1.5×IQR", "window": window,
                "samples": max(0, len(rows) - 1), "ready": False,
                "message": "More historical bars are needed before adaptive bounds are available."}

    close = pd.Series([float(row[1]) for row in rows])
    volumes = pd.Series([float(row[2]) for row in rows])
    returns = close.pct_change().dropna().iloc[:-1].tail(window).reset_index(drop=True)
    prior_volumes = volumes.iloc[:-1].tail(window).reset_index(drop=True)
    minimum = min(MIN_BASELINE_SAMPLES, window)
    price_low, price_high = rolling_iqr_bounds(returns, window, minimum, shift=0)
    volume_low, volume_high = rolling_iqr_bounds(prior_volumes, window, minimum, shift=0)
    average_volume = float(prior_volumes.mean())
    return {
        "symbol": symbol.upper(), "timeframe": timeframe,
        "method": "rolling_iqr_fences", "fence_rule": "Q1 - 1.5×IQR / Q3 + 1.5×IQR", "window": window,
        "samples": len(returns), "ready": len(returns) >= minimum and average_volume > 0,
        "based_on_timestamp": rows[-2][0], "latest_timestamp": rows[-1][0],
        "latest_price": float(close.iloc[-1]),
        "price_return_lower": float(price_low.iloc[-1]),
        "price_return_upper": float(price_high.iloc[-1]),
        "volume_ratio_lower": float(volume_low.iloc[-1]) / average_volume if average_volume else None,
        "volume_ratio_upper": float(volume_high.iloc[-1]) / average_volume if average_volume else None,
        "message": "Bounds are recalculated from this symbol's previous observations; the latest bar is excluded.",
    }
