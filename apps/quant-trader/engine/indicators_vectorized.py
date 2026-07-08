"""Vectorized technical indicators — pure NumPy/Pandas, no loops.

All functions accept a 1-D NumPy array (float64) or Pandas Series and return
arrays of the same length.  NaN is used where a lookback window is not yet
full, consistent with Pandas ``rolling`` conventions.

Design goals
~~~~~~~~~~~~
- **Zero Python loops** — every computation is a vectorized Pandas/NumPy op.
- **Batch-friendly** — callers can stack multiple indicator outputs into a
  matrix for downstream vectorized signal generation.
- **Drop-in compatible** — return types mirror ``pd.Series`` when the input
  is a ``pd.Series``, so strategies can switch without rewriting callers.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ── helpers ──────────────────────────────────────────────────────────────────


def _as_series(data, index=None, name=None) -> pd.Series:
    """Ensure *data* is a ``pd.Series``; NumPy arrays are wrapped."""
    if isinstance(data, pd.Series):
        return data
    return pd.Series(data, index=index, name=name)


def _extract_close(data) -> tuple[np.ndarray, pd.Index | None]:
    """Return ``(close_np, index)`` from a DataFrame, Series, or array."""
    if isinstance(data, pd.DataFrame):
        return data["close"].values.astype(np.float64), data.index
    if isinstance(data, pd.Series):
        return data.values.astype(np.float64), data.index
    return np.asarray(data, dtype=np.float64), None


# ── Moving Averages ─────────────────────────────────────────────────────────


def sma(close, period: int) -> pd.Series:
    """Simple Moving Average — vectorized via ``rolling().mean()``."""
    s = _as_series(close)
    return s.rolling(period, min_periods=period).mean()


def ema(close, period: int, *, adjust: bool = False) -> pd.Series:
    """Exponential Moving Average — vectorized via ``ewm()``."""
    s = _as_series(close)
    return s.ewm(span=period, adjust=adjust).mean()


def dema(close, period: int) -> pd.Series:
    """Double Exponential Moving Average (DEMA = 2*EMA - EMA(EMA))."""
    e1 = ema(close, period)
    e2 = ema(e1, period)
    return 2.0 * e1 - e2


def wma(close, period: int) -> pd.Series:
    """Weighted Moving Average with linearly-increasing weights."""
    s = _as_series(close)
    weights = np.arange(1, period + 1, dtype=np.float64)
    return s.rolling(period).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)


# ── Momentum / Oscillators ──────────────────────────────────────────────────


def rsi(close, period: int = 14) -> pd.Series:
    """Relative Strength Index — Wilder smoothing via ``ewm(alpha=1/period)``."""
    s = _as_series(close)
    delta = s.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def macd(close, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    """MACD line, signal line, histogram — all vectorized."""
    ema_fast = ema(close, fast)
    ema_slow = ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def stochastic(high, low, close, k_period: int = 14, d_period: int = 3) -> tuple[pd.Series, pd.Series]:
    """Stochastic %K and %D — vectorized via ``rolling`` min/max."""
    h = _as_series(high)
    l = _as_series(low)
    c = _as_series(close)
    lowest_low = l.rolling(k_period, min_periods=k_period).min()
    highest_high = h.rolling(k_period, min_periods=k_period).max()
    denom = (highest_high - lowest_low).replace(0.0, np.nan)
    k = 100.0 * (c - lowest_low) / denom
    d = k.rolling(d_period, min_periods=d_period).mean()
    return k, d


def williams_r(high, low, close, period: int = 14) -> pd.Series:
    """Williams %R — vectorized via ``rolling`` min/max."""
    h = _as_series(high)
    l = _as_series(low)
    c = _as_series(close)
    hh = h.rolling(period, min_periods=period).max()
    ll = l.rolling(period, min_periods=period).min()
    denom = (hh - ll).replace(0.0, np.nan)
    return -100.0 * (hh - c) / denom


def cci(high, low, close, period: int = 20) -> pd.Series:
    """Commodity Channel Index — vectorized."""
    tp = (_as_series(high) + _as_series(low) + _as_series(close)) / 3.0
    sma_tp = tp.rolling(period, min_periods=period).mean()
    mad = tp.rolling(period, min_periods=period).apply(
        lambda x: np.abs(x - x.mean()).mean(),
        raw=True,
    )
    denom = 0.015 * mad
    denom = denom.replace(0.0, np.nan)
    return (tp - sma_tp) / denom


# ── Volatility ──────────────────────────────────────────────────────────────


def atr(high, low, close, period: int = 14) -> pd.Series:
    """Average True Range — Wilder smoothing (EMA with alpha=1/period)."""
    h = _as_series(high)
    l = _as_series(low)
    c = _as_series(close)
    prev_close = c.shift(1)
    tr = pd.concat(
        [
            h - l,
            (h - prev_close).abs(),
            (l - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()


def bollinger_bands(close, period: int = 20, num_std: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Bollinger Bands (upper, middle, lower) — vectorized."""
    s = _as_series(close)
    middle = sma(s, period)
    rolling_std = s.rolling(period, min_periods=period).std()
    upper = middle + num_std * rolling_std
    lower = middle - num_std * rolling_std
    return upper, middle, lower


