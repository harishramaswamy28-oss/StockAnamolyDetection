import os

from dotenv import load_dotenv
from alpaca.trading.client import TradingClient


load_dotenv()


def get_alpaca_client():
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")

    if not api_key or not secret_key:
        raise ValueError("Alpaca API credentials are missing.")

    return TradingClient(
        api_key,
        secret_key,
        paper=True
    )