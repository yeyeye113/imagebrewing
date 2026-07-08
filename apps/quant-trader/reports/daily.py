"""每日交易报告 — 单日预测、交易、盈亏汇总。"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .generator import (
    LOG_DIR,
    BaseReport,
    compute_prediction_summary,
    load_tracker,
    load_trades_csv,
    money_str,
    pnl_class,
    render_table,
    stat_box,
)


class DailyReport(BaseReport):
    """每日报告: 预测准确率 + 交易绩效 + 持仓状态。"""

    report_type = "daily"

    def _title(self) -> str:
        return f"每日交易报告 — {self.target_date.isoformat()}"

    def _subtitle(self) -> str:
        dow_map = {0: "一", 1: "二", 2: "三", 3: "四", 4: "五", 5: "六", 6: "日"}
        dow = dow_map.get(self.target_date.weekday(), "")
        return f"{self.target_date.isoformat()} 星期{dow}"

    def build_content(self) -> str:
        parts: list[str] = []
        today_str = self.target_date.isoformat()

        # ── 1. 核心指标卡片 ──
        parts.append(self._section_overview(today_str))

        # ── 2. 今日预测明细 ──
        parts.append(self._section_predictions(today_str))

        # ── 3. 今日交易明细 ──
        parts.append(self._section_trades(today_str))

        # ── 4. 策略参数状态 ──
        parts.append(self._section_params())

        # ── 5. 近7天准确率趋势 ──
        parts.append(self._section_accuracy_trend())

        return "\n".join(parts)

    # ── 各区块 ──────────────────────────────────────────────────

    def _section_overview(self, today: str) -> str:
        """核心指标卡片。"""
        records = [r for r in self.tracker if r.get("date") == today]
        summary = compute_prediction_summary(records)
        state = self.state

        # 今日 PnL
        day_pnl = state.get("day_pnl", 0.0)
        total_pnl = state.get("total_pnl", 0.0)
        day_trades = state.get("day_trades", 0)
        total_trades = state.get("total_trades", 0)
        consecutive = state.get("consecutive_losses", 0)

        win_rate = summary["accuracy"]
        verified = summary["verified"]
        correct = summary["correct"]

        cards = []
        cards.append(stat_box("今日预测", f"{summary['total']}条"))
        cards.append(stat_box("已验证", f"{verified}条"))
        cards.append(stat_box("准确率", f"{win_rate * 100:.1f}%", pnl_class(win_rate - 0.5)))
        cards.append(stat_box("今日交易", f"{day_trades}笔"))
        cards.append(stat_box("今日盈亏", money_str(day_pnl), pnl_class(day_pnl)))
        cards.append(stat_box("累计盈亏", money_str(total_pnl), pnl_class(total_pnl)))
        cards.append(stat_box("累计交易", f"{total_trades}笔"))
        cards.append(stat_box("连续亏损", f"{consecutive}笔", "negative" if consecutive >= 2 else ""))

        return f'<h2>核心指标</h2><div class="grid">{"".join(cards)}</div>'

    def _section_predictions(self, today: str) -> str:
        """今日预测明细表格。"""
        records = [r for r in self.tracker if r.get("date") == today]
        if not records:
            return '<h2>今日预测</h2><div class="card">今日暂无预测记录。</div>'

        headers = ["标的", "市场", "信号", "置信度", "预测价", "状态", "实际涨跌"]
        rows = []
        for r in records:
            status = ""
            change = ""
            if r.get("verified"):
                if r.get("was_correct") is True:
                    status = '<span class="positive">正确</span>'
                elif r.get("was_correct") is False:
                    status = '<span class="negative">错误</span>'
                else:
                    status = '<span class="neutral">待定</span>'
                change = f"{r.get('actual_change_pct', 0):+.2f}%"
            else:
                status = '<span class="neutral">未验证</span>'
                change = "-"

            rows.append(
                [
                    r.get("symbol", ""),
                    r.get("market", ""),
                    r.get("signal", ""),
                    f"{r.get('confidence', 0):.0%}",
                    f"{r.get('forecast_price', 0):,.2f}",
                    status,
                    change,
                ]
            )

        table = render_table(headers, rows)
        return f'<h2>今日预测明细</h2><div class="card">{table}</div>'

    def _section_trades(self, today: str) -> str:
        """今日交易记录。"""
        # 搜索所有可能的 trades CSV
        all_trades = []
        for csv_path in LOG_DIR.glob("trades_*.csv"):
            try:
                trades = load_trades_csv(csv_path.stem.replace("trades_", ""))
                for t in trades:
                    entered = t.get("entered_at", "")
                    if today in entered:
                        all_trades.append(t)
            except Exception:
                continue

        if not all_trades:
            return '<h2>今日交易</h2><div class="card">今日暂无成交记录。</div>'

        headers = ["标的", "入场价", "出场价", "数量", "盈亏", "盈亏%", "退出原因", "LLM置信度"]
        rows = []
        for t in all_trades:
            pnl = float(t.get("pnl", 0))
            rows.append(
                [
                    t.get("symbol", ""),
                    f"{float(t.get('entry_price', 0)):,.2f}",
                    f"{float(t.get('exit_price', 0)):,.2f}",
                    t.get("qty", ""),
                    f'<span class="{pnl_class(pnl)}">{money_str(pnl)}</span>',
                    f"{float(t.get('pnl_pct', 0)) * 100:+.2f}%",
                    t.get("exit_reason", ""),
                    f"{float(t.get('llm_confidence', 0)):.0%}",
                ]
            )

        table = render_table(headers, rows)
        return f'<h2>今日交易明细</h2><div class="card">{table}</div>'

    def _section_params(self) -> str:
        """当前策略参数。"""
        p = self.params
        if not p:
            return '<h2>策略参数</h2><div class="card">暂无策略参数。</div>'

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

        return (
            f'<h2>策略参数状态</h2><div class="card"><ul style="list-style:none;padding:0">{"".join(items)}</ul></div>'
        )

    def _section_accuracy_trend(self) -> str:
        """近7天预测准确率趋势。"""

        records = load_tracker()

        days_data: list[dict[str, Any]] = []
        for i in range(6, -1, -1):
            d = (self.target_date - timedelta(days=i)).isoformat()
            day_recs = [r for r in records if r.get("date") == d]
            verified = [r for r in day_recs if r.get("verified") and r.get("was_correct") is not None]
            correct = sum(1 for r in verified if r["was_correct"])
            total = len(day_recs)
            n_verified = len(verified)
            acc = correct / n_verified if n_verified > 0 else None
            days_data.append(
                {
                    "date": d,
                    "total": total,
                    "verified": n_verified,
                    "correct": correct,
                    "accuracy": acc,
                }
            )

        headers = ["日期", "预测数", "已验证", "正确", "准确率"]
        rows = []
        for dd in days_data:
            d_label = dd["date"][5:]  # MM-DD
            acc_str = f"{dd['accuracy'] * 100:.1f}%" if dd["accuracy"] is not None else "-"
            rows.append(
                [
                    d_label,
                    str(dd["total"]),
                    str(dd["verified"]),
                    str(dd["correct"]),
                    acc_str,
                ]
            )

        table = render_table(headers, rows)
        return f'<h2>近7天准确率趋势</h2><div class="card">{table}</div>'


# ── 便捷函数 ──────────────────────────────────────────────────────


def generate_daily_report(target_date: date | None = None) -> Path:
    """生成每日报告并保存，返回文件路径。"""
    report = DailyReport(target_date)
    return report.generate()


def generate_daily_html(target_date: date | None = None) -> str:
    """生成每日报告 HTML（不保存）。"""
    report = DailyReport(target_date)
    return report.generate_html()


if __name__ == "__main__":
    path = generate_daily_report()
    print(f"报告已生成: {path}")
