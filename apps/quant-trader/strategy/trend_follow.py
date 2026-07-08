"""双向趋势跟随策略 (TrendFollow) —— 期货 CTA 主力信号。

快线 MA(fast) 上穿慢线 MA(slow) 做多(+1)、下穿做空(-1)、未定空仓(0)。
实证(2026-06-29, 29 商品主力连续 ≈8 年): MA20/60 配 FuturesBacktester 波动率目标后
净夏普 0.60、回撤 -8%, 碾压纯多买持; 弱势段是危机 alpha。**做空腿需配 FuturesBacktester**
(核心 Backtester 仅做多, 只会执行其多头腿)。股指期货上趋势失效, 本策略宜用于商品。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy


class TrendFollowStrategy(Strategy):
    """双向均线趋势跟随 (sign(MA_fast - MA_slow))，输出 -1/0/+1 目标仓位。"""

    name = "trend_follow"

    def __init__(self, fast: int = 20, slow: int = 60):
        self.fast = int(fast)
        self.slow = int(slow)
        if self.fast >= self.slow:
            raise ValueError(f"fast({self.fast}) 必须 < slow({self.slow})")

    def generate(self, prices: pd.DataFrame) -> pd.Series:
        close = prices["close"]
        ma_fast = close.rolling(self.fast).mean()
        ma_slow = close.rolling(self.slow).mean()
        sig = np.sign(ma_fast - ma_slow)
        return pd.Series(sig, index=close.index).fillna(0.0)
