import pandas as pd

from config import (
    DAILY_WINDOW,
    SYMBOLS,
)
from database.connection import get_connection
from analysis.indicators import (
    calculate_returns,
    calculate_rolling_statistics,
    calculate_z_score,
    calculate_volume_indicators,
    classify_anomalies_with_volume,
)


def run_analysis(symbol: str, window: int = DAILY_WINDOW, threshold: float | None = None):
    symbol = symbol.upper()
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT security_id FROM security WHERE symbol = %s", (symbol,))
            result = cursor.fetchone()
            if result is None:
                raise ValueError(f"Security not found: {symbol}")
            security_id = result[0]
            cursor.execute(
                """
                SELECT timestamp, close, volume
                FROM price_bar
                WHERE security_id = %s AND timeframe = 'day'
                ORDER BY timestamp
                """,
                (security_id,),
            )
            rows = cursor.fetchall()
    finally:
        connection.close()

    if not rows:
        raise ValueError(f"No price data found for {symbol}")

    df = pd.DataFrame(rows, columns=["timestamp", "close", "volume"])
    df["close"] = df["close"].astype(float)
    df["volume"] = df["volume"].astype(float)
    df = calculate_returns(df)
    df = calculate_rolling_statistics(df, window)
    df = calculate_z_score(df)
    # ``threshold`` remains accepted for older callers, but classification is
    # based only on each row's rolling distribution-derived fences below.
    df["anomaly_score"] = df["z_score"].abs()
    df = calculate_volume_indicators(df, window)
    df = classify_anomalies_with_volume(
        df,
        window=window,
    )

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO analysis_run
                    (security_id, start_time, end_time, method, status)
                VALUES (%s, %s, %s, %s, 'running')
                RETURNING analysis_id
                """,
                (
                    security_id,
                    df["timestamp"].min(),
                    df["timestamp"].max(),
                    f"daily_rolling_iqr_fences_{window}d_v2",
                ),
            )
            analysis_id = cursor.fetchone()[0]

            for _, row in df[df["price_anomaly"]].iterrows():
                anomaly_type = "positive_return_spike" if row["return"] > 0 else "negative_return_spike"
                cursor.execute(
                    """
                    INSERT INTO anomaly
                        (security_id, timestamp, timeframe, analysis_id, anomaly_score, threshold, anomaly_type)
                    VALUES (%s, %s, 'day', %s, %s, %s, %s)
                    ON CONFLICT (analysis_id, security_id, timestamp, timeframe, anomaly_type) DO NOTHING
                    """,
                    (security_id, row["timestamp"], analysis_id, abs(row["return"]),
                     abs(row["price_lower_bound"] if row["return"] < row["price_lower_bound"] else row["price_upper_bound"]), anomaly_type),
                )

            for _, row in df[df["volume_spike"]].iterrows():
                cursor.execute(
                    """
                    INSERT INTO anomaly
                        (security_id, timestamp, timeframe, analysis_id, anomaly_score, threshold, anomaly_type)
                    VALUES (%s, %s, 'day', %s, %s, %s, 'volume_spike')
                    ON CONFLICT (analysis_id, security_id, timestamp, timeframe, anomaly_type) DO NOTHING
                    """,
                    (security_id, row["timestamp"], analysis_id, row["volume_ratio"], row["volume_upper_bound"]),
                )

            for _, row in df[df["volume_decline"]].iterrows():
                cursor.execute(
                    """
                    INSERT INTO anomaly
                        (security_id, timestamp, timeframe, analysis_id, anomaly_score, threshold, anomaly_type)
                    VALUES (%s, %s, 'day', %s, %s, %s, 'volume_decline')
                    ON CONFLICT (analysis_id, security_id, timestamp, timeframe, anomaly_type) DO NOTHING
                    """,
                    (security_id, row["timestamp"], analysis_id, row["volume_ratio"], row["volume_lower_bound"]),
                )

            cursor.execute(
                "UPDATE analysis_run SET status = 'completed' WHERE analysis_id = %s",
                (analysis_id,),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    print(f"{symbol}: analysis_id={analysis_id}")
    print(f"  price anomalies: {int(df['price_anomaly'].sum())}")
    print(f"  volume spikes:   {int(df['volume_spike'].sum())}")
    print(f"  volume declines: {int(df['volume_decline'].sum())}")
    return analysis_id


def run_all_symbols():
    return {symbol: run_analysis(symbol) for symbol in SYMBOLS}


if __name__ == "__main__":
    run_all_symbols()
