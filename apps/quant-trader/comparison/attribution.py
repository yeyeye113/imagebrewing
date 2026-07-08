"""归因分析 — 拆解回测与模拟收益差异的来源。"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .recorder import ComparisonRecord, TradeRecorder


@dataclass
class AttributionEntry:
    """单笔交易归因 — 拆解收益差异来源。"""

    decision_id: str = ""
    symbol: str = ""
    # 差异总量
    total_gap: float = 0.0  # sim_pnl - backtest_pnl
    # 归因因子
    slippage_cost: float = 0.0  # 滑点造成的差异
    timing_cost: float = 0.0  # 入场/出场时机差异
    decision_quality: float = 0.0  # 决策质量 (置信度 vs 结果)
    regime_effect: float = 0.0  # 市场环境变化影响
    fee_drag: float = 0.0  # 费用拖累
    # 标签
    primary_driver: str = ""  # 主要差异来源标签
    severity: str = ""  # LOW / MEDIUM / HIGH


@dataclass
class AttributionSummary:
    """归因汇总 — 各因子的系统性影响。"""

    total_trades: int = 0
    avg_gap: float = 0.0  # 平均每笔差异
    # 因子汇总
    total_slippage_cost: float = 0.0
    total_timing_cost: float = 0.0
    total_fee_drag: float = 0.0
    avg_decision_quality: float = 0.0
    # 主要驱动因子
    dominant_factor: str = ""  # 最大影响因子
    factor_breakdown: dict = field(default_factory=dict)  # factor -> total
    # 建议
    recommendations: list = field(default_factory=list)


class AttributionAnalyzer:
    """归因分析引擎 — 自动拆解回测 vs 模拟差异来源。"""

    # 归因阈值
    SLIPPAGE_THRESHOLD = 0.001  # 滑点超过 0.1% 视为显著
    TIMING_THRESHOLD = 0.002  # 时机差异超过 0.2%
    DECISION_THRESHOLD = 0.3  # 置信度差距阈值

    def __init__(self, recorder: TradeRecorder):
        self.recorder = recorder

    def analyze_trade(self, record: ComparisonRecord) -> AttributionEntry:
        """单笔交易归因分析。"""
        d, s = record.decision, record.simulation
        total_gap = s.pnl - s.backtest_pnl

        # 1. 滑点成本: 直接用记录的滑点
        slippage_cost = abs(s.slippage) * s.qty if s.slippage else 0.0

        # 2. 时机成本: 模拟入场价与回测入场价的差异
        entry_diff = abs(s.entry_price - d.backtest_price) if d.backtest_price else 0.0
        timing_cost = entry_diff * s.qty * (1 if s.pnl > 0 else -1)

        # 3. 决策质量: 置信度高但亏损 → 负; 置信度低但盈利 → 正
        if d.confidence > 0 and d.backtest_confidence > 0:
            conf_delta = d.confidence - d.backtest_confidence
            decision_quality = conf_delta * abs(total_gap)
        else:
            decision_quality = 0.0

        # 4. 费用拖累
        fee_drag = -s.total_fees

        # 5. 市场环境: 剩余未解释部分
        explained = slippage_cost + timing_cost + fee_drag
        regime_effect = total_gap - explained

        # 确定主要驱动因子
        factors = {
            "滑点": abs(slippage_cost),
            "时机": abs(timing_cost),
            "费用": abs(fee_drag),
            "市场环境": abs(regime_effect),
        }
        dominant = max(factors, key=lambda k: factors[k]) if factors else "未知"

        # 严重程度
        gap_pct = abs(total_gap) / abs(s.backtest_pnl) if s.backtest_pnl else 0
        if gap_pct > 0.1:
            severity = "HIGH"
        elif gap_pct > 0.03:
            severity = "MEDIUM"
        else:
            severity = "LOW"

        return AttributionEntry(
            decision_id=d.id,
            symbol=d.symbol,
            total_gap=round(total_gap, 4),
            slippage_cost=round(slippage_cost, 4),
            timing_cost=round(timing_cost, 4),
            decision_quality=round(decision_quality, 4),
            regime_effect=round(regime_effect, 4),
            fee_drag=round(fee_drag, 4),
            primary_driver=dominant,
            severity=severity,
        )

    def analyze_all(self) -> list[AttributionEntry]:
        """全量归因分析。"""
        records = self.recorder.load_all()
        return [self.analyze_trade(r) for r in records]

    def summary(self) -> AttributionSummary:
        """归因汇总 — 系统性分析。"""
        entries = self.analyze_all()
        if not entries:
            return AttributionSummary()

        n = len(entries)
        total_gap = sum(e.total_gap for e in entries)

        # 因子汇总
        total_slippage = sum(e.slippage_cost for e in entries)
        total_timing = sum(e.timing_cost for e in entries)
        total_fee = sum(e.fee_drag for e in entries)
        avg_quality = np.mean([e.decision_quality for e in entries])

        # 主导因子
        factor_totals = {
            "滑点": abs(total_slippage),
            "时机": abs(total_timing),
            "费用": abs(total_fee),
        }
        dominant = max(factor_totals, key=lambda k: factor_totals[k]) if factor_totals else "未知"

        # 自动生成建议
        recs = self._generate_recommendations(entries, total_slippage, total_timing, total_fee)

        return AttributionSummary(
            total_trades=n,
            avg_gap=round(total_gap / n, 4) if n else 0,
            total_slippage_cost=round(total_slippage, 4),
            total_timing_cost=round(total_timing, 4),
            total_fee_drag=round(total_fee, 4),
            avg_decision_quality=round(float(avg_quality), 4),
            dominant_factor=dominant,
            factor_breakdown={
                "滑点": round(total_slippage, 4),
                "时机": round(total_timing, 4),
                "费用": round(total_fee, 4),
            },
            recommendations=recs,
        )

    def by_symbol(self) -> dict[str, AttributionSummary]:
        """按标的归因汇总。"""
        records = self.recorder.load_all()
        symbols = set(r.decision.symbol for r in records)
        result = {}
        for sym in symbols:
            sym_records = [r for r in records if r.decision.symbol == sym]
            sym_entries = [self.analyze_trade(r) for r in sym_records]
            result[sym] = self._summarize_entries(sym_entries)
        return result

    # ── 内部 ─────────────────────────────────────────────────────────

    def _summarize_entries(self, entries: list[AttributionEntry]) -> AttributionSummary:
        if not entries:
            return AttributionSummary()
        n = len(entries)
        total_gap = sum(e.total_gap for e in entries)
        total_slippage = sum(e.slippage_cost for e in entries)
        total_timing = sum(e.timing_cost for e in entries)
        total_fee = sum(e.fee_drag for e in entries)
        return AttributionSummary(
            total_trades=n,
            avg_gap=round(total_gap / n, 4),
            total_slippage_cost=round(total_slippage, 4),
            total_timing_cost=round(total_timing, 4),
            total_fee_drag=round(total_fee, 4),
            avg_decision_quality=round(float(np.mean([e.decision_quality for e in entries])), 4),
            factor_breakdown={
                "滑点": round(total_slippage, 4),
                "时机": round(total_timing, 4),
                "费用": round(total_fee, 4),
            },
        )

    def _generate_recommendations(
        self,
        entries: list[AttributionEntry],
        total_slippage: float,
        total_timing: float,
        total_fee: float,
    ) -> list[str]:
        recs: list[str] = []
        n = len(entries)
        if n == 0:
            return recs

        # 滑点分析
        avg_slip = abs(total_slippage) / n if n else 0
        if avg_slip > 50:
            recs.append(f"平均滑点成本 {avg_slip:.1f} 元偏高，建议优化入场时机或使用限价单")

        # 时机分析
        avg_timing = abs(total_timing) / n if n else 0
        if avg_timing > 30:
            recs.append(f"入场/出场时机差异 {avg_timing:.1f} 元，建议调整信号触发条件")

        # 费用分析
        fee_pct = abs(total_fee) / abs(total_slippage + total_timing + total_fee + 0.01)
        if fee_pct > 0.15:
            recs.append("费用占比超 15%，建议检查佣金费率或减少交易频率")

        # 置信度分析
        high_conf_bad = sum(1 for e in entries if e.decision_quality < -10 and e.severity == "HIGH")
        if high_conf_bad > n * 0.2:
            recs.append(f"高置信度亏损占比 {high_conf_bad}/{n}，LLM 判断质量需关注")

        # 一致性
        agree = sum(1 for e in entries if e.total_gap > 0 or abs(e.total_gap) < 1)
        if agree / n < 0.6:
            recs.append(f"方向一致性仅 {agree}/{n}，回测与模拟信号偏差较大")

        if not recs:
            recs.append("各项指标正常，无需特别调整")

        return recs
