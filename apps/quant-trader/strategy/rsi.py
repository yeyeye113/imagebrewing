from __future__ import annotations

import pandas as pd

from .base import Strategy


class RsiStrategy(Strategy):
    """RSI mean-reversion.

    Trader's logic: buy fear, sell greed. Go long when RSI dips into oversold
    territory (the crowd has over-sold), exit when it recovers past the upper
    band. Works best in ranging markets; pair with a trend filter or stop-loss
    in trends.
    """

    name = "rsi"

    def __init__(self, period: int = 14, oversold: float = 30.0, overbought: float = 70.0):
        self.period = int(period)
        self.oversold = float(oversold)
        self.overbought = float(overbought)

    def _rsi(self, close: pd.Series) -> pd.Series:
        delta = close.diff()
        gain = delta.clip(lower=0.0)
        loss = -delta.clip(upper=0.0)
        avg_gain = gain.ewm(alpha=1 / self.period, min_periods=self.period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / self.period, min_periods=self.period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0.0, pd.NA)
        return 100 - (100 / (1 + rs))

    def generate(self, prices: pd.DataFrame) -> pd.Series:
        rsi = self._rsi(prices["close"])
        raw = pd.Series(pd.NA, index=prices.index, dtype="object")
        raw[rsi < self.oversold] = 1
        raw[rsi > self.overbought] = 0
        return raw.ffill().fillna(0).astype("int64")
