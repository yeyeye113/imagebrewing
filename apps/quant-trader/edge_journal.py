"""Edge setup 台账 — 记录 / 回填 / 按 setup 统计方向准确率，驱动 SETUP_MIN_SCORES 渐进微调."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .direction_edge import SETUP_MIN_SCORES, find_best_edge_setup
from .log import get_logger

logger = get_logger("edge_journal")

_DEFAULT_DIR = Path(__file__).resolve().parent / "prediction_logs"
_JOURNAL_FILE = "edge_journal.jsonl"
_THRESH_FILE = "edge_setup_thresholds.json"


@dataclass
class EdgeJournalEntry:
    timestamp: str
    symbol: str
    setup_name: str
    setup_score: float
    direction: int
    entry_price: float
    forward_days: int = 7
    # 回填
    actual_return: float | None = None
    direction_correct: bool | None = None
    filled: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> EdgeJournalEntry:
        fields = set(cls.__dataclass_fields__.keys())
        return cls(**{k: v for k, v in d.items() if k in fields})


@dataclass
class SetupStats:
    name: str
    n: int = 0
    correct: int = 0
    accuracy: float = 0.0
    current_threshold: float = 70.0
    suggested_threshold: float = 70.0
    note: str = ""


class EdgeJournal:
    def __init__(self, log_dir: str | Path | None = None) -> None:
        base = Path(log_dir) if log_dir else _DEFAULT_DIR
        base.mkdir(parents=True, exist_ok=True)
        self.log_dir = base
        self.journal_path = base / _JOURNAL_FILE
        self.threshold_path = base / _THRESH_FILE

    def log_prediction(
        self,
        symbol: str,
        prices,
        *,
        forward_days: int = 7,
        price_loader=None,
    ) -> EdgeJournalEntry | None:
        """从行情快照记录当前 edge setup（无 setup 则跳过）。"""
        setup = find_best_edge_setup(prices)
        if setup is None:
            return None
        entry = EdgeJournalEntry(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            symbol=symbol,
            setup_name=setup.name,
            setup_score=round(setup.score, 1),
            direction=setup.direction,
            entry_price=float(prices["close"].iloc[-1]),
            forward_days=forward_days,
        )
        with open(self.journal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        return entry

    def _load_entries(self, *, filled_only: bool = False) -> list[EdgeJournalEntry]:
        if not self.journal_path.exists():
            return []
        out: list[EdgeJournalEntry] = []
        with open(self.journal_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = EdgeJournalEntry.from_dict(json.loads(line))
                except (json.JSONDecodeError, TypeError):
                    continue
                if filled_only and not e.filled:
                    continue
                out.append(e)
        return out

    def backfill(self, price_loader) -> dict:
        """用 price_loader(symbol) -> DataFrame 回填未验证条目。"""
        entries = self._load_entries()
        summary = {"n_checked": 0, "n_filled": 0, "n_errors": 0}
        updated: list[EdgeJournalEntry] = []

        for e in entries:
            if e.filled:
                updated.append(e)
                continue
            summary["n_checked"] += 1
            try:
                ts = datetime.fromisoformat(e.timestamp)
                if datetime.now() - ts < timedelta(days=e.forward_days):
                    updated.append(e)
                    continue
                df = price_loader(e.symbol)
                if df is None or len(df) < 10:
                    updated.append(e)
                    continue
                # 找 timestamp 之后 forward_days 交易日收益
                idx = df.index
                if hasattr(idx, "tz") and idx.tz is not None:
                    idx = idx.tz_localize(None)
                target = ts.date()
                pos = None
                for i, t in enumerate(idx):
                    d = t.date() if hasattr(t, "date") else t
                    if d >= target:
                        pos = i
                        break
                if pos is None or pos + e.forward_days >= len(df):
                    updated.append(e)
                    continue
                ret = float(df["close"].iloc[pos + e.forward_days] / df["close"].iloc[pos] - 1)
                e.actual_return = round(ret, 6)
                e.direction_correct = (ret > 0) if e.direction == 1 else (ret < 0)
                e.filled = True
                summary["n_filled"] += 1
                updated.append(e)
            except Exception:
                summary["n_errors"] += 1
                updated.append(e)

        if summary["n_filled"]:
            with open(self.journal_path, "w", encoding="utf-8") as f:
                for e in updated:
                    f.write(json.dumps(e.to_dict(), ensure_ascii=False) + "\n")
        return summary

    def setup_stats(self, min_samples: int = 5) -> list[SetupStats]:
        """按 setup 聚合方向准确率。"""
        by_name: dict[str, list[bool]] = {}
        for e in self._load_entries(filled_only=True):
            if e.direction_correct is None:
                continue
            by_name.setdefault(e.setup_name, []).append(e.direction_correct)

        rows: list[SetupStats] = []
        for name, hits in by_name.items():
            n = len(hits)
            acc = sum(hits) / n if n else 0.0
            cur = SETUP_MIN_SCORES.get(name, 70.0)
            sug, note = _suggest_threshold(name, acc, n, cur, min_samples)
            rows.append(SetupStats(
                name=name, n=n, correct=sum(hits), accuracy=round(acc, 4),
                current_threshold=cur, suggested_threshold=sug, note=note,
            ))
        return sorted(rows, key=lambda r: -r.accuracy)

    def save_suggested_thresholds(self) -> dict:
        """把建议门槛写入 edge_setup_thresholds.json（供人工审核后手动合并到代码）。"""
        stats = self.setup_stats()
        payload = {
            "updated": datetime.now().isoformat(timespec="seconds"),
            "setups": {
                s.name: {
                    "current": s.current_threshold,
                    "suggested": s.suggested_threshold,
                    "accuracy": s.accuracy,
                    "n": s.n,
                    "note": s.note,
                }
                for s in stats
            },
        }
        self.threshold_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        return payload

    def format_report(self) -> str:
        stats = self.setup_stats()
        if not stats:
            return "Edge 台账暂无已回填样本。"
        lines = ["Edge setup 方向准确率（已回填）", "-" * 56]
        for s in stats:
            lines.append(
                f"{s.name:<16} n={s.n:3d} acc={s.accuracy*100:5.1f}%  "
                f"门槛 {s.current_threshold:.0f}→{s.suggested_threshold:.0f}  {s.note}"
            )
        return "\n".join(lines)


def _suggest_threshold(
    name: str, acc: float, n: int, current: float, min_samples: int,
) -> tuple[float, str]:
    """渐进微调：样本够才动，每次最多 ±2。"""
    if n < min_samples:
        return current, "样本不足"
    if acc >= 0.72:
        return max(70.0, current - 2), "准确率高，略放宽"
    if acc < 0.55:
        return min(90.0, current + 2), "准确率低，略收紧"
    return current, "维持"


def edge_summary_for_display(prices) -> dict:
    """forecast / CLI 用：当前 edge 快照。"""
    setup = find_best_edge_setup(prices)
    if setup is None:
        return {"edge_active": False}
    return {
        "edge_active": True,
        "edge_setup": setup.name,
        "edge_score": round(setup.score, 1),
        "edge_direction": "BUY" if setup.direction == 1 else "SELL",
        "edge_reasons": setup.reasons,
    }


# 默认监控池（期货主力 + 流动性 A 股）
DEFAULT_WATCH_SYMBOLS: list[str] = [
    "RB0", "M0", "AU0", "AG0", "CU0", "I0", "SI0", "BU0", "TA0", "NI0",
    "600519", "000001", "300750", "601318", "000858",
]


def load_prices_for_symbol(symbol: str):
    """统一行情加载：期货 akshare / A 股 akshare。"""
    import re

    s = str(symbol).strip().upper()
    try:
        if re.fullmatch(r"[A-Z]{1,4}0?", s):
            from .data.futures_history import get_futures_history
            df = get_futures_history(s, days=800)
            if df is not None and len(df) >= 60:
                return df
        if s.isdigit() and len(s) == 6:
            from .data.akshare_cn import AkShareDataFeed
            from .data.base import BarRequest

            return AkShareDataFeed().history(BarRequest(symbol=s, start="2023-01-01"))
    except Exception as e:
        logger.debug("load_prices_for_symbol %s: %s", s, e)
    return None


def daily_edge_cycle(symbols: list[str] | None = None) -> dict:
    """每日：记录 edge → 回填 → 统计 → 写建议门槛。"""
    syms = symbols or DEFAULT_WATCH_SYMBOLS
    journal = EdgeJournal()
    logged = 0
    for sym in syms:
        df = load_prices_for_symbol(sym)
        if df is not None and len(df) >= 80:
            if journal.log_prediction(sym, df):
                logged += 1
    backfill = journal.backfill(load_prices_for_symbol)
    stats = journal.setup_stats()
    thresholds = journal.save_suggested_thresholds()
    filled = journal._load_entries(filled_only=True)
    overall_acc = 0.0
    if filled:
        hits = [e.direction_correct for e in filled if e.direction_correct is not None]
        overall_acc = sum(hits) / len(hits) if hits else 0.0
    return {
        "logged_today": logged,
        "backfill": backfill,
        "overall_accuracy": round(overall_acc, 4),
        "filled_total": len(filled),
        "setups": [asdict(s) for s in stats],
        "thresholds_file": str(journal.threshold_path),
        "thresholds": thresholds,
    }


def api_stats_payload() -> dict:
    """API /api/edge/stats 用。"""
    journal = EdgeJournal()
    stats = journal.setup_stats(min_samples=1)
    filled = journal._load_entries(filled_only=True)
    overall = 0.0
    if filled:
        hits = [e.direction_correct for e in filled if e.direction_correct is not None]
        overall = sum(hits) / len(hits) if hits else 0.0
    thresholds = {}
    if journal.threshold_path.exists():
        try:
            thresholds = json.loads(journal.threshold_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "overall_accuracy": round(overall, 4),
        "filled_total": len(filled),
        "pending_total": len(journal._load_entries()) - len(filled),
        "setups": [asdict(s) for s in stats],
        "thresholds": thresholds,
        "setup_min_scores": dict(SETUP_MIN_SCORES),
    }


def _cli_backfill() -> int:
    """python -m quanttrader.edge_journal backfill"""
    result = daily_edge_cycle()
    journal = EdgeJournal()
    print(journal.format_report())
    print("cycle:", {k: v for k, v in result.items() if k != "thresholds"})
    return 0


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "backfill":
        raise SystemExit(_cli_backfill())
    j = EdgeJournal()
    print(j.format_report())
