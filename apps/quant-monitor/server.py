"""
Quant Trading Monitor Dashboard — FastAPI Server
Serves a single-page dashboard and JSON API endpoints
reading from the quant-trader project data.
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

# 确保路径正确处理中文用户名
def _resolve_path(*parts):
    """安全解析路径，正确处理中文用户名。"""
    # 使用 os.path.expanduser 处理 ~ 和中文用户名
    base = os.path.expanduser("~")
    full = os.path.join(base, *parts) if parts else base
    return Path(full).resolve()

# 优先使用环境变量
if os.environ.get("QT_ROOT"):
    QT_ROOT = Path(os.environ["QT_ROOT"]).resolve()
else:
    # 向上查找 quant-trader 目录
    current = Path(__file__).resolve().parent
    for _ in range(5):
        qt_dir = current / "Archives" / "quant-trader.archived"
        if qt_dir.exists():
            QT_ROOT = qt_dir
            break
        current = current.parent
    else:
        # 回退到默认路径
        QT_ROOT = _resolve_path("Archives", "quant-trader.archived")

DAEMON_STATE = QT_ROOT / "daemon_state.json"
LOGS_DIR = QT_ROOT / "logs"
CONFIG_YAML = QT_ROOT / "config_llm.yaml"  # 使用实际的配置文件
CONFIG_BASE = QT_ROOT / "config_base.yaml"
CONFIG_LLM = QT_ROOT / "config_llm.yaml"
CONFIG_MIMO = QT_ROOT / "config_mimo.yaml"

app = FastAPI(title="Quant Monitor", docs_url=None, redoc_url=None)
_template_dir = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_template_dir))


# ── helpers ────────────────────────────────────────────────
def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge: override wins, recursively for nested dicts."""
    merged = dict(base)
    for k, v in override.items():
        if v is None:
            continue
        if isinstance(v, dict) and k in merged and isinstance(merged[k], dict):
            merged[k] = _deep_merge(merged[k], v)
        else:
            merged[k] = v
    return merged


def _read_yaml(path: Path) -> dict:
    """Read YAML with _extends support (single-level inheritance)."""
    try:
        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            return {}

        # Handle _extends
        extends = data.pop("_extends", None)
        if extends:
            base_path = path.parent / extends
            base = _read_yaml(base_path)
            data = _deep_merge(base, data)

        return data
    except Exception as e:
        print(f"[warn] Failed to read {path}: {e}")
        return {}


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[warn] Failed to read {path}: {e}")
        return {}


def _merge(base: dict, override: dict) -> dict:
    """Shallow merge: override wins."""
    merged = dict(base)
    for k, v in override.items():
        if v is not None:
            merged[k] = v
    return merged


def _tail_log(path: Path, n: int = 80) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-n:]
    except Exception:
        return []


def _latest_log() -> Path | None:
    logs = sorted(LOGS_DIR.glob("tracker_*.log"), key=lambda p: p.name, reverse=True)
    return logs[0] if logs else None


def _parse_signals(lines: list[str]) -> list[dict]:
    """Extract signal-like entries from log lines."""
    signals = []
    sig_re = re.compile(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*\|\s*(\w+)\s*\|(.*)"
    )
    for line in reversed(lines):
        m = sig_re.match(line.strip())
        if not m:
            continue
        ts, level, msg = m.group(1), m.group(2), m.group(3).strip()
        # classify signal type
        sig_type = "info"
        msg_lower = msg.lower()
        if any(w in msg_lower for w in ["买入", "buy", "做多", "long", "开仓"]):
            sig_type = "buy"
        elif any(w in msg_lower for w in ["卖出", "sell", "做空", "short", "平仓"]):
            sig_type = "sell"
        elif level == "WARNING":
            sig_type = "warning"
        elif level == "ERROR" or level == "CRITICAL":
            sig_type = "error"
        signals.append({
            "time": ts,
            "level": level,
            "message": msg,
            "type": sig_type,
        })
        if len(signals) >= 50:
            break
    return list(reversed(signals))


# ── HTML page ──────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(name="index.html", request=request)


# ── API endpoints ──────────────────────────────────────────
@app.get("/api/status")
async def api_status():
    state = _read_json(DAEMON_STATE)
    total = state.get("total_trades", 0)
    wins = state.get("wins", 0)
    losses = total - wins
    win_rate = (wins / total * 100) if total else 0.0
    return {
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 1),
        "total_pnl": state.get("total_pnl", 0.0),
        "day_trades": state.get("day_trades", 0),
        "day_pnl": state.get("day_pnl", 0.0),
        "peak_equity": state.get("peak_equity", 0),
        "consecutive_losses": state.get("consecutive_losses", 0),
        "last_decision": state.get("last_decision_at", ""),
        "halt_reason": state.get("halt_reason", ""),
        "date": state.get("date", ""),
        "server_time": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/signals")
async def api_signals():
    log_path = _latest_log()
    if not log_path:
        return {"signals": [], "log_file": None}
    lines = _tail_log(log_path, 200)
    return {
        "signals": _parse_signals(lines),
        "log_file": log_path.name,
    }


@app.get("/api/risk")
async def api_risk():
    cfg = _read_yaml(CONFIG_YAML)
    base = _read_yaml(CONFIG_BASE)
    merged = _merge(base, cfg)
    risk = merged.get("risk", {})
    sizing = merged.get("sizing", {})
    return {
        "stop_loss": risk.get("stop_loss", 0.08),
        "take_profit": risk.get("take_profit", 0.0),
        "trailing_stop": risk.get("trailing_stop", 0.15),
        "max_drawdown": risk.get("max_drawdown", 0.25),
        "risk_per_trade": risk.get("risk_per_trade", 0.01),
        "max_position_pct": sizing.get("max_position_pct", 0.30),
        "max_total_exposure": sizing.get("max_total_exposure", 0.80),
        "cash_reserve_pct": sizing.get("cash_reserve_pct", 0.20),
        "allow_leverage": sizing.get("allow_leverage", False),
    }


@app.get("/api/config")
async def api_config():
    cfg = _read_yaml(CONFIG_YAML)
    base = _read_yaml(CONFIG_BASE)
    merged = _merge(base, cfg)
    strategy = merged.get("strategy", {})
    scanner = merged.get("scanner", {})
    return {
        "symbol": merged.get("symbol", ""),
        "symbols": merged.get("symbols", []),
        "data_source": merged.get("data_source", ""),
        "broker": merged.get("broker", {}).get("name", ""),
        "cash": merged.get("cash", 0),
        "interval": merged.get("interval", ""),
        "horizon": merged.get("horizon", ""),
        "strategy_name": strategy.get("name", ""),
        "strategy_params": {k: v for k, v in strategy.items() if k != "name"},
        "scanner_enabled": scanner.get("use_ai", False),
        "scanner_top_n": scanner.get("top_n", 0),
        "ai_provider": scanner.get("ai_provider", ""),
        "commission": merged.get("commission", 0),
    }


@app.get("/api/errors")
async def api_errors():
    log_path = _latest_log()
    if not log_path:
        return {"errors": []}
    lines = _tail_log(log_path, 500)
    errors = []
    for line in lines:
        if "| ERROR " in line or "| CRITICAL " in line:
            m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*\|\s*(\w+)\s*\|(.*)", line.strip())
            if m:
                errors.append({"time": m.group(1), "level": m.group(2), "message": m.group(3).strip()})
    return {"errors": errors[-20:]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
