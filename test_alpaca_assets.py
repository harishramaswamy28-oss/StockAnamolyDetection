import os
from dotenv import load_dotenv
import requests

load_dotenv()

API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

symbols = ["AAPL", "MSFT", "TSLA", "NVDA", "SPY", "QQQ"]

headers = {
    "APCA-API-KEY-ID": API_KEY,
    "APCA-API-SECRET-KEY": SECRET_KEY
}

for symbol in symbols:

    url = f"https://paper-api.alpaca.markets/v2/assets/{symbol}"

    response = requests.get(url, headers=headers)

    print("\n" + "=" * 60)
    print(f"Symbol: {symbol}")
    print("HTTP Status:", response.status_code)

    if response.status_code == 200:

        data = response.json()

        print("ID:", data.get("id"))
        print("Class:", data.get("class"))
        print("Exchange:", data.get("exchange"))
        print("Symbol:", data.get("symbol"))
        print("Name:", data.get("name"))
        print("Status:", data.get("status"))
        print("Tradable:", data.get("tradable"))
        print("Fractionable:", data.get("fractionable"))

    else:
        print(response.json())