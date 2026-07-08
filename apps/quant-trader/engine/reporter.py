"""回测报告导出器 — 将回测结果输出为美观的 Markdown / HTML 表格。

Usage:
    from quanttrader.engine.reporter import report_markdown, report_html
    print(report_markdown(result))
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

_TR = """<tr>
<td align="left">{label}</td>
<td align="right">{value}</td>
</tr>"""

_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>回测报告 — {title}</title>
<style>
  body {{ font-family: -apple-system, 'Noto Sans SC', sans-serif; max-width: 860px; margin: 40px auto; padding: 0 20px; color: #1a1a2e; background: #f8f9fa; }}
  h1 {{ font-size: 24px; margin-bottom: 4px; }}
  .sub  {{ color: #6b7280; font-size: 14px; margin-bottom: 24px; }}
  .card {{ background: #fff; border-radius: 12px; padding: 20px 24px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }}
  h2   {{ font-size: 16px; margin: 0 0 12px; color: #374151; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  td:first-child {{ color: #6b7280; padding: 4px 0; }}
  td:last-child  {{ font-weight: 600; text-align: right; font-variant-numeric: tabular-nums; }}
  .pos {{ color: #16a34a; }}
  .neg {{ color: #dc2626; }}
  .risk-event {{ font-size: 12px; color: #b91c1c; background: #fef2f2; padding: 2px 8px; border-radius: 4px; margin: 2px; display: inline-block; }}
  hr {{ border: none; border-top: 1px solid #e5e7eb; margin: 16px 0; }}
</style></head>
<body>
"""


def _color_pct(value: float) -> str:
    """Return a CSS class for a percentage value."""
    if value > 0:
        return "pos"
    if value < 0:
        return "neg"
    return ""


def _pct(value: float) -> str:
    return f"{value * 100:,.2f}%"


def _money(value: float) -> str:
    return f"${value:,.2f}"


def _metric_row(label: str, value: str, css_class: str = "") -> str:
    if css_class:
        return f'<tr><td align="left">{label}</td><td align="right" class="{css_class}">{value}</td></tr>'
    return _TR.format(label=label, value=value)


def _equity_chart_svg(equity_curve, width: int = 760, height: int = 200) -> str:
    """Render a self-contained SVG equity + drawdown chart (no JS deps)."""
    if equity_curve is None or len(equity_curve) < 2:
        return "<p style='color:#9ca3af;font-size:13px;'>权益数据不足，无法绘制曲线。</p>"

    series = equity_curve.dropna()
    if len(series) < 2:
        return "<p style='color:#9ca3af;font-size:13px;'>权益数据不足，无法绘制曲线。</p>"

    values = series.astype(float).tolist()
    peak = values[0]
    drawdowns = []
    for v in values:
        peak = max(peak, v)
        drawdowns.append((v / peak - 1.0) if peak > 0 else 0.0)

    pad_x, pad_y = 8, 8
    inner_w = width - pad_x * 2
    inner_h = height - pad_y * 2
    eq_h = int(inner_h * 0.72)
    dd_h = inner_h - eq_h - 6

    vmin, vmax = min(values), max(values)
    if vmax == vmin:
        vmax = vmin + 1.0

    def _points(vals, h, invert=False):
        n = len(vals)
        if n < 2:
            return ""
        lo, hi = min(vals), max(vals)
        if hi == lo:
            hi = lo + 1.0
        pts = []
        for i, v in enumerate(vals):
            x = pad_x + inner_w * i / (n - 1)
            norm = (v - lo) / (hi - lo)
            y = pad_y + h - norm * h if not invert else pad_y + norm * h
            pts.append(f"{x:.1f},{y:.1f}")
        return " ".join(pts)

    eq_pts = _points(values, eq_h)
    dd_pts = _points(drawdowns, dd_h, invert=True)
    dd_y0 = pad_y + eq_h + 6

    start_eq = values[0]
    end_eq = values[-1]
    max_dd = min(drawdowns) * 100

    return f"""<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" role="img" aria-label="权益曲线">
  <rect x="0" y="0" width="{width}" height="{height}" fill="#fafafa" rx="8"/>
  <text x="{pad_x}" y="{pad_y + 12}" fill="#6b7280" font-size="11">权益 ${start_eq:,.0f} → ${end_eq:,.0f}</text>
  <polyline fill="none" stroke="#2563eb" stroke-width="2" points="{eq_pts}"/>
  <text x="{width - pad_x}" y="{pad_y + 12}" fill="#6b7280" font-size="11" text-anchor="end">最大回撤 {max_dd:.1f}%</text>
  <line x1="{pad_x}" y1="{dd_y0}" x2="{width - pad_x}" y2="{dd_y0}" stroke="#e5e7eb"/>
  <polyline fill="none" stroke="#dc2626" stroke-width="1.5" points="{_shift_y(dd_pts, dd_y0)}"/>
</svg>"""


