"""期货回测引擎（双向交易 + 保证金/杠杆）。

与核心 `Backtester`（仅做多/空仓、股票口径）**完全隔离**，专为期货设计、不影响其测试：
  - 持仓 position ∈ [-1, +1]（可经波动率目标放大），**支持做空**；
  - 保证金交易：名义敞口 = position × leverage × 权益，杠杆受 ``max_leverage`` 约束；
  - 收益率口径：日收益 = position.shift1 × 标的日收益 × leverage − |Δposition|.shift1 × cost；
    （次日生效，避免未来函数；做空时标的下跌则盈利）；
  - 逐日盯市净值 + 夏普/年化/回撤/在场占比/多空占比/换手次数。

研究/回测期货 CTA（趋势可做空）用本引擎；A股长多回测仍用核心 Backtester。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..strategy.base import Strategy

ANN_DAYS = 252


@dataclass
class FuturesBacktestConfig:
    leverage: float = 1.0          # 名义杠杆倍数
    cost: float = 0.0003           # 单边换手成本(手续费+滑点)
    max_leverage: float = 5.0      # 杠杆上限(保证金约束的等价表达)
    target_vol: float | None = None  # 若设(年化)，按反向波动缩放仓位(CTA 风险平价)
    vol_lookback: int = 20
    maintenance_margin: float = 0.0  # >0 启用保证金强平：权益(初值1.0)跌破此线即强平(吸收态)；0=关闭


@dataclass
class FuturesBacktestResult:
    equity_curve: pd.Series
    returns: pd.Series
    position: pd.Series            # 实际(含杠杆/缩放)目标仓位
    stats: dict


class FuturesBacktester:
    """期货双向(可做空)+保证金回测，收益率口径、逐日盯市。"""

    def __init__(self, config: FuturesBacktestConfig | None = None):
        self.cfg = config or FuturesBacktestConfig()

    def run(self, prices: pd.DataFrame, strategy: Strategy | pd.Series) -> FuturesBacktestResult:
        cfg = self.cfg
        close = prices["close"]
        ret = close.pct_change().fillna(0.0)

        if isinstance(strategy, Strategy):
            sig = strategy.generate(prices)
        else:
            sig = strategy
        sig = pd.Series(sig).reindex(prices.index).fillna(0.0)
        pos = np.sign(sig).astype(float)          # 归一到 -1/0/+1

        if cfg.target_vol:                        # 波动率目标缩放(可放大/缩小)
            rvol = ret.rolling(cfg.vol_lookback).std() * np.sqrt(ANN_DAYS)
            scale = (cfg.target_vol / rvol).replace([np.inf, -np.inf], np.nan)
            scale = scale.clip(upper=cfg.max_leverage).fillna(0.0)
            pos = pos * scale

        lev_pos = (pos * cfg.leverage).clip(-cfg.max_leverage, cfg.max_leverage)
        exec_pos = lev_pos.shift(1).fillna(0.0)   # 次日生效
        turnover = lev_pos.diff().abs()
        if len(lev_pos):
            turnover.iloc[0] = abs(float(lev_pos.iloc[0]))  # 建仓首笔也计成本
        turnover = turnover.shift(1).fillna(0.0)

        strat_ret = exec_pos * ret - turnover * cfg.cost
        # 杠杆下单日亏损可能 ≤ -100%(爆仓): 不封底会让 (1+r) 变 0/负, cumprod 后净值
        # 符号乱跳、Sharpe/回撤全失真。按破产吸收态封底单日收益 -100%——触及即净值归零
        # 并维持(后续 cumprod 恒 0), 符合真实强平语义。正常温和行情下此 clip 不改变结果。
        strat_ret = strat_ret.clip(lower=-1.0)
        equity = (1.0 + strat_ret).cumprod()

        # 保证金强平(可选)：真实期货在权益跌破维持保证金线时即被强平，而非亏满单日 -100%。
        # maintenance_margin>0 时启用——权益(初值 1.0)首次跌破该线即强平：权益冻结、仓位归零、
        # 后续不再产生损益(吸收态)。默认 0.0=关闭，保持向后兼容、既有回测结果不变。
        if cfg.maintenance_margin > 0.0:
            below = equity.to_numpy() <= cfg.maintenance_margin
            if below.any():
                liq = int(below.argmax())              # 首次跌破维持保证金的 bar
                equity.iloc[liq:] = float(equity.iloc[liq])
                strat_ret.iloc[liq + 1:] = 0.0
                exec_pos.iloc[liq + 1:] = 0.0

        return FuturesBacktestResult(equity, strat_ret, lev_pos,
                                     self._stats(equity, strat_ret, exec_pos))

    @staticmethod
    def _stats(equity: pd.Series, ret: pd.Series, pos: pd.Series) -> dict:
        eq = equity.to_numpy()
        r = ret.to_numpy()
        p = pos.to_numpy()
        n = len(eq)
        total_return = float(eq[-1] - 1.0) if n else 0.0
        yrs = max(1e-9, n / ANN_DAYS)
        cagr = float(eq[-1] ** (1.0 / yrs) - 1.0) if n and eq[-1] > 0 else -1.0
        sharpe = float(r.mean() / r.std() * np.sqrt(ANN_DAYS)) if r.std() > 0 else 0.0
        peak = np.maximum.accumulate(eq) if n else np.array([1.0])
        max_dd = float((eq / peak - 1.0).min()) if n else 0.0
        flips = int((np.diff(np.sign(p)) != 0).sum()) if n > 1 else 0
        return {
            "total_return": total_return,
            "cagr": cagr,
            "sharpe": sharpe,
            "max_drawdown": max_dd,
            "exposure": float((p != 0).mean()) if n else 0.0,
            "long_share": float((p > 0).mean()) if n else 0.0,
            "short_share": float((p < 0).mean()) if n else 0.0,
            "n_flips": flips,
        }
