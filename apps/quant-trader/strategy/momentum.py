from __future__ import annotations

import pandas as pd

from .base import Strategy


class MomentumStrategy(Strategy):
    """Time-series momentum (trend following).

    Trader's logic: "the trend is your friend." Hold long while price is above
    where it was `lookback` bars ago (positive momentum), step aside otherwise.
    An optional volatility/trend filter avoids whipsaws in flat markets.
    """

    name = "momentum"

    def __init__(self, lookback: int = 90, trend_filter: int = 0):
        self.lookback = int(lookback)
        self.trend_filter = int(trend_filter)  # 0 disables the SMA trend filter

    def generate(self, prices: pd.DataFrame) -> pd.Series:
        close = prices["close"]
        mom = close - close.shift(self.lookback)
        long_ok = mom > 0

        if self.trend_filter > 0:
            sma = close.rolling(self.trend_filter, min_periods=self.trend_filter).mean()
            long_ok = long_ok & (close > sma)

        target = pd.Series(0, index=prices.index, dtype="int64")
        target[long_ok.fillna(False)] = 1
        return target
