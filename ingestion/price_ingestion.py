import argparse
import os
from datetime import datetime, timedelta, timezone

from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from dotenv import load_dotenv

from config import DATA_FEED, SYMBOLS
from database.connection import get_connection

load_dotenv()


def get_price_data(timeframe: TimeFrame, days: int):
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    if not api_key or not secret_key:
        raise ValueError("ALPACA_API_KEY and ALPACA_SECRET_KEY are required")

    client = StockHistoricalDataClient(api_key, secret_key)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    request = StockBarsRequest(
        symbol_or_symbols=SYMBOLS,
        timeframe=timeframe,
        start=start,
        end=end,
        feed=DataFeed(DATA_FEED),
    )
    return client.get_stock_bars(request)


def insert_price_data(timeframe: TimeFrame, days: int):
    bars = get_price_data(timeframe, days)
    connection = get_connection()
    total = 0
    try:
        with connection.cursor() as cursor:
            for symbol in SYMBOLS:
                cursor.execute("SELECT security_id FROM security WHERE symbol = %s", (symbol,))
                row = cursor.fetchone()
                if row is None:
                    print(f"{symbol}: Security not found; run metadata ingestion first")
                    continue
                security_id = row[0]
                symbol_bars = bars.data.get(symbol, [])
                for bar in symbol_bars:
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
                        (security_id, bar.timestamp, "day" if timeframe.unit == TimeFrameUnit.Day else "minute",
                         bar.open, bar.high, bar.low, bar.close, bar.volume, bar.trade_count, bar.vwap),
                    )
                    total += 1
                print(f"{symbol}: {len(symbol_bars)} {timeframe} bars inserted/updated")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeframe", choices=["day", "minute"], default="day")
    parser.add_argument("--days", type=int, default=None)
    args = parser.parse_args()
    if args.days is None:
        args.days = 365 if args.timeframe == "day" else 5
    timeframe = TimeFrame.Day if args.timeframe == "day" else TimeFrame.Minute
    total = insert_price_data(timeframe, args.days)
    print(f"Total bars inserted/updated: {total}")


if __name__ == "__main__":
    main()
