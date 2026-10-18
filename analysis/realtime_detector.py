from datetime import datetime

import pandas as pd

from analysis.indicators import rolling_iqr_bounds
from config import MIN_BASELINE_SAMPLES, REALTIME_WINDOW
from database.connection import get_connection


def get_security_id(symbol: str):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT security_id FROM security WHERE symbol = %s", (symbol.upper(),))
            row = cursor.fetchone()
            if row is None:
                raise ValueError(f"Security not found: {symbol.upper()}")
            return row[0]


def evaluate_current_bar(symbol: str, timestamp: datetime):
    """Evaluate a minute bar against dynamic fences learned from prior bars."""
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT security_id FROM security WHERE symbol = %s", (symbol.upper(),))
            row = cursor.fetchone()
            if row is None:
                raise ValueError(f"Security not found: {symbol.upper()}")
            security_id = row[0]
            cursor.execute(
                """SELECT timestamp, close, volume FROM price_bar
                   WHERE security_id = %s AND timeframe = 'minute' AND timestamp < %s
                   ORDER BY timestamp DESC LIMIT %s""",
                (security_id, timestamp, REALTIME_WINDOW + 1),
            )
            history = list(reversed(cursor.fetchall()))
            cursor.execute(
                """SELECT close, volume FROM price_bar
                   WHERE security_id = %s AND timeframe = 'minute' AND timestamp = %s""",
                (security_id, timestamp),
            )
            current = cursor.fetchone()
            if current is None or len(history) < REALTIME_WINDOW + 1:
                return []

            closes = [float(item[1]) for item in history]
            volumes = [float(item[2]) for item in history]
            returns = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes)) if closes[i - 1]]
            sample_count = min(REALTIME_WINDOW, len(returns))
            minimum = min(MIN_BASELINE_SAMPLES, sample_count)
            if sample_count < minimum or minimum < 2:
                return []
            recent_returns = pd.Series(returns[-sample_count:])
            price_low, price_high = rolling_iqr_bounds(
                recent_returns, sample_count, min_samples=minimum, shift=0
            )
            price_low, price_high = float(price_low.iloc[-1]), float(price_high.iloc[-1])

            recent_volumes = volumes[-sample_count:]
            volume_average = sum(recent_volumes) / len(recent_volumes)
            current_close, current_volume = float(current[0]), float(current[1])
            previous_close = closes[-1]
            current_return = current_close / previous_close - 1 if previous_close else 0.0
            volume_ratio = current_volume / volume_average if volume_average else 0.0
            raw_low, raw_high = rolling_iqr_bounds(
                pd.Series(recent_volumes), sample_count, min_samples=minimum, shift=0
            )
            volume_low = float(raw_low.iloc[-1]) / volume_average if volume_average else 0.0
            volume_high = float(raw_high.iloc[-1]) / volume_average if volume_average else 0.0
            events = []
            if current_return < price_low or current_return > price_high:
                events.append({
                    "security_id": security_id, "symbol": symbol.upper(), "timestamp": timestamp,
                    "anomaly_score": abs(current_return),
                    "threshold": abs(price_low if current_return < price_low else price_high),
                    "anomaly_type": "realtime_positive_return_spike" if current_return > price_high else "realtime_negative_return_spike",
                })
            if volume_ratio > volume_high:
                events.append({
                    "security_id": security_id, "symbol": symbol.upper(), "timestamp": timestamp,
                    "anomaly_score": volume_ratio, "threshold": volume_high,
                    "anomaly_type": "realtime_volume_spike",
                })
            if volume_ratio < volume_low:
                events.append({
                    "security_id": security_id, "symbol": symbol.upper(), "timestamp": timestamp,
                    "anomaly_score": volume_ratio, "threshold": volume_low,
                    "anomaly_type": "realtime_volume_decline",
                })
            return events
    finally:
        connection.close()
