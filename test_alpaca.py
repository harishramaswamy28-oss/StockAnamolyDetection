import os
from dotenv import load_dotenv

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

load_dotenv()

API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

print("API key loaded:", API_KEY is not None)
print("Secret key loaded:", SECRET_KEY is not None)

client = StockHistoricalDataClient(
    API_KEY,
    SECRET_KEY
)

request = StockBarsRequest(
    symbol_or_symbols=["AAPL"],
    timeframe=TimeFrame.Minute,
    start="2025-01-02",
    end="2025-01-03"
)

bars = client.get_stock_bars(request)

print("\nHistorical data:")
print(bars.df)