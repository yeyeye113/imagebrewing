from __future__ import annotations

import pandas as pd

from .base import Strategy


class BollingerStrategy(Strategy):
    """Bollinger Band mean-reversion.

    Trader's logic: price stretched far below its statistical norm tends to
    snap back. Enter long when close pierces the lower band (n std below the
    mean), exit when it reverts to the middle band. The band width adapts to
    volatility, so position entries self-tighten in calm markets.
    """

    name = "bollinger"

    def __init__(self, period: int = 20, num_std: float = 2.0):
        self.period = int(period)
        self.num_std = float(num_std)

    def generate(self, prices: pd.DataFrame) -> pd.Series:
        close = prices["close"]
        mid = close.rolling(self.period, min_periods=self.period).mean()
        std = close.rolling(self.period, min_periods=self.period).std()
        lower = mid - self.num_std * std

        raw = pd.Series(pd.NA, index=prices.index, dtype="object")
        raw[close < lower] = 1  # stretched down -> buy
        raw[close >= mid] = 0  # reverted -> exit
        return raw.ffill().fillna(0).astype("int64")
