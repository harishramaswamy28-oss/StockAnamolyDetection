import os
import json
import websocket
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

URL = "wss://stream.data.alpaca.markets/v2/iex"


def on_open(ws):
    print("Connected to Alpaca WebSocket!")

    auth_message = {
        "action": "auth",
        "key": API_KEY,
        "secret": SECRET_KEY
    }

    ws.send(json.dumps(auth_message))
    print("Authentication message sent")


def on_message(ws, message):
    data = json.loads(message)

    print("\nReceived:")
    print(json.dumps(data, indent=2))

    # Wait for successful authentication
    if isinstance(data, list):
        for msg in data:
            if msg.get("T") == "success" and msg.get("msg") == "authenticated":

                print("\nAuthentication successful!")
                print("Now subscribing to AAPL...")

                subscribe_message = {
                    "action": "subscribe",
                    "trades": ["AAPL"],
                    "bars": ["AAPL"]
                }

                ws.send(json.dumps(subscribe_message))


def on_error(ws, error):
    print("\nWebSocket error:")
    print(error)


def on_close(ws, close_status_code, close_msg):
    print("\nWebSocket closed")
    print("Code:", close_status_code)
    print("Message:", close_msg)


ws = websocket.WebSocketApp(
    URL,
    on_open=on_open,
    on_message=on_message,
    on_error=on_error,
    on_close=on_close
)

ws.run_forever()