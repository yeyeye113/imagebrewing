"""对比分析器 — 回测 vs 模拟收益对比，计算偏差指标。"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .recorder import ComparisonRecord, TradeRecorder


@dataclass
class TradeComparison:
    """单笔交易的回测 vs 模拟对比结果。"""

    decision_id: str = ""
    symbol: str = ""
    # 回测指标
    backtest_pnl: float = 0.0
    backtest_pnl_pct: float = 0.0
    backtest_confidence: float = 0.0
    # 模拟指标
    sim_pnl: float = 0.0
    sim_pnl_pct: float = 0.0
    sim_confidence: float = 0.0
    # 偏差
    pnl_delta: float = 0.0  # sim - backtest
    pnl_pct_delta: float = 0.0
    confidence_delta: float = 0.0
    slippage: float = 0.0
    exit_reason: str = ""


@dataclass
class ComparisonResult:
    """完整对比结果集。"""

    period: str = ""  # 分析区间
    total_trades: int = 0
    # 回测汇总
    backtest_total_pnl: float = 0.0
    backtest_win_rate: float = 0.0
    backtest_avg_pnl_pct: float = 0.0
    backtest_sharpe: float = 0.0
    backtest_max_drawdown: float = 0.0
    # 模拟汇总
    sim_total_pnl: float = 0.0
    sim_win_rate: float = 0.0
    sim_avg_pnl_pct: float = 0.0
    sim_sharpe: float = 0.0
    sim_max_drawdown: float = 0.0
    # 偏差
    pnl_gap: float = 0.0  # sim - backtest 总收益差
    win_rate_gap: float = 0.0  # 胜率差
    avg_slippage: float = 0.0  # 平均滑点
    accuracy_score: float = 0.0  # 模拟与回测一致性评分 0-1
    # 按标的明细
    per_symbol: dict = field(default_factory=dict)  # symbol -> dict


class ComparisonAnalyzer:
    """对比分析引擎 — 计算回测与模拟的系统性偏差。"""

    def __init__(self, recorder: TradeRecorder):
        self.recorder = recorder

    def analyze_full(self) -> ComparisonResult:
        """全量对比分析。"""
        records = self.recorder.load_all()
        return self._compute_result(records, "全量")

    def analyze_by_symbol(self, symbol: str) -> ComparisonResult:
        """按标的对比分析。"""
        records = self.recorder.get_by_symbol(symbol)
        return self._compute_result(records, symbol)

    def analyze_by_period(self, start_date: str, end_date: str) -> ComparisonResult:
        """按时间段对比分析。"""
        records = self.recorder.load_all()
        filtered = [r for r in records if start_date <= r.decision.ts[:10] <= end_date]
        return self._compute_result(filtered, f"{start_date} ~ {end_date}")

    def trade_level_comparison(self) -> list[dict]:
        """逐笔回测 vs 模拟对比。"""
        records = self.recorder.load_all()
        results = []
        for r in records:
            d, s = r.decision, r.simulation
            results.append(
                {
                    "id": d.id,
                    "symbol": d.symbol,
                    "ts": d.ts,
                    "backtest_pnl": s.backtest_pnl,
                    "backtest_pnl_pct": s.backtest_pnl_pct,
                    "sim_pnl": s.pnl,
                    "sim_pnl_pct": s.pnl_pct,
                    "pnl_delta": s.pnl - s.backtest_pnl,
                    "pnl_pct_delta": s.pnl_pct - s.backtest_pnl_pct,
                    "slippage": s.slippage,
                    "exit_reason": s.exit_reason,
                    "confidence": d.confidence,
                }
            )
        return results

    def consistency_score(self, records: list[ComparisonRecord]) -> float:
        """一致性评分: sim 和 backtest 方向一致的比例。"""
        if not records:
            return 0.0
        agree = 0
        for r in records:
            bt_sign = 1 if r.simulation.backtest_pnl > 0 else (-1 if r.simulation.backtest_pnl < 0 else 0)
            sim_sign = 1 if r.simulation.pnl > 0 else (-1 if r.simulation.pnl < 0 else 0)
            if bt_sign == sim_sign:
                agree += 1
        return agree / len(records)

    # ── 内部 ─────────────────────────────────────────────────────────

    def _compute_result(self, records: list[ComparisonRecord], period: str) -> ComparisonResult:
        if not records:
            return ComparisonResult(period=period)

        sims = [r.simulation for r in records]

        # 回测汇总
        bt_pnls = [s.backtest_pnl for s in sims]
        bt_pnl_pcts = [s.backtest_pnl_pct for s in sims]
        bt_wins = sum(1 for p in bt_pnls if p > 0)

        # 模拟汇总
        sim_pnls = [s.pnl for s in sims]
        sim_pnl_pcts = [s.pnl_pct for s in sims]
        sim_wins = sum(1 for p in sim_pnls if p > 0)

        # 滑点
        slippages = [abs(s.slippage) for s in sims]

        # 按标的分组
        per_symbol = {}
        symbols = set(r.decision.symbol for r in records)
        for sym in symbols:
            sym_records = [r for r in records if r.decision.symbol == sym]
            sym_sims = [r.simulation for r in sym_records]
            sym_bt = sum(s.backtest_pnl for s in sym_sims)
            sym_sim = sum(s.pnl for s in sym_sims)
            sym_wins = sum(1 for s in sym_sims if s.pnl > 0)
            per_symbol[sym] = {
                "trades": len(sym_records),
                "backtest_pnl": round(sym_bt, 2),
                "sim_pnl": round(sym_sim, 2),
                "delta": round(sym_sim - sym_bt, 2),
                "win_rate": round(sym_wins / len(sym_records), 4) if sym_records else 0,
            }

        n = len(records)
        return ComparisonResult(
            period=period,
            total_trades=n,
            backtest_total_pnl=round(sum(bt_pnls), 2),
            backtest_win_rate=round(bt_wins / n, 4),
            backtest_avg_pnl_pct=round(np.mean(bt_pnl_pcts), 6) if bt_pnl_pcts else 0,
            sim_total_pnl=round(sum(sim_pnls), 2),
            sim_win_rate=round(sim_wins / n, 4),
            sim_avg_pnl_pct=round(np.mean(sim_pnl_pcts), 6) if sim_pnl_pcts else 0,
            pnl_gap=round(sum(sim_pnls) - sum(bt_pnls), 2),
            win_rate_gap=round((sim_wins / n) - (bt_wins / n), 4) if n else 0,
            avg_slippage=round(np.mean(slippages), 4) if slippages else 0,
            accuracy_score=round(self.consistency_score(records), 4),
            per_symbol=per_symbol,
        )