def keltner_channel(
    high, low, close, ema_period: int = 20, atr_period: int = 10, multiplier: float = 1.5
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Keltner Channel (upper, middle, lower)."""
    mid = ema(close, ema_period)
    atr_val = atr(high, low, close, atr_period)
    upper = mid + multiplier * atr_val
    lower = mid - multiplier * atr_val
    return upper, mid, lower


def realized_volatility(close, period: int = 20, periods_per_year: int = 252) -> pd.Series:
    """Annualized realized volatility from log returns — vectorized."""
    s = _as_series(close)
    log_ret = np.log(s / s.shift(1))
    return log_ret.rolling(period, min_periods=period).std() * np.sqrt(periods_per_year)


# ── Volume ──────────────────────────────────────────────────────────────────


def obv(close, volume) -> pd.Series:
    """On-Balance Volume — vectorized via sign diff and cumsum."""
    c = _as_series(close)
    v = _as_series(volume)
    direction = np.sign(c.diff()).fillna(0.0)
    return (direction * v).cumsum()


def vwap(high, low, close, volume) -> pd.Series:
    """Volume-Weighted Average Price — cumulative from first bar."""
    tp = (_as_series(high) + _as_series(low) + _as_series(close)) / 3.0
    v = _as_series(volume)
    cum_tp_vol = (tp * v).cumsum()
    cum_vol = v.cumsum()
    return cum_tp_vol / cum_vol.replace(0.0, np.nan)


# ── Batch / Matrix helpers ──────────────────────────────────────────────────


def batch_indicators(df: pd.DataFrame, *, config: dict | None = None) -> pd.DataFrame:
    """Compute a battery of indicators in one call; returns a DataFrame.

    Parameters
    ----------
    df : DataFrame with columns ``close``, ``high``, ``low``, ``volume``.
    config : optional overrides for indicator parameters.  Keys:
        sma_periods : list[int], default [20, 50, 200]
        rsi_period  : int, default 14
        macd_fast/slow/signal : int
        bb_period, bb_std : int, float
        atr_period : int

    Returns
    -------
    DataFrame with one column per indicator, same index as *df*.
    """
    cfg = config or {}
    close = df["close"]
    out = pd.DataFrame(index=df.index)

    # Moving averages
    for p in cfg.get("sma_periods", [20, 50, 200]):
        out[f"sma_{p}"] = sma(close, p)

    # RSI
    out["rsi"] = rsi(close, cfg.get("rsi_period", 14))

    # MACD
    m, s, h = macd(close, cfg.get("macd_fast", 12), cfg.get("macd_slow", 26), cfg.get("macd_signal", 9))
    out["macd"] = m
    out["macd_signal"] = s
    out["macd_hist"] = h

    # Bollinger
    bb_p = cfg.get("bb_period", 20)
    bb_s = cfg.get("bb_std", 2.0)
    bb_upper, bb_mid, bb_lower = bollinger_bands(close, bb_p, bb_s)
    out["bb_upper"] = bb_upper
    out["bb_mid"] = bb_mid
    out["bb_lower"] = bb_lower

    # ATR (needs HLC)
    if all(c in df.columns for c in ("high", "low")):
        out["atr"] = atr(df["high"], df["low"], close, cfg.get("atr_period", 14))
        out["volatility"] = realized_volatility(close)

    # Volume indicators
    if "volume" in df.columns:
        out["obv"] = obv(close, df["volume"])

    return out
