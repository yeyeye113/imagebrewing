"""Technical factors computed from OHLCV data.

22 factors covering momentum, volatility, volume, trend, overbought/oversold,
and channel-based signals. All inputs are standard OHLCV DataFrames.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Factor, FactorCategory, FactorResult

# ---------------------------------------------------------------------------
# Helpers (private)
# ---------------------------------------------------------------------------

_TRADING_DAYS = 252


def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


def _sma(s: pd.Series, window: int) -> pd.Series:
    return s.rolling(window, min_periods=1).mean()


def _true_range(df: pd.DataFrame) -> pd.Series:
    high, low, prev_close = df["high"], df["low"], df["close"].shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


# ---------------------------------------------------------------------------
# Momentum factors
# ---------------------------------------------------------------------------


class MomentumFactor(Factor):
    """N-day price momentum (log return).

    Parameters on construction: period (default 20).
    """

    name = "momentum"
    category = FactorCategory.TECHNICAL
    description = "Log return over N periods"

    def __init__(self, period: int = 20) -> None:
        self.period = period
        self._lookback = period + 5
        self.name = f"momentum_{period}"

    def compute(self, df: pd.DataFrame) -> FactorResult:
        close = df["close"]
        mom = np.log(close / close.shift(self.period))
        return FactorResult(
            name=self.name,
            values=mom,
            category=self.category,
            description=f"Log return over {self.period} bars",
        )


# ---------------------------------------------------------------------------
# Volatility factors
# ---------------------------------------------------------------------------


class HistoricalVolatilityFactor(Factor):
    """Annualised standard deviation of log returns."""

    name = "hist_volatility"
    category = FactorCategory.TECHNICAL
    description = "Annualised historical volatility"

    def __init__(self, period: int = 20) -> None:
        self.period = period
        self._lookback = period + 5
        self.name = f"hist_vol_{period}"

    def compute(self, df: pd.DataFrame) -> FactorResult:
        log_ret = np.log(df["close"] / df["close"].shift(1))
        vol = log_ret.rolling(self.period, min_periods=max(self.period // 2, 2)).std() * np.sqrt(_TRADING_DAYS)
        return FactorResult(
            name=self.name,
            values=vol,
            category=self.category,
            description=f"{self.period}-day annualised volatility",
        )


class ATRFactor(Factor):
    """Average True Range."""

    name = "atr"
    category = FactorCategory.TECHNICAL
    description = "Average True Range"

    def __init__(self, period: int = 14) -> None:
        self.period = period
        self._lookback = period + 5
        self.name = f"atr_{period}"

    def compute(self, df: pd.DataFrame) -> FactorResult:
        tr = _true_range(df)
        atr = tr.ewm(span=self.period, adjust=False).mean()
        return FactorResult(
            name=self.name,
            values=atr,
            category=self.category,
            description=f"ATR({self.period})",
        )


class ATRPctFactor(Factor):
    """ATR as a percentage of close price."""

    name = "atr_pct"
    category = FactorCategory.TECHNICAL
    description = "ATR / Close"

    def __init__(self, period: int = 14) -> None:
        self.period = period
        self._lookback = period + 5
        self.name = f"atr_pct_{period}"

    def compute(self, df: pd.DataFrame) -> FactorResult:
        tr = _true_range(df)
        atr = tr.ewm(span=self.period, adjust=False).mean()
        return FactorResult(
            name=self.name,
            values=atr / df["close"],
            category=self.category,
            description=f"ATR({self.period}) / Close",
        )


# ---------------------------------------------------------------------------
# Volume factors
# ---------------------------------------------------------------------------


class VolumeRatioFactor(Factor):
    """Today's volume / N-day average volume."""

    name = "volume_ratio"
    category = FactorCategory.TECHNICAL
    description = "Volume relative to moving average"

    def __init__(self, period: int = 20) -> None:
        self.period = period
        self._lookback = period + 5
        self.name = f"volume_ratio_{period}"

    def compute(self, df: pd.DataFrame) -> FactorResult:
        vol = df["volume"].astype(float)
        avg_vol = vol.rolling(self.period, min_periods=max(self.period // 2, 1)).mean()
        ratio = vol / avg_vol.replace(0, np.nan)
        return FactorResult(
            name=self.name,
            values=ratio,
            category=self.category,
            description=f"Volume / MA({self.period}) volume",
        )


class VolumeMAFactor(Factor):
    """Volume moving average (smoothing)."""

    name = "volume_ma"
    category = FactorCategory.TECHNICAL
    description = "Volume moving average"

    def __init__(self, period: int = 20) -> None:
        self.period = period
        self._lookback = period + 5
        self.name = f"volume_ma_{period}"

    def compute(self, df: pd.DataFrame) -> FactorResult:
        vol = df["volume"].astype(float)
        ma = vol.rolling(self.period, min_periods=1).mean()
        return FactorResult(
            name=self.name,
            values=ma,
            category=self.category,
            description=f"Volume MA({self.period})",
        )


class VolumePriceTrendFactor(Factor):
    """Volume Price Trend (VPT) = cumulative volume * % price change."""

    name = "vpt"
    category = FactorCategory.TECHNICAL
    description = "Volume Price Trend"

    _lookback = 5

    def compute(self, df: pd.DataFrame) -> FactorResult:
        close = df["close"]
        vol = df["volume"].astype(float)
        pct = close.pct_change().fillna(0)
        vpt = (vol * pct).cumsum()
        return FactorResult(
            name=self.name,
            values=vpt,
            category=self.category,
            description="Cumulative volume-weighted price change",
        )


# ---------------------------------------------------------------------------
# Trend factors
# ---------------------------------------------------------------------------


class ADFactor(Factor):
    """Accumulation/Distribution line.

    AD = cumulative(((Close - Low) - (High - Close)) / (High - Low) * Volume)
    """

    name = "ad_line"
    category = FactorCategory.TECHNICAL
    description = "Accumulation/Distribution line"

    _lookback = 5

    def compute(self, df: pd.DataFrame) -> FactorResult:
        high, low, close, vol = df["high"], df["low"], df["close"], df["volume"].astype(float)
        hl_range = (high - low).replace(0, np.nan)
        mfm = ((close - low) - (high - close)) / hl_range
        ad = (mfm * vol).cumsum()
        return FactorResult(
            name=self.name,
            values=ad,
            category=self.category,
            description="Accumulation/Distribution line",
        )


class TRIXFactor(Factor):
    """TRIX: 100-day ROC of a triple EMA."""

    name = "trix"
    category = FactorCategory.TECHNICAL
    description = "Triple exponential smoothed ROC"

    def __init__(self, period: int = 15) -> None:
        self.period = period
        self._lookback = period * 3 + 10
        self.name = f"trix_{period}"

    def compute(self, df: pd.DataFrame) -> FactorResult:
        close = df["close"]
        e1 = _ema(close, self.period)
        e2 = _ema(e1, self.period)
        e3 = _ema(e2, self.period)
        trix = e3.pct_change() * 100
        return FactorResult(
            name=self.name,
            values=trix,
            category=self.category,
            description=f"TRIX({self.period})",
        )


# ---------------------------------------------------------------------------
# Overbought / Oversold
# ---------------------------------------------------------------------------


class RSIFactor(Factor):
    """Relative Strength Index."""

    name = "rsi"
    category = FactorCategory.TECHNICAL
    description = "Relative Strength Index"

    def __init__(self, period: int = 14) -> None:
        self.period = period
        self._lookback = period + 5
        self.name = f"rsi_{period}"

    def compute(self, df: pd.DataFrame) -> FactorResult:
        return FactorResult(
            name=self.name,
            values=_rsi(df["close"], self.period),
            category=self.category,
            description=f"RSI({self.period})",
        )


class RSIOverboughtFactor(Factor):
    """Binary flag: RSI > threshold."""

    name = "rsi_overbought"
    category = FactorCategory.TECHNICAL
    description = "RSI overbought flag"

    def __init__(self, period: int = 14, threshold: float = 70.0) -> None:
        self.period = period
        self.threshold = threshold
        self._lookback = period + 5
        self.name = f"rsi_overbought_{period}"

    def compute(self, df: pd.DataFrame) -> FactorResult:
        rsi = _rsi(df["close"], self.period)
        flag = (rsi > self.threshold).astype(float)
        return FactorResult(
            name=self.name,
            values=flag,
            category=self.category,
            description=f"RSI({self.period}) > {self.threshold}",
        )


class RSIOversoldFactor(Factor):
    """Binary flag: RSI < threshold."""

    name = "rsi_oversold"
    category = FactorCategory.TECHNICAL
    description = "RSI oversold flag"

    def __init__(self, period: int = 14, threshold: float = 30.0) -> None:
        self.period = period
        self.threshold = threshold
        self._lookback = period + 5
        self.name = f"rsi_oversold_{period}"

    def compute(self, df: pd.DataFrame) -> FactorResult:
        rsi = _rsi(df["close"], self.period)
        flag = (rsi < self.threshold).astype(float)
        return FactorResult(
            name=self.name,
            values=flag,
            category=self.category,
            description=f"RSI({self.period}) < {self.threshold}",
        )


class CCIFactor(Factor):
    """Commodity Channel Index."""

    name = "cci"
    category = FactorCategory.TECHNICAL
    description = "Commodity Channel Index"

    def __init__(self, period: int = 20) -> None:
        self.period = period
        self._lookback = period + 5
        self.name = f"cci_{period}"

    def compute(self, df: pd.DataFrame) -> FactorResult:
        tp = (df["high"] + df["low"] + df["close"]) / 3
        sma = _sma(tp, self.period)
        mad = tp.rolling(self.period, min_periods=max(self.period // 2, 1)).apply(
            lambda x: np.mean(np.abs(x - x.mean())), raw=True
        )
        cci = (tp - sma) / (0.015 * mad.replace(0, np.nan))
        return FactorResult(
            name=self.name,
            values=cci,
            category=self.category,
            description=f"CCI({self.period})",
        )


class WilliamsRFactor(Factor):
    """Williams %R oscillator."""

    name = "williams_r"
    category = FactorCategory.TECHNICAL
    description = "Williams %R"

    def __init__(self, period: int = 14) -> None:
        self.period = period
        self._lookback = period + 5
        self.name = f"williams_r_{period}"

    def compute(self, df: pd.DataFrame) -> FactorResult:
        high = df["high"].rolling(self.period, min_periods=1).max()
        low = df["low"].rolling(self.period, min_periods=1).min()
        wr = -100 * (high - df["close"]) / (high - low).replace(0, np.nan)
        return FactorResult(
            name=self.name,
            values=wr,
            category=self.category,
            description=f"Williams %R({self.period})",
        )


# ---------------------------------------------------------------------------
# Channel factors
# ---------------------------------------------------------------------------


class BollingerPositionFactor(Factor):
    """Position within Bollinger Bands: (close - lower) / (upper - lower).

    Returns 0 at lower band, 1 at upper band.
    """

    name = "bollinger_position"
    category = FactorCategory.TECHNICAL
    description = "Bollinger Band position"

    def __init__(self, period: int = 20, num_std: float = 2.0) -> None:
        self.period = period
        self.num_std = num_std
        self._lookback = period + 5
        self.name = f"boll_pos_{period}"

    def compute(self, df: pd.DataFrame) -> FactorResult:
        close = df["close"]
        ma = _sma(close, self.period)
        std = close.rolling(self.period, min_periods=max(self.period // 2, 1)).std()
        upper = ma + self.num_std * std
        lower = ma - self.num_std * std
        width = (upper - lower).replace(0, np.nan)
        pos = (close - lower) / width
        return FactorResult(
            name=self.name,
            values=pos,
            category=self.category,
            description=f"BB position ({self.period}, {self.num_std} sigma)",
        )


class BollingerWidthFactor(Factor):
    """Bollinger Band width (upper - lower) / middle."""

    name = "bollinger_width"
    category = FactorCategory.TECHNICAL
    description = "Bollinger Band width"

    def __init__(self, period: int = 20, num_std: float = 2.0) -> None:
        self.period = period
        self.num_std = num_std
        self._lookback = period + 5
        self.name = f"boll_width_{period}"

    def compute(self, df: pd.DataFrame) -> FactorResult:
        close = df["close"]
        ma = _sma(close, self.period)
        std = close.rolling(self.period, min_periods=max(self.period // 2, 1)).std()
        width = (self.num_std * std * 2) / ma.replace(0, np.nan)
        return FactorResult(
            name=self.name,
            values=width,
            category=self.category,
            description=f"BB width ({self.period}, {self.num_std} sigma)",
        )


class ATRBandPositionFactor(Factor):
    """ATR Channel position: where close sits between SMA +/- N*ATR."""

    name = "atr_band_position"
    category = FactorCategory.TECHNICAL
    description = "ATR channel position"

    def __init__(self, period: int = 14, multiplier: float = 2.0) -> None:
        self.period = period
        self.multiplier = multiplier
        self._lookback = period + 5
        self.name = f"atr_band_pos_{period}"

    def compute(self, df: pd.DataFrame) -> FactorResult:
        close = df["close"]
        ma = _sma(close, self.period * 2)
        tr = _true_range(df)
        atr = tr.ewm(span=self.period, adjust=False).mean()
        upper = ma + self.multiplier * atr
        lower = ma - self.multiplier * atr
        width = (upper - lower).replace(0, np.nan)
        pos = (close - lower) / width
        return FactorResult(
            name=self.name,
            values=pos,
            category=self.category,
            description=f"ATR channel position ({self.period}, x{self.multiplier})",
        )


# ---------------------------------------------------------------------------
# MACD family
# ---------------------------------------------------------------------------


class MACDFactor(Factor):
    """MACD line (fast EMA - slow EMA)."""

    name = "macd"
    category = FactorCategory.TECHNICAL
    description = "MACD line"

    def __init__(self, fast: int = 12, slow: int = 26) -> None:
        self.fast = fast
        self.slow = slow
        self._lookback = slow + 10
        self.name = f"macd_{fast}_{slow}"

    def compute(self, df: pd.DataFrame) -> FactorResult:
        close = df["close"]
        macd = _ema(close, self.fast) - _ema(close, self.slow)
        return FactorResult(
            name=self.name,
            values=macd,
            category=self.category,
            description=f"MACD({self.fast},{self.slow})",
        )


class MACDHistogramFactor(Factor):
    """MACD histogram (MACD - signal line)."""

    name = "macd_histogram"
    category = FactorCategory.TECHNICAL
    description = "MACD histogram"

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9) -> None:
        self.fast = fast
        self.slow = slow
        self.signal = signal
        self._lookback = slow + signal + 10
        self.name = f"macd_hist_{fast}_{slow}_{signal}"

    def compute(self, df: pd.DataFrame) -> FactorResult:
        close = df["close"]
        macd_line = _ema(close, self.fast) - _ema(close, self.slow)
        signal_line = _ema(macd_line, self.signal)
        hist = macd_line - signal_line
        return FactorResult(
            name=self.name,
            values=hist,
            category=self.category,
            description=f"MACD histogram ({self.fast},{self.slow},{self.signal})",
        )


# ---------------------------------------------------------------------------
# Smoothed / exotic
# ---------------------------------------------------------------------------


class DEMAFactor(Factor):
    """Double Exponential Moving Average (DEMA)."""

    name = "dema"
    category = FactorCategory.TECHNICAL
    description = "Double EMA"

    def __init__(self, period: int = 20) -> None:
        self.period = period
        self._lookback = period * 2 + 10
        self.name = f"dema_{period}"

    def compute(self, df: pd.DataFrame) -> FactorResult:
        close = df["close"]
        e1 = _ema(close, self.period)
        e2 = _ema(e1, self.period)
        dema = 2 * e1 - e2
        return FactorResult(
            name=self.name,
            values=dema / close,  # normalize to price ratio
            category=self.category,
            description=f"DEMA({self.period}) / Close",
        )


class MassIndexFactor(Factor):
    """Mass Index: detects trend reversals via range expansion."""

    name = "mass_index"
    category = FactorCategory.TECHNICAL
    description = "Mass Index"

    def __init__(self, period: int = 9, sum_period: int = 25) -> None:
        self.period = period
        self.sum_period = sum_period
        self._lookback = sum_period + period + 10
        self.name = f"mass_index_{period}"

    def compute(self, df: pd.DataFrame) -> FactorResult:
        hl = df["high"] - df["low"]
        ema1 = _ema(hl, self.period)
        ema2 = _ema(ema1, self.period)
        ratio = ema1 / ema2.replace(0, np.nan)
        mass = ratio.rolling(self.sum_period, min_periods=max(self.sum_period // 2, 1)).sum()
        return FactorResult(
            name=self.name,
            values=mass,
            category=self.category,
            description=f"Mass Index({self.period},{self.sum_period})",
        )


class OBVFactor(Factor):
    """On-Balance Volume."""

    name = "obv"
    category = FactorCategory.TECHNICAL
    description = "On-Balance Volume"

    _lookback = 5

    def compute(self, df: pd.DataFrame) -> FactorResult:
        close = df["close"]
        vol = df["volume"].astype(float)
        direction = np.sign(close.diff()).fillna(0)
        obv = (vol * direction).cumsum()
        return FactorResult(
            name=self.name,
            values=obv,
            category=self.category,
            description="On-Balance Volume",
        )
