"""报告生成器 — 生成对比分析的文本/JSON报告。"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .analyzer import ComparisonAnalyzer, ComparisonResult
from .attribution import AttributionAnalyzer, AttributionSummary
from .recorder import TradeRecorder


class ComparisonReporter:
    """对比报告生成器 — 支持文本/JSON输出。"""

    def __init__(self, recorder: TradeRecorder):
        self.recorder = recorder
        self.analyzer = ComparisonAnalyzer(recorder)
        self.attribution = AttributionAnalyzer(recorder)

    def text_report(self, result: ComparisonResult | None = None) -> str:
        """生成纯文本报告。"""
        if result is None:
            result = self.analyzer.analyze_full()
        attr_summary = self.attribution.summary()
        return self._render_text(result, attr_summary)

    def json_report(self, result: ComparisonResult | None = None) -> dict:
        """生成 JSON 报告。"""
        if result is None:
            result = self.analyzer.analyze_full()
        attr_summary = self.attribution.summary()
        return {
            "generated_at": datetime.now().isoformat(),
            "comparison": asdict(result),
            "attribution": {
                "total_trades": attr_summary.total_trades,
                "avg_gap": attr_summary.avg_gap,
                "dominant_factor": attr_summary.dominant_factor,
                "factor_breakdown": attr_summary.factor_breakdown,
                "recommendations": attr_summary.recommendations,
            },
            "trade_level": self.analyzer.trade_level_comparison(),
            "summary": self.recorder.summary(),
        }

    def save_report(self, path: str | Path, fmt: str = "text") -> Path:
        """保存报告到文件。支持 text / json 格式。"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if fmt == "json":
            data = self.json_report()
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            path.write_text(self.text_report(), encoding="utf-8")
        return path

    def daily_report(self, date_str: str | None = None) -> str:
        """生成单日报告。"""
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
        records = self.recorder.get_by_date(date_str)
        if not records:
            return f"日期 {date_str} 无交易记录。"
        result = self.analyzer._compute_result(records, date_str)
        attr_summary = self._summarize_records(records)
        return self._render_text(result, attr_summary)

    def symbol_report(self, symbol: str) -> str:
        """生成单标的报告。"""
        result = self.analyzer.analyze_by_symbol(symbol)
        records = self.recorder.get_by_symbol(symbol)
        attr_summary = self._summarize_records(records) if records else AttributionSummary()
        return self._render_text(result, attr_summary)

    def quick_summary(self) -> str:
        """快速一行摘要。"""
        s = self.recorder.summary()
        if s["total"] == 0:
            return "暂无交易记录。"
        return (
            f"交易 {s['total']} 笔 | "
            f"胜率 {s['win_rate']:.1%} | "
            f"总盈亏 {s['total_pnl']:+.2f} | "
            f"平均滑点 {s['avg_slippage']:.4f}"
        )

    # ── 内部渲染 ─────────────────────────────────────────────────────

    def _render_text(self, result: ComparisonResult, attr: AttributionSummary) -> str:
        lines = []
        lines.append("=" * 60)
        lines.append(f"  实盘模拟对比报告 — {result.period}")
        lines.append(f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 60)
        lines.append("")

        # 汇总
        lines.append("─" * 40)
        lines.append("  总体对比")
        lines.append("─" * 40)
        lines.append(f"  交易笔数:       {result.total_trades}")
        lines.append(f"  回测总盈亏:     {result.backtest_total_pnl:+.2f}")
        lines.append(f"  模拟总盈亏:     {result.sim_total_pnl:+.2f}")
        lines.append(f"  盈亏差额:       {result.pnl_gap:+.2f}")
        lines.append("")
        lines.append(f"  回测胜率:       {result.backtest_win_rate:.1%}")
        lines.append(f"  模拟胜率:       {result.sim_win_rate:.1%}")
        lines.append(f"  胜率差:         {result.win_rate_gap:+.1%}")
        lines.append("")
        lines.append(f"  回测均盈亏%:    {result.backtest_avg_pnl_pct:.4%}")
        lines.append(f"  模拟均盈亏%:    {result.sim_avg_pnl_pct:.4%}")
        lines.append(f"  平均滑点:       {result.avg_slippage:.4f}")
        lines.append(f"  一致性评分:     {result.accuracy_score:.1%}")
        lines.append("")

        # 按标的
        if result.per_symbol:
            lines.append("─" * 40)
            lines.append("  按标的明细")
            lines.append("─" * 40)
            for sym, info in result.per_symbol.items():
                lines.append(f"  {sym}:")
                lines.append(
                    f"    笔数={info['trades']}  回测={info['backtest_pnl']:+.2f}  "
                    f"模拟={info['sim_pnl']:+.2f}  差={info['delta']:+.2f}  "
                    f"胜率={info['win_rate']:.1%}"
                )
            lines.append("")

        # 归因
        lines.append("─" * 40)
        lines.append("  归因分析")
        lines.append("─" * 40)
        if attr.total_trades > 0:
            lines.append(f"  主要差异来源:   {attr.dominant_factor}")
            lines.append(f"  滑点总成本:     {attr.total_slippage_cost:+.2f}")
            lines.append(f"  时机总成本:     {attr.total_timing_cost:+.2f}")
            lines.append(f"  费用总拖累:     {attr.total_fee_drag:+.2f}")
            lines.append(f"  平均决策质量:   {attr.avg_decision_quality:+.4f}")
            lines.append("")
            if attr.recommendations:
                lines.append("  建议:")
                for i, rec in enumerate(attr.recommendations, 1):
                    lines.append(f"    {i}. {rec}")
        else:
            lines.append("  无足够数据进行归因分析。")
        lines.append("")

        # 逐笔明细 (前 10 笔)
        trade_list = self.analyzer.trade_level_comparison()
        if trade_list:
            lines.append("─" * 40)
            lines.append("  逐笔对比 (前 10 笔)")
            lines.append("─" * 40)
            lines.append(f"  {'ID':<20} {'标的':<8} {'回测PnL':>10} {'模拟PnL':>10} {'差额':>10} {'滑点':>8}")
            lines.append("  " + "-" * 66)
            for t in trade_list[:10]:
                tid = t["id"][:18]
                lines.append(
                    f"  {tid:<20} {t['symbol']:<8} "
                    f"{t['backtest_pnl']:>+10.2f} {t['sim_pnl']:>+10.2f} "
                    f"{t['pnl_delta']:>+10.2f} {t['slippage']:>8.4f}"
                )
            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)

    def _summarize_records(self, records) -> AttributionSummary:
        """从一组 ComparisonRecord 生成归因汇总。"""
        entries = [self.attribution.analyze_trade(r) for r in records]
        return self.attribution._summarize_entries(entries)
