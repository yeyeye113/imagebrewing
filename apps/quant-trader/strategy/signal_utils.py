"""策略信号工具 — 将稀疏 BUY/SELL 事件转为 Backtester 可用的目标持仓序列。"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Signal


def long_only_hold_targets(events: pd.Series | np.ndarray) -> pd.Series | np.ndarray:
    """稀疏 BUY/SELL 事件 → 逐 bar 多头目标持仓 (BUY=持有 / HOLD=空仓).

    Backtester 按每 bar 的 want 决策；若仅在交叉日发 BUY、其余 HOLD，会在次日被平仓。
    """
    if isinstance(events, pd.Series):
        idx = events.index
        arr = long_only_hold_targets(events.to_numpy(dtype=int))
        return pd.Series(arr, index=idx)
    out = np.zeros(len(events), dtype=int)
    pos = 0
    for i, v in enumerate(events):
        v = int(v)
        if v == Signal.BUY:
            pos = 1
        elif v == Signal.SELL:
            pos = 0
        out[i] = Signal.BUY if pos else Signal.HOLD
    return out
