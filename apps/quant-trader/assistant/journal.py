"""交易日志 — 记录每次建议和结果，用于复盘。"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .card import TradeCard


@dataclass
class TradeRecord:
    """一条交易记录。"""
    id: str = ""
    date: str = ""
    symbol: str = ""
    direction: str = ""
    entry_price: float = 0.0
    exit_price: float = 0.0
    pnl_pct: float = 0.0
    score: float = 0.0
    rating: str = ""
    v530_hit: bool | None = None  # v530高/低点是否命中
    direction_correct: bool | None = None  # SymbolFilter方向是否正确
    adopted: bool = False  # 用户是否采纳
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TradeJournal:
    """交易日志管理器。"""

    def __init__(self, log_dir: Path | str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _today_path(self) -> Path:
        return self.log_dir / f"journal_{datetime.now().strftime('%Y%m%d')}.json"

    def _load(self) -> list[dict]:
        path = self._today_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
            except Exception:
                pass
        return []

    def _save(self, records: list[dict]) -> None:
        path = self._today_path()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def record_suggestion(self, card: TradeCard) -> str:
        """记录一条交易建议。"""
        records = self._load()
        record = TradeRecord(
            id=card.id,
            date=datetime.now().strftime("%Y-%m-%d"),
            symbol=card.symbol,
            direction=card.direction,
            entry_price=card.current_price,
            score=card.score,
            rating=card.rating,
            adopted=False,
        )
        records.append(record.to_dict())
        self._save(records)
        return record.id

    def mark_adopted(self, record_id: str) -> None:
        """标记用户采纳了这条建议。"""
        records = self._load()
        for r in records:
            if r.get("id") == record_id:
                r["adopted"] = True
                break
        self._save(records)

    def record_result(
        self,
        record_id: str,
        exit_price: float,
        pnl_pct: float,
        v530_hit: bool | None = None,
        direction_correct: bool | None = None,
        notes: str = "",
    ) -> None:
        """记录交易结果。"""
        records = self._load()
        for r in records:
            if r.get("id") == record_id:
                r["exit_price"] = exit_price
                r["pnl_pct"] = pnl_pct
                r["v530_hit"] = v530_hit
                r["direction_correct"] = direction_correct
                r["notes"] = notes
                break
        self._save(records)

    def get_today_stats(self) -> dict[str, Any]:
        """获取今日统计。"""
        records = self._load()
        if not records:
            return {
                "total_suggestions": 0,
                "adopted": 0,
                "trades_closed": 0,
                "wins": 0,
                "losses": 0,
                "total_pnl": 0,
                "v530_hit_rate": 0,
                "direction_accuracy": 0,
            }

        adopted = [r for r in records if r.get("adopted")]
        closed = [r for r in records if r.get("exit_price", 0) > 0]
        wins = [r for r in closed if r.get("pnl_pct", 0) > 0]
        losses = [r for r in closed if r.get("pnl_pct", 0) <= 0]

        v530_hits = [r for r in closed if r.get("v530_hit")]
        dir_correct = [r for r in closed if r.get("direction_correct")]

        return {
            "total_suggestions": len(records),
            "adopted": len(adopted),
            "trades_closed": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "total_pnl": sum(r.get("pnl_pct", 0) for r in closed),
            "win_rate": len(wins) / len(closed) * 100 if closed else 0,
            "v530_hit_rate": len(v530_hits) / len(closed) * 100 if closed else 0,
            "direction_accuracy": len(dir_correct) / len(closed) * 100 if closed else 0,
        }
