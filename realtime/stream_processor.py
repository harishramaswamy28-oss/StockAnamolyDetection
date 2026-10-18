"""Real-time market-data consumer.

Connects to Alpaca's authenticated stock WebSocket (IEX feed), receives
1-minute bars for the configured symbols, and delegates all storage/
detection/notification logic to :mod:`analysis.pipeline` so the real-time
workflow is implemented in exactly one place.

Authentication ordering
------------------------
``StockDataStream.subscribe_bars(...)`` only *registers* the handler and the
requested symbol locally; it does not send anything over the wire by itself.
The actual connect -> authenticate -> subscribe sequence is performed inside
``StockDataStream.run()`` (alpaca-py's internal event loop), which opens the
websocket, waits for a successful auth acknowledgement from Alpaca, and only
then flushes the queued subscription requests. Consequently, calling
``subscribe_bars`` before ``run()`` (as done below) is the documented,
correct alpaca-py usage: bars for a symbol are never delivered before that
symbol's subscription has been sent, and the subscription is never sent
before authentication succeeds. If authentication fails, alpaca-py raises/
surfaces an error from ``run()`` instead of silently continuing.
"""
import os

from alpaca.data.enums import DataFeed
from alpaca.data.live import StockDataStream
from dotenv import load_dotenv

from analysis.pipeline import close_open_analysis_runs, process_new_bar
from config import DATA_FEED, SYMBOLS

load_dotenv()


class RealtimeProcessor:
    def __init__(self, symbols=None):
        self.symbols = symbols or SYMBOLS
        self.api_key = os.getenv("ALPACA_API_KEY")
        self.secret_key = os.getenv("ALPACA_SECRET_KEY")
        if not self.api_key or not self.secret_key:
            raise ValueError("ALPACA_API_KEY and ALPACA_SECRET_KEY are required")
        self.stream = StockDataStream(self.api_key, self.secret_key, feed=DataFeed(DATA_FEED))

    async def handle_bar(self, bar):
        symbol = bar.symbol.upper()
        try:
            result = process_new_bar(
                symbol,
                bar.timestamp,
                float(bar.open),
                float(bar.high),
                float(bar.low),
                float(bar.close),
                int(bar.volume),
                bar.trade_count,
                float(bar.vwap) if bar.vwap is not None else None,
                timeframe="minute",
            )
        except ValueError as exc:
            # Unknown security, missing metadata, etc. Do not crash the stream.
            print(f"{symbol}: skipped bar ({exc})")
            return

        print(
            f"{symbol} {result['timestamp']}: close={float(bar.close):.4f}, "
            f"anomalies={result['anomalies_detected']}, "
            f"alert-notifications={result['alert_notifications_created']}"
        )

    def run(self):
        for symbol in self.symbols:
            self.stream.subscribe_bars(self.handle_bar, symbol)
        print(f"Streaming minute bars for: {', '.join(self.symbols)}")
        print("Feed: IEX")
        try:
            self.stream.run()
        except KeyboardInterrupt:
            print("Stopping real-time processor...")
            self.stream.stop()
        finally:
            close_open_analysis_runs(self.symbols)


if __name__ == "__main__":
    RealtimeProcessor().run()
