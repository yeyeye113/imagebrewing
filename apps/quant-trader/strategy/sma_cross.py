from __future__ import annotations

import pandas as pd

from .base import Signal, Strategy


class SmaCrossStrategy(Strategy):
    """Classic dual moving-average crossover.

    Long when the fast SMA is above the slow SMA, flat otherwise.
    A simple, well-understood baseline strategy.
    """

    name = "sma_cross"

    def __init__(self, fast: int = 20, slow: int = 50):
        if fast >= slow:
            raise ValueError(f"fast ({fast}) must be < slow ({slow})")
        self.fast = int(fast)
        self.slow = int(slow)

    def generate(self, prices: pd.DataFrame) -> pd.Series:
        close = prices["close"]
        fast_ma = close.rolling(self.fast, min_periods=self.fast).mean()
        slow_ma = close.rolling(self.slow, min_periods=self.slow).mean()

        target = pd.Series(Signal.HOLD, index=prices.index, dtype="int64")
        target[fast_ma > slow_ma] = Signal.BUY
        # Before both MAs are valid, stay flat.
        target[slow_ma.isna()] = Signal.HOLD
        return target
