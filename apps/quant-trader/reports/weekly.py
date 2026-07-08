"""每周交易报告 — 7天汇总、信号准确率对比、策略表现。"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

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


class WeeklyReport(BaseReport):
    """每周报告: 7天预测汇总 + 按标的/信号分组 + 策略参数变化。"""

    report_type = "weekly"

    def __init__(self, target_date: date | None = None):
        super().__init__(target_date)
        # 周一 = 本周起始
        self.week_start = self.target_date - timedelta(days=self.target_date.weekday())
        self.week_end = self.week_start + timedelta(days=6)

    def _title(self) -> str:
        return "每周交易报告"

    def _subtitle(self) -> str:
        return f"{self.week_start.isoformat()} ~ {self.week_end.isoformat()}"

    def build_content(self) -> str:
        parts: list[str] = []
        records = load_tracker()
        week_records = [
            r for r in records if self.week_start.isoformat() <= r.get("date", "") <= self.week_end.isoformat()
        ]

        # ── 1. 周度核心指标 ──
        parts.append(self._section_overview(week_records))

        # ── 2. 每日准确率对比 ──
        parts.append(self._section_daily_accuracy(week_records))

        # ── 3. 按标的分组统计 ──
        parts.append(self._section_by_symbol(week_records))

        # ── 4. 按信号分组统计 ──
        parts.append(self._section_by_signal(week_records))

        # ── 5. 策略参数变化 ──
        parts.append(self._section_params())

        return "\n".join(parts)

    # ── 各区块 ──────────────────────────────────────────────────

    def _section_overview(self, week_records: list[dict]) -> str:
        """周度核心指标卡片。"""
        summary = compute_prediction_summary(week_records)
        state = self.state

        total_pnl = state.get("total_pnl", 0.0)
        total_trades = state.get("total_trades", 0)

        # 周度 PnL（从 tracker 实际涨跌估算）
        verified = [r for r in week_records if r.get("verified") and r.get("was_correct") is not None]
        week_pnl_est = sum(r.get("actual_change_pct", 0) for r in verified) if verified else 0.0

        cards = []
        cards.append(stat_box("本周预测", f"{summary['total']}条"))
        cards.append(stat_box("已验证", f"{summary['verified']}条"))
        cards.append(stat_box("正确", f"{summary['correct']}条"))
        acc = summary["accuracy"]
        cards.append(stat_box("准确率", f"{acc * 100:.1f}%", pnl_class(acc - 0.5)))
        cards.append(stat_box("累计盈亏", money_str(total_pnl), pnl_class(total_pnl)))
        cards.append(stat_box("累计交易", f"{total_trades}笔"))

        return f'<h2>周度概览</h2><div class="grid">{"".join(cards)}</div>'

    def _section_daily_accuracy(self, week_records: list[dict]) -> str:
        """每天的准确率对比。"""
        days: list[dict[str, Any]] = []
        for i in range(7):
            d = (self.week_start + timedelta(days=i)).isoformat()
            day_recs = [r for r in week_records if r.get("date") == d]
            verified = [r for r in day_recs if r.get("verified") and r.get("was_correct") is not None]
            correct = sum(1 for r in verified if r["was_correct"])
            n_v = len(verified)
            n_t = len(day_recs)
            acc: float | None = correct / n_v if n_v > 0 else None
            days.append(
                {
                    "date": d[5:],  # MM-DD
                    "weekday": ["一", "二", "三", "四", "五", "六", "日"][i],
                    "total": n_t,
                    "verified": n_v,
                    "correct": correct,
                    "accuracy": acc,
                }
            )

        headers = ["日期", "星期", "预测数", "已验证", "正确", "准确率", "准确率图示"]
        rows: list[list[str]] = []
        for dd in days:
            acc_val = dd["accuracy"]
            acc_str = f"{acc_val * 100:.1f}%" if acc_val is not None else "-"
            bar = accuracy_bar(acc_val) if acc_val is not None else "-"
            rows.append(
                [
                    dd["date"],
                    dd["weekday"],
                    str(dd["total"]),
                    str(dd["verified"]),
                    str(dd["correct"]),
                    acc_str,
                    bar,
                ]
            )

        table = render_table(headers, rows)
        return f'<h2>每日准确率对比</h2><div class="card">{table}</div>'

    def _section_by_symbol(self, week_records: list[dict]) -> str:
        """按标的分组统计。"""
        verified = [r for r in week_records if r.get("verified") and r.get("was_correct") is not None]
        if not verified:
            return '<h2>按标的统计</h2><div class="card">本周暂无已验证预测。</div>'

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

        # 按准确率降序
        rows.sort(key=lambda x: float(x[3].replace("%", "")), reverse=True)
        table = render_table(headers, rows)
        return f'<h2>按标的统计</h2><div class="card">{table}</div>'

    def _section_by_signal(self, week_records: list[dict]) -> str:
        """按信号类型分组统计。"""
        summary = compute_prediction_summary(week_records)
        by_signal = summary.get("by_signal", {})

        if not by_signal:
            return '<h2>按信号统计</h2><div class="card">本周暂无已验证预测。</div>'

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


def generate_weekly_report(target_date: date | None = None) -> Path:
    """生成每周报告并保存，返回文件路径。"""
    report = WeeklyReport(target_date)
    return report.generate()


def generate_weekly_html(target_date: date | None = None) -> str:
    """生成每周报告 HTML（不保存）。"""
    report = WeeklyReport(target_date)
    return report.generate_html()


if __name__ == "__main__":
    path = generate_weekly_report()
    print(f"报告已生成: {path}")
