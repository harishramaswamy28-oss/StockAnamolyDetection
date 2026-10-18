import os


SYMBOLS = ["AAPL", "MSFT", "TSLA", "NVDA"]

# Baseline sample sizes. These define how much recent data informs each
# recalculated threshold; they are not anomaly cutoffs.
DAILY_WINDOW = 20
REALTIME_WINDOW = 20
MIN_BASELINE_SAMPLES = 8

# Automation intervals are operational settings, not detection thresholds.
AUTO_MONITORING_ENABLED = os.getenv("AUTO_MONITORING_ENABLED", "true").lower() in {"1", "true", "yes"}
AUTO_ALERT_CHECK_SECONDS = max(15, int(os.getenv("AUTO_ALERT_CHECK_SECONDS", "60")))
AUTO_DATA_REFRESH_SECONDS = max(300, int(os.getenv("AUTO_DATA_REFRESH_SECONDS", "21600")))
AUTO_DAILY_REFRESH_DAYS = max(1, int(os.getenv("AUTO_DAILY_REFRESH_DAYS", "5")))
AUTO_MINUTE_REFRESH_DAYS = max(1, int(os.getenv("AUTO_MINUTE_REFRESH_DAYS", "1")))

# Alpaca basic/IEX feed
DATA_FEED = "iex"
