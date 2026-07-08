"""HTML 报告生成引擎。

提供统一的 HTML 模板、数据加载、图表渲染能力。
所有报告类型 (daily/weekly/monthly) 共用此模块。
"""

from __future__ import annotations

import csv
import json
from datetime import date, datetime
from pathlib import Path

# ── 路径常量 ──────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = PROJECT_ROOT / "logs"
REPORT_DIR = LOG_DIR / "reports"
STATE_FILE = PROJECT_ROOT / "daemon_state.json"
TRACKER_FILE = LOG_DIR / "tracker.json"
PARAMS_FILE = LOG_DIR / "strategy_params.json"


# ── 数据加载 ──────────────────────────────────────────────────────


def load_state() -> dict:
    """加载 daemon_state.json。"""
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def load_tracker() -> list[dict]:
    """加载 tracker.json 预测追踪表。"""
    if TRACKER_FILE.exists():
        try:
            data = json.loads(TRACKER_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


def load_strategy_params() -> dict:
    """加载 strategy_params.json。"""
    if PARAMS_FILE.exists():
        try:
            data = json.loads(PARAMS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def load_trades_csv(symbol: str) -> list[dict]:
    """加载 trades_{symbol}.csv 交易记录。"""
    csv_path = LOG_DIR / f"trades_{symbol}.csv"
    if not csv_path.exists():
        return []
    rows = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def load_decisions_csv(symbol: str = "") -> list[dict]:
    """加载 decisions CSV。如指定 symbol 则过滤。"""
    results = []
    for p in LOG_DIR.glob("decisions_*.csv"):
        try:
            with open(p, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if symbol and row.get("symbol") != symbol:
                        continue
                    results.append(row)
        except Exception:
            continue
    return results


def filter_tracker_by_date(records: list[dict], start: str, end: str) -> list[dict]:
    """按日期范围过滤 tracker 记录。"""
    return [r for r in records if start <= r.get("date", "") <= end]


def compute_prediction_summary(records: list[dict]) -> dict:
    """计算预测统计摘要。"""
    verified = [r for r in records if r.get("verified") and r.get("was_correct") is not None]
    correct = [r for r in verified if r["was_correct"]]
    total = len(records)
    n_verified = len(verified)
    n_correct = len(correct)

    # 按信号分组
    by_signal: dict[str, dict] = {}
    for sig in ["BUY", "SELL", "HOLD", "LONG", "SHORT", "NEUTRAL"]:
        subset = [r for r in verified if r.get("signal") == sig]
        if subset:
            c = sum(1 for r in subset if r["was_correct"])
            by_signal[sig] = {"total": len(subset), "correct": c, "accuracy": round(c / len(subset), 3)}

    # 按卦象分组
    by_hexagram: dict[str, dict] = {}
    for h in ["吉", "平", "凶", "注意"]:
        subset = [r for r in verified if r.get("hexagram_sent") == h]
        if subset:
            c = sum(1 for r in subset if r["was_correct"])
            by_hexagram[h] = {"total": len(subset), "correct": c, "accuracy": round(c / len(subset), 3)}

    return {
        "total": total,
        "verified": n_verified,
        "correct": n_correct,
        "accuracy": round(n_correct / n_verified, 3) if n_verified > 0 else 0.0,
        "by_signal": by_signal,
        "by_hexagram": by_hexagram,
    }


def compute_trade_summary(state: dict, trades_csv: list[dict] | None = None) -> dict:
    """汇总交易绩效。优先用 trades CSV，回退到 daemon_state。"""
    if trades_csv:
        total_trades = len(trades_csv)
        wins = sum(1 for t in trades_csv if float(t.get("pnl", 0)) > 0)
        total_pnl = sum(float(t.get("pnl", 0)) for t in trades_csv)
        win_rate = wins / total_trades if total_trades > 0 else 0.0
        avg_pnl = total_pnl / total_trades if total_trades > 0 else 0.0
        avg_win = (
            (sum(float(t.get("pnl", 0)) for t in trades_csv if float(t.get("pnl", 0)) > 0) / wins) if wins > 0 else 0.0
        )
        losses = [t for t in trades_csv if float(t.get("pnl", 0)) <= 0]
        avg_loss = (sum(float(t.get("pnl", 0)) for t in losses) / len(losses)) if losses else 0.0
        return {
            "total_trades": total_trades,
            "wins": wins,
            "losses": len(losses),
            "win_rate": round(win_rate, 3),
            "total_pnl": round(total_pnl, 2),
            "avg_pnl": round(avg_pnl, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(avg_win / abs(avg_loss), 2) if avg_loss != 0 else float("inf"),
        }

    # 回退到 daemon_state
    total = state.get("total_trades", 0)
    pnl = state.get("total_pnl", 0.0)
    return {
        "total_trades": total,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "total_pnl": round(pnl, 2),
        "avg_pnl": round(pnl / total, 2) if total > 0 else 0.0,
        "avg_win": 0.0,
        "avg_loss": 0.0,
        "profit_factor": 0.0,
    }


# ── HTML 模板 ─────────────────────────────────────────────────────

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
:root {{
  --bg: #0d1117; --surface: #161b22; --border: #30363d;
  --text: #e6edf3; --text2: #8b949e; --accent: #58a6ff;
  --green: #3fb950; --red: #f85149; --yellow: #d29922;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif;
       background: var(--bg); color: var(--text); line-height: 1.6; padding: 24px; }}
.container {{ max-width: 960px; margin: 0 auto; }}
h1 {{ font-size: 1.6em; margin-bottom: 8px; color: var(--accent); }}
h2 {{ font-size: 1.2em; margin: 20px 0 10px; color: var(--text2); border-bottom: 1px solid var(--border); padding-bottom: 4px; }}
h3 {{ font-size: 1.0em; margin: 12px 0 6px; color: var(--text2); }}
.meta {{ color: var(--text2); font-size: 0.85em; margin-bottom: 16px; }}
.card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; margin-bottom: 12px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 16px; }}
.stat-box {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 14px; text-align: center; }}
.stat-box .label {{ font-size: 0.8em; color: var(--text2); }}
.stat-box .value {{ font-size: 1.5em; font-weight: 700; margin-top: 2px; }}
.positive {{ color: var(--green); }}
.negative {{ color: var(--red); }}
.neutral {{ color: var(--yellow); }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.9em; }}
th, td {{ padding: 8px 10px; text-align: left; border-bottom: 1px solid var(--border); }}
th {{ color: var(--text2); font-weight: 600; font-size: 0.8em; text-transform: uppercase; }}
tr:hover {{ background: rgba(88,166,255,0.05); }}
.bar {{ height: 6px; border-radius: 3px; background: var(--border); overflow: hidden; }}
.bar-fill {{ height: 100%; border-radius: 3px; transition: width 0.3s; }}
.footer {{ margin-top: 24px; padding-top: 12px; border-top: 1px solid var(--border);
           color: var(--text2); font-size: 0.8em; text-align: center; }}
