import numpy as np
import pandas as pd


def rolling_iqr_bounds(series: pd.Series, window: int, min_samples: int = 8,
                       multiplier: float = 1.5, shift: int = 1):
    """Return per-observation Tukey fences learned from prior values only.

    The fences are recalculated as the rolling distribution changes. ``shift``
    defaults to one so the observation being classified cannot move its own
    threshold. Early observations remain unclassified until enough history is
    available; zero-IQR histories do not create infinite/NaN bounds.
    """
    prior = series.shift(shift)
    rolling = prior.rolling(window=window, min_periods=min_samples)
    q1 = rolling.quantile(0.25)
    q3 = rolling.quantile(0.75)
    spread = q3 - q1
    return q1 - multiplier * spread, q3 + multiplier * spread


def calculate_returns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("timestamp").copy()
    df["return"] = df["close"].pct_change()
    return df


def calculate_rolling_statistics(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    df = df.copy()
    df["rolling_mean"] = df["return"].rolling(window).mean().shift(1)
    df["rolling_std"] = df["return"].rolling(window).std().shift(1)
    return df


def calculate_z_score(df: pd.DataFrame) -> pd.DataFrame:
    """Z_t = (R_t - mu_t) / sigma_t

    Zero/undefined rolling standard deviation is handled safely: when
    ``rolling_std`` is 0 or NaN, the z-score is set to 0.0 rather than
    +/-inf or NaN. This prevents invalid infinite/NaN values from ever being
    stored as an anomaly_score (a NUMERIC database column cannot represent
    infinity, and NaN must never be interpreted as "very anomalous").
    """
    df = df.copy()
    safe_std = df["rolling_std"].replace(0, np.nan)
    z = (df["return"] - df["rolling_mean"]) / safe_std
    df["z_score"] = z.fillna(0.0)
    return df


def detect_anomalies(df: pd.DataFrame, threshold: float | None = None, window: int = 20) -> pd.DataFrame:
    """Classify returns using adaptive prior-sample fences.

    ``threshold`` is accepted only for compatibility with older callers; it
    does not affect the data-derived classification.
    """
    df = df.copy()
    df["anomaly_score"] = df["z_score"].abs()
    if "return" in df:
        lower, upper = rolling_iqr_bounds(df["return"], window, min_samples=min(8, window))
        df["is_anomaly"] = df["return"].lt(lower) | df["return"].gt(upper)
    else:
        df["is_anomaly"] = False
    return df


def calculate_volume_indicators(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    df = df.copy()
    df["volume_average"] = df["volume"].rolling(window).mean().shift(1)
    df["volume_ratio"] = df["volume"] / df["volume_average"]
    raw_low, raw_high = rolling_iqr_bounds(
        df["volume"], window, min_samples=min(8, window)
    )
    df["volume_lower_bound"] = raw_low / df["volume_average"]
    df["volume_upper_bound"] = raw_high / df["volume_average"]
    return df


def classify_anomalies_with_volume(df: pd.DataFrame, window: int = 20, **_legacy_thresholds) -> pd.DataFrame:
    df = df.copy()
    if "return" in df:
        df["price_lower_bound"], df["price_upper_bound"] = rolling_iqr_bounds(
            df["return"], window, min_samples=min(8, window)
        )
        df["price_anomaly"] = df["return"].lt(df["price_lower_bound"]) | df["return"].gt(df["price_upper_bound"])
    else:
        df["price_lower_bound"] = np.nan
        df["price_upper_bound"] = np.nan
        df["price_anomaly"] = False
    df["volume_spike"] = df["volume_ratio"].gt(df["volume_upper_bound"])
    df["volume_decline"] = df["volume_ratio"].lt(df["volume_lower_bound"])
    return df
