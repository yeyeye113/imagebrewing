"""Feature engineering for ML trading strategies.

Builds a rich feature matrix from OHLCV data including:
- Technical indicators (RSI, MACD, Bollinger, ATR, etc.)
- Price pattern features (returns, momentum, volatility)
- Volume features (volume ratio, OBV, VWAP deviation)
- Time features (day-of-week, month, quarter)

All features are computed with strict causality (no look-ahead).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Technical indicator helpers
# ---------------------------------------------------------------------------


def _sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, min_periods=n, adjust=False).mean()


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def _bollinger(close: pd.Series, n: int = 20, k: float = 2.0):
    mid = _sma(close, n)
    std = close.rolling(n, min_periods=n).std()
    upper = mid + k * std
    lower = mid - k * std
    return upper, mid, lower


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / n, min_periods=n, adjust=False).mean()


def _obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


# ---------------------------------------------------------------------------
# Feature Builder
# ---------------------------------------------------------------------------


class FeatureEngineer:
    """Build a feature matrix from OHLCV data.

    Parameters
    ----------
    windows : list[int]
        Rolling windows to use for multi-scale features.
    """

    def __init__(self, windows: Sequence[int] | None = None):
        self.windows: list[int] = sorted(windows or [5, 10, 20, 60])

    # -- public API ---------------------------------------------------------

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return a feature DataFrame aligned to *df.index*.

        Input *df* must have columns: open, high, low, close, volume.
        The first ``max(windows)`` rows will contain NaN due to lookback.
        """
        df = df.copy()
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        features: dict[str, pd.Series] = {}

        # ---- price returns & momentum ----
        for w in self.windows:
            features[f"ret_{w}"] = close.pct_change(w)
            features[f"mom_{w}"] = close / close.shift(w) - 1

        # log return (1-bar)
        features["log_ret_1"] = np.log(close / close.shift(1))

        # ---- volatility ----
        log_ret = features["log_ret_1"]
        for w in self.windows:
            features[f"vol_{w}"] = log_ret.rolling(w, min_periods=w).std()

        # ATR
        features["atr_14"] = _atr(high, low, close, 14)
        features["atr_pct"] = features["atr_14"] / close  # normalised

        # ---- moving averages & crossovers ----
        for w in self.windows:
            sma = _sma(close, w)
            ema = _ema(close, w)
            features[f"sma_{w}"] = sma
            features[f"ema_{w}"] = ema
            features[f"close_over_sma_{w}"] = close / sma - 1
            features[f"close_over_ema_{w}"] = close / ema - 1

        # MA cross ratios (fast/slow pairs)
        for i in range(len(self.windows) - 1):
            fast_w = self.windows[i]
            slow_w = self.windows[i + 1]
            sma_fast = features[f"sma_{fast_w}"]
            sma_slow = features[f"sma_{slow_w}"]
            features[f"sma_ratio_{fast_w}_{slow_w}"] = sma_fast / sma_slow - 1

        # ---- RSI ----
        for n in (6, 14, 28):
            features[f"rsi_{n}"] = _rsi(close, n)

        # ---- MACD ----
        macd_line, signal_line, macd_hist = _macd(close)
        features["macd"] = macd_line
        features["macd_signal"] = signal_line
        features["macd_hist"] = macd_hist

        # ---- Bollinger Bands ----
        bb_upper, bb_mid, bb_lower = _bollinger(close)
        features["bb_width"] = (bb_upper - bb_lower) / bb_mid
        features["bb_pct"] = (close - bb_lower) / (bb_upper - bb_lower)

        # ---- volume features ----
        for w in self.windows:
            features[f"vol_ratio_{w}"] = volume / volume.rolling(w, min_periods=w).mean()

        features["obv"] = _obv(close, volume)

        # VWAP deviation (approx: use cumulative typical price * volume / cum volume)
        tp = (high + low + close) / 3
        cum_tp_vol = (tp * volume).cumsum()
        cum_vol = volume.cumsum()
        vwap = cum_tp_vol / cum_vol.replace(0, np.nan)
        features["vwap_dev"] = close / vwap - 1

        # ---- price pattern features ----
        features["high_low_range"] = (high - low) / close
        features["close_position"] = (close - low) / (high - low).replace(0, np.nan)

        # candle body ratio
        body = (close - df["open"]).abs()
        wick = high - low
        features["body_ratio"] = body / wick.replace(0, np.nan)

        # gap from previous close
        features["gap"] = df["open"] / close.shift(1) - 1

        # n-bar high/low proximity
        for w in self.windows:
            roll_high = high.rolling(w, min_periods=w).max()
            roll_low = low.rolling(w, min_periods=w).min()
            features[f"dist_high_{w}"] = close / roll_high - 1
            features[f"dist_low_{w}"] = close / roll_low - 1

        # ---- time features (only if DatetimeIndex) ----
        if isinstance(df.index, pd.DatetimeIndex):
            features["dow"] = pd.Series(df.index.dayofweek, index=df.index, dtype="float64")
            features["month"] = pd.Series(df.index.month, index=df.index, dtype="float64")
            features["quarter"] = pd.Series(df.index.quarter, index=df.index, dtype="float64")

            # cyclical encoding
            features["dow_sin"] = np.sin(2 * np.pi * features["dow"] / 5)
            features["dow_cos"] = np.cos(2 * np.pi * features["dow"] / 5)
            features["month_sin"] = np.sin(2 * np.pi * features["month"] / 12)
            features["month_cos"] = np.cos(2 * np.pi * features["month"] / 12)

        out = pd.DataFrame(features, index=df.index)
        return out

    def fit_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Alias for :meth:`transform` (stateless)."""
        return self.transform(df)

    @property
    def feature_names(self) -> list[str]:
        """Run once on a dummy frame to get the canonical feature list."""
        dummy = pd.DataFrame(
            {
                "open": [1.0] * 100,
                "high": [1.01] * 100,
                "low": [0.99] * 100,
                "close": [1.0] * 100,
                "volume": [1e6] * 100,
            },
            index=pd.date_range("2020-01-01", periods=100, freq="B"),
        )
        return list(self.transform(dummy).columns)
