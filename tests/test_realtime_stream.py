from unittest.mock import patch


def test_realtime_processor_uses_configured_market_feed(monkeypatch):
    from alpaca.data.enums import DataFeed

    from realtime import stream_processor

    monkeypatch.setenv("ALPACA_API_KEY", "test-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")
    monkeypatch.setattr(stream_processor, "DATA_FEED", "sip")

    with patch.object(stream_processor, "StockDataStream") as stream_class:
        stream_processor.RealtimeProcessor(symbols=["AAPL"])

    assert stream_class.call_args.kwargs["feed"] == DataFeed.SIP
