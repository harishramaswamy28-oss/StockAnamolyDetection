import os
import json
import websocket
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("FINNHUB_API_KEY")


def on_open(ws):
    print("Connected to Finnhub WebSocket!")

    message = {
        "type": "subscribe",
        "symbol": "AAPL"
    }

    ws.send(json.dumps(message))

    print("Subscribed to AAPL")


def on_message(ws, message):
    data = json.loads(message)

    if data.get("type") == "ping":
        print("Ping received - connection is alive")

    elif data.get("type") == "trade":
        print("TRADE RECEIVED:")
        print(data)

    else:
        print("Other message:")
        print(data)


def on_error(ws, error):
    print("WebSocket error:", error)


def on_close(ws, close_status_code, close_msg):
    print("WebSocket closed")
    print("Code:", close_status_code)
    print("Message:", close_msg)


url = f"wss://ws.finnhub.io?token={API_KEY}"

ws = websocket.WebSocketApp(
    url,
    on_open=on_open,
    on_message=on_message,
    on_error=on_error,
    on_close=on_close
)

ws.run_forever()