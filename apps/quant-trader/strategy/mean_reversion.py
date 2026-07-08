"""均值回归策略 — 深度超跌反转 (DeepDipReversal).

实证背景 (2026-06-29, 30 只 A 股核心标的、~800 交易日真实 OOS 研究):
  - 多指标投票预测短期方向 ≈ 随机 (48%, 越筛越差);
  - 11 个技术择时策略无一跑赢买入持有 (买持均年化 40.3%, 最高 RSI 仅 5.3%);
  - 唯一稳定 edge = "深度超跌反转": 仅当股价深跌、远离年线 (MA60) 达阈值时,
    未来 20 日 55% 上涨 / 平均 +2.31%, 显著跑赢基准 (48% / +0.85%);
  - 浅跌信号 (RSI<30 / 20 日新低 / 连跌 3 天) 无 edge 甚至有害。
  详见 docs/prediction_accuracy_plan.md「二次复核实证」。

故本策略只在"深超跌"时抄底、反弹到中期均线 (MA20) 或触及最大持有期止盈。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Signal, Strategy


class DeepDipReversalStrategy(Strategy):
    """深度超跌反转 (mean reversion on deep dips below the long MA).

    入场: close / MA(ma_long) - 1 <= entry_dev   (深跌远离年线, 如 -10%)
    出场: close / MA(ma_exit) - 1 >= exit_dev     (反弹到中期均线)
          或 持有天数 >= max_hold                  (兜底, 避免长期套牢)

    返回目标持仓序列 (1=持有 / 0=空仓), 供 Backtester 按状态变化交易。
    """

    name = "deep_dip"

    def __init__(
        self,
        ma_long: int = 60,
        ma_exit: int = 20,
        entry_dev: float = -0.10,
        exit_dev: float = 0.0,
        max_hold: int = 30,
    ):
        self.ma_long = int(ma_long)
        self.ma_exit = int(ma_exit)
        self.entry_dev = float(entry_dev)
        self.exit_dev = float(exit_dev)
        self.max_hold = int(max_hold)

    def generate(self, prices: pd.DataFrame) -> pd.Series:
        close = prices["close"]
        n = len(close)
        if n < self.ma_long + 2:
            return pd.Series(Signal.HOLD, index=prices.index)

        ma_long = close.rolling(self.ma_long).mean()
        ma_exit = close.rolling(self.ma_exit).mean()
        dev_long = (close / ma_long - 1.0).to_numpy()
        dev_exit = (close / ma_exit - 1.0).to_numpy()

        sig = np.full(n, int(Signal.HOLD), dtype=int)
        holding = False
        hold_days = 0
        for i in range(self.ma_long, n):
            dl = dev_long[i]
            if np.isnan(dl):
                continue
            if not holding:
                # 深度超跌 → 抄底入场
                if dl <= self.entry_dev:
                    holding = True
                    hold_days = 0
                    sig[i] = int(Signal.BUY)
            else:
                hold_days += 1
                de = dev_exit[i]
                rebounded = (not np.isnan(de)) and de >= self.exit_dev
                if rebounded or hold_days >= self.max_hold:
                    holding = False  # 反弹止盈 / 到期离场
                else:
                    sig[i] = int(Signal.BUY)  # 继续持有
        return pd.Series(sig, index=prices.index)
