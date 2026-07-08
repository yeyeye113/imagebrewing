"""月度交易报告 — 全月汇总、策略绩效深度分析、自学习循环效果。"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from pathlib import Path

from .generator import (
    BaseReport,
    accuracy_bar,
    compute_prediction_summary,
    load_tracker,
    money_str,
    pnl_class,
    render_table,
    stat_box,
)


class MonthlyReport(BaseReport):
    """月度报告: 全月预测汇总 + 按周/标的/信号分组 + 策略自适应效果。"""

    report_type = "monthly"

    def __init__(self, target_date: date | None = None):
        super().__init__(target_date)
        self.year = self.target_date.year
        self.month = self.target_date.month
        _, last_day = calendar.monthrange(self.year, self.month)
        self.month_start = date(self.year, self.month, 1)
        self.month_end = date(self.year, self.month, last_day)

    def _title(self) -> str:
        return f"月度交易报告 — {self.year}年{self.month}月"

    def _subtitle(self) -> str:
        return f"{self.month_start.isoformat()} ~ {self.month_end.isoformat()}"

    def build_content(self) -> str:
        parts: list[str] = []
        records = load_tracker()
        month_records = [
            r for r in records if self.month_start.isoformat() <= r.get("date", "") <= self.month_end.isoformat()
        ]

        # ── 1. 月度核心指标 ──
        parts.append(self._section_overview(month_records))

        # ── 2. 每周准确率对比 ──
        parts.append(self._section_weekly_accuracy(month_records))

        # ── 3. 按标的分组统计 ──
        parts.append(self._section_by_symbol(month_records))

        # ── 4. 按信号分组统计 ──
        parts.append(self._section_by_signal(month_records))

        # ── 5. 按市场分组统计 ──
        parts.append(self._section_by_market(month_records))

        # ── 7. 策略自适应效果 ──
        parts.append(self._section_adaptive_effect(month_records))

        # ── 8. 策略参数 ──
        parts.append(self._section_params())

        return "\n".join(parts)

    # ── 各区块 ──────────────────────────────────────────────────

    def _section_overview(self, month_records: list[dict]) -> str:
        """月度核心指标卡片。"""
        summary = compute_prediction_summary(month_records)
        state = self.state

        total_pnl = state.get("total_pnl", 0.0)
        total_trades = state.get("total_trades", 0)

        # 月度统计
        verified = [r for r in month_records if r.get("verified") and r.get("was_correct") is not None]
        correct = [r for r in verified if r["was_correct"]]
        bullish_correct = sum(1 for r in correct if r.get("signal") in ("BUY", "LONG"))
        bearish_correct = sum(1 for r in correct if r.get("signal") in ("SELL", "SHORT"))

        # 月度参与天数
        active_days = len(set(r.get("date", "") for r in month_records))

        cards = []
        cards.append(stat_box("本月预测", f"{summary['total']}条"))
        cards.append(stat_box("已验证", f"{summary['verified']}条"))
        cards.append(stat_box("正确", f"{summary['correct']}条"))
        acc = summary["accuracy"]
        cards.append(stat_box("准确率", f"{acc * 100:.1f}%", pnl_class(acc - 0.5)))
        cards.append(stat_box("活跃天数", f"{active_days}天"))
        cards.append(stat_box("做多正确", f"{bullish_correct}"))
        cards.append(stat_box("做空正确", f"{bearish_correct}"))
        cards.append(stat_box("累计盈亏", money_str(total_pnl), pnl_class(total_pnl)))

        return f'<h2>月度概览</h2><div class="grid">{"".join(cards)}</div>'

    def _section_weekly_accuracy(self, month_records: list[dict]) -> str:
        """按周分组统计准确率。"""
        weeks: dict[int, list[dict]] = {}
        for r in month_records:
            d = r.get("date", "")
            if not d:
                continue
            try:
                dt = date.fromisoformat(d)
                # ISO week number
                week_num = dt.isocalendar()[1]
                weeks.setdefault(week_num, []).append(r)
            except ValueError:
                continue

        if not weeks:
            return '<h2>每周准确率</h2><div class="card">本月暂无预测数据。</div>'

        headers = ["周次", "预测数", "已验证", "正确", "准确率", "准确率图示"]
        rows = []
        for wk in sorted(weeks.keys()):
            recs = weeks[wk]
            summary = compute_prediction_summary(recs)
            acc = summary["accuracy"]
            rows.append(
                [
                    f"第{wk}周",
                    str(summary["total"]),
                    str(summary["verified"]),
                    str(summary["correct"]),
                    f"{acc * 100:.1f}%",
                    accuracy_bar(acc),
                ]
            )

        table = render_table(headers, rows)
        return f'<h2>每周准确率对比</h2><div class="card">{table}</div>'

    def _section_by_symbol(self, month_records: list[dict]) -> str:
        """按标的分组统计。"""
        verified = [r for r in month_records if r.get("verified") and r.get("was_correct") is not None]
        if not verified:
            return '<h2>按标的统计</h2><div class="card">本月暂无已验证预测。</div>'

        symbols: dict[str, list[dict]] = {}
        for r in verified:
            sym = r.get("symbol", "未知")
            symbols.setdefault(sym, []).append(r)

        headers = ["标的", "预测数", "正确", "准确率", "平均涨跌%", "准确率图示"]
        rows = []
        for sym in sorted(symbols.keys()):
            recs = symbols[sym]
            n = len(recs)
            c = sum(1 for r in recs if r["was_correct"])
            acc = c / n if n > 0 else 0
            avg_chg = sum(r.get("actual_change_pct", 0) for r in recs) / n
            rows.append(
                [
                    sym,
                    str(n),
                    str(c),
                    f"{acc * 100:.1f}%",
                    f"{avg_chg:+.2f}%",
                    accuracy_bar(acc),
                ]
            )

        rows.sort(key=lambda x: float(x[3].replace("%", "")), reverse=True)
        table = render_table(headers, rows)
        return f'<h2>按标的统计</h2><div class="card">{table}</div>'

    def _section_by_signal(self, month_records: list[dict]) -> str:
        """按信号类型分组统计。"""
        summary = compute_prediction_summary(month_records)
        by_signal = summary.get("by_signal", {})

        if not by_signal:
            return '<h2>按信号统计</h2><div class="card">本月暂无已验证预测。</div>'

        headers = ["信号", "预测数", "正确", "准确率", "准确率图示"]
        rows = []
        for sig in ["BUY", "LONG", "SELL", "SHORT", "HOLD", "NEUTRAL"]:
            if sig not in by_signal:
                continue
            s = by_signal[sig]
            rows.append(
                [
                    sig,
                    str(s["total"]),
                    str(s["correct"]),
                    f"{s['accuracy'] * 100:.1f}%",
                    accuracy_bar(s["accuracy"]),
                ]
            )

        table = render_table(headers, rows)
        return f'<h2>按信号统计</h2><div class="card">{table}</div>'

    def _section_by_market(self, month_records: list[dict]) -> str:
        """按市场分组统计。"""
        verified = [r for r in month_records if r.get("verified") and r.get("was_correct") is not None]
        if not verified:
            return '<h2>按市场统计</h2><div class="card">暂无数据。</div>'

        markets: dict[str, list[dict]] = {}
        for r in verified:
            mkt = r.get("market", "未知")
            markets.setdefault(mkt, []).append(r)

        headers = ["市场", "预测数", "正确", "准确率"]
        rows = []
        for mkt in sorted(markets.keys()):
            recs = markets[mkt]
            n = len(recs)
            c = sum(1 for r in recs if r["was_correct"])
            acc = c / n if n > 0 else 0
            rows.append([mkt, str(n), str(c), f"{acc * 100:.1f}%"])

        table = render_table(headers, rows)
        return f'<h2>按市场统计</h2><div class="card">{table}</div>'

    def _section_adaptive_effect(self, month_records: list[dict]) -> str:
        """分析策略自适应效果 — 前半月 vs 后半月准确率对比。"""
        verified = [r for r in month_records if r.get("verified") and r.get("was_correct") is not None]
        if len(verified) < 4:
            return '<h2>自适应效果</h2><div class="card">数据不足，无法分析自适应效果。</div>'

        mid_day = self.month_start + timedelta(days=15)
        first_half = [r for r in verified if r.get("date", "") < mid_day.isoformat()]
        second_half = [r for r in verified if r.get("date", "") >= mid_day.isoformat()]

        def _acc(recs: list[dict]) -> float:
            if not recs:
                return 0.0
            return sum(1 for r in recs if r["was_correct"]) / len(recs)

        acc1 = _acc(first_half)
        acc2 = _acc(second_half)
        delta = acc2 - acc1

        trend = "提升" if delta > 0 else ("下降" if delta < 0 else "持平")
        trend_cls = pnl_class(delta) if delta != 0 else ""

        cards = []
        cards.append(stat_box("上半月准确率", f"{acc1 * 100:.1f}%"))
        cards.append(stat_box("下半月准确率", f"{acc2 * 100:.1f}%"))
        cards.append(stat_box("变化", f"{delta * 100:+.1f}%", trend_cls))
        cards.append(stat_box("趋势", trend))

        return (
            "<h2>策略自适应效果</h2>"
            '<p style="color:var(--text2);font-size:0.85em;margin-bottom:8px">'
            "对比上半月与下半月准确率，评估自学习循环是否有效。</p>"
            f'<div class="grid">{"".join(cards)}</div>'
        )

    def _section_params(self) -> str:
        """当前策略参数。"""
        p = self.params
        if not p:
            return ""

        items = []
        if "llm_temperature" in p:
            items.append(f"<li>LLM 温度: <b>{p['llm_temperature']}</b></li>")
        if "min_confidence" in p:
            items.append(f"<li>最低置信度: <b>{p['min_confidence']:.0%}</b></li>")
        if "stop_loss_pct" in p:
            items.append(f"<li>止损阈值: <b>{p['stop_loss_pct']:.0%}</b></li>")
        if "based_on" in p:
            items.append(f"<li>基于: {p['based_on']}</li>")
        if "updated_at" in p:
            items.append(f"<li>更新时间: {p['updated_at']}</li>")

        return f'<h2>策略参数</h2><div class="card"><ul style="list-style:none;padding:0">{"".join(items)}</ul></div>'


# ── 便捷函数 ──────────────────────────────────────────────────────


def generate_monthly_report(target_date: date | None = None) -> Path:
    """生成月度报告并保存，返回文件路径。"""
    report = MonthlyReport(target_date)
    return report.generate()


def generate_monthly_html(target_date: date | None = None) -> str:
    """生成月度报告 HTML（不保存）。"""
    report = MonthlyReport(target_date)
    return report.generate_html()


if __name__ == "__main__":
    path = generate_monthly_report()
    print(f"报告已生成: {path}")