</style>
</head>
<body>
<div class="container">
  <h1>{title}</h1>
  <div class="meta">{subtitle} | 生成时间: {generated_at}</div>
  {content}
  <div class="footer">Quant Trader 自动报告系统 | {generated_at}</div>
</div>
</body>
</html>
"""


# ── 辅助渲染函数 ──────────────────────────────────────────────────


def stat_box(label: str, value: str, cls: str = "") -> str:
    """渲染一个统计卡片。"""
    return f'<div class="stat-box"><div class="label">{label}</div><div class="value {cls}">{value}</div></div>'


def pnl_class(value: float) -> str:
    """根据盈亏返回 CSS 类名。"""
    if value > 0:
        return "positive"
    elif value < 0:
        return "negative"
    return "neutral"


def pct_str(value: float) -> str:
    """百分比格式化。"""
    return f"{value * 100:+.2f}%" if isinstance(value, float) and abs(value) < 10 else f"{value:.2f}%"


def money_str(value: float) -> str:
    """金额格式化。"""
    return f"{'+' if value > 0 else ''}{value:,.2f}"


def accuracy_bar(accuracy: float) -> str:
    """渲染准确率进度条。"""
    pct = accuracy * 100
    cls = "positive" if accuracy >= 0.6 else ("negative" if accuracy < 0.4 else "neutral")
    return (
        f'<div class="bar"><div class="bar-fill {cls}" '
        f'style="width:{pct:.0f}%"></div></div>'
        f'<span style="font-size:0.8em;color:var(--text2)"> {pct:.1f}%</span>'
    )


def render_table(headers: list[str], rows: list[list[str]], classes: list[str] | None = None) -> str:
    """渲染 HTML 表格。"""
    cls_attr = f' class="{classes[0]}"' if classes else ""
    thead = "<tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>"
    tbody = []
    for row in rows:
        tr = "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>"
        tbody.append(tr)
    return f"<table{cls_attr}><thead>{thead}</thead><tbody>{''.join(tbody)}</tbody></table>"


def render_report(title: str, subtitle: str, content: str) -> str:
    """组装完整 HTML。"""
    return HTML_TEMPLATE.format(
        title=title,
        subtitle=subtitle,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        content=content,
    )


def save_report(html: str, filename: str) -> Path:
    """保存 HTML 报告到 logs/reports/，返回路径。"""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / filename
    path.write_text(html, encoding="utf-8")
    return path


# ── 报告基类 ──────────────────────────────────────────────────────


class ReportGenerator:
    """统一报告生成入口 — 根据类型生成日/周/月报告。"""

    @staticmethod
    def daily(target_date: date | None = None) -> Path:
        from .daily import DailyReport

        return DailyReport(target_date).generate()

    @staticmethod
    def weekly(target_date: date | None = None) -> Path:
        from .weekly import WeeklyReport

        return WeeklyReport(target_date).generate()

    @staticmethod
    def monthly(target_date: date | None = None) -> Path:
        from .monthly import MonthlyReport

        return MonthlyReport(target_date).generate()

    @staticmethod
    def all(target_date: date | None = None) -> dict[str, Path]:
        """一次生成日/周/月三份报告，返回路径字典。"""
        from .daily import DailyReport
        from .monthly import MonthlyReport
        from .weekly import WeeklyReport

        d = DailyReport(target_date).generate()
        w = WeeklyReport(target_date).generate()
        m = MonthlyReport(target_date).generate()
        return {"daily": d, "weekly": w, "monthly": m}


class BaseReport:
    """报告基类 — 子类实现 build_content()。"""

    report_type: str = "base"

    def __init__(self, target_date: date | None = None):
        self.target_date = target_date or date.today()
        self.state = load_state()
        self.tracker = load_tracker()
        self.params = load_strategy_params()

    def build_content(self) -> str:
        raise NotImplementedError

    def generate(self) -> Path:
        """生成报告并保存，返回文件路径。"""
        html = render_report(
            title=self._title(),
            subtitle=self._subtitle(),
            content=self.build_content(),
        )
        filename = f"{self.report_type}_{self.target_date.isoformat()}.html"
        return save_report(html, filename)

    def generate_html(self) -> str:
        """仅返回 HTML，不写文件。"""
        return render_report(
            title=self._title(),
            subtitle=self._subtitle(),
            content=self.build_content(),
        )

    def _title(self) -> str:
        return f"Quant Trader {self.report_type.upper()} 报告"

    def _subtitle(self) -> str:
        return f"日期: {self.target_date.isoformat()}"