def _shift_y(points: str, offset: float) -> str:
    shifted = []
    for pair in points.split():
        x, y = pair.split(",")
        shifted.append(f"{x},{float(y) + offset:.1f}")
    return " ".join(shifted)


def report_html(result, title: str = "回测报告") -> str:
    """Generate a self-contained HTML report from a BacktestResult."""
    stats = result.stats
    trade = getattr(result, "trade_stats", None)
    if trade is None and hasattr(result, "portfolio"):
        from .metrics import trade_stats as _trade_stats
        trade = _trade_stats(result.portfolio.fills)

    # --- header ---
    html = _HTML.format(title=title)
    html += f"<h1>{title}</h1><div class='sub'>{getattr(result, 'symbol', '')} &nbsp; {getattr(result, 'strategy', '')}</div>\n"

    # --- performance card ---
    html += '<div class="card"><h2>绩效指标</h2><table>\n'
    html += _metric_row("起始资金", _money(stats.get("start_equity", 0)))
    html += _metric_row("最终权益", _money(stats.get("end_equity", 0)))
    html += _metric_row("总收益", _pct(stats.get("total_return", 0)), _color_pct(stats.get("total_return", 0)))
    html += _metric_row("年化收益 CAGR", _pct(stats.get("cagr", 0)), _color_pct(stats.get("cagr", 0)))
    html += _metric_row("年化波动", _pct(stats.get("annual_vol", 0)))
    html += _metric_row("夏普比率", f"{stats.get('sharpe', 0):.2f}")
    html += _metric_row("索提诺比率", f"{stats.get('sortino', 0):.2f}")
    html += _metric_row("最大回撤", _pct(stats.get("max_drawdown", 0)), _color_pct(stats.get("max_drawdown", 0)))
    html += '</table></div>\n'

    # --- trade stats card ---
    if trade and trade.get("n_round_trips", 0) > 0:
        html += '<div class="card"><h2>交易统计</h2><table>\n'
        html += _metric_row("往返交易数", str(trade["n_round_trips"]))
        html += _metric_row("胜率", _pct(trade.get("win_rate", 0)))
        html += _metric_row("平均盈利", _money(trade.get("avg_win", 0)), "pos")
        html += _metric_row("平均亏损", _money(trade.get("avg_loss", 0)), "neg")
        html += _metric_row("盈亏比", f"{trade.get('payoff_ratio', 0):.2f}")
        html += _metric_row("盈利因子", f"{trade.get('profit_factor', 0):.2f}")
        html += '</table></div>\n'

    # --- risk events ---
    if result.risk_events:
        html += '<div class="card"><h2>风控事件</h2>\n'
        for ts, reason in result.risk_events:
            html += f'<span class="risk-event">{ts} &nbsp; {reason}</span>\n'
        html += '</div>\n'

    # --- equity chart ---
    html += '<div class="card"><h2>权益曲线</h2>\n'
    html += _equity_chart_svg(getattr(result, "equity_curve", None))
    html += '</div>\n'

    html += "</body></html>"
    return html


def report_markdown(result) -> str:
    """Generate a Markdown summary table from a BacktestResult."""
    stats = result.stats
    trade = getattr(result, "trade_stats", None)
    if trade is None and hasattr(result, "portfolio"):
        from .metrics import trade_stats as _trade_stats
        trade = _trade_stats(result.portfolio.fills)

    lines = [
        "## 回测报告",
        "",
        f"> 交易笔数: {result.n_trades}",
        "",
        "| 指标 | 数值 |",
        "|------|------|",
        f"| 起始资金 | {_money(stats.get('start_equity', 0))} |",
        f"| 最终权益 | {_money(stats.get('end_equity', 0))} |",
        f"| 总收益   | {_pct(stats.get('total_return', 0))} |",
        f"| 年化 CAGR | {_pct(stats.get('cagr', 0))} |",
        f"| 年化波动 | {_pct(stats.get('annual_vol', 0))} |",
        f"| 夏普比率 | {stats.get('sharpe', 0):.2f} |",
        f"| 索提诺   | {stats.get('sortino', 0):.2f} |",
        f"| 最大回撤 | {_pct(stats.get('max_drawdown', 0))} |",
        "",
    ]
    if trade and trade.get("n_round_trips", 0) > 0:
        lines += [
            "| 交易指标 | 数值 |",
            "|----------|------|",
            f"| 胜率     | {_pct(trade.get('win_rate', 0))} |",
            f"| 盈亏比   | {trade.get('payoff_ratio', 0):.2f} |",
            f"| 盈利因子 | {trade.get('profit_factor', 0):.2f} |",
            "",
        ]
    return "\n".join(lines)


def save_html_report(result, path: str | Path, title: str = "回测报告") -> Path:
    """Save an HTML report to disk. Returns the written path."""
    p = Path(path)
    p.write_text(report_html(result, title=title), encoding="utf-8")
    return p
