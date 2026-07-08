"""SF×ML 冲突记录 — 供 auto_tune 学习 SF vs ML 谁更常正确。"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_LOG = Path("logs")
_FILE = _LOG / "sf_ml_conflicts.jsonl"


@dataclass
class SfMlConflictRecord:
    ts: str
    symbol: str
    sf_sig: int
    sf_tier: str
    ml_signal: int
    ml_confidence: float
    ml_mode: str
    outcome: str
    sf_win_rate: float = 0.0
    resolved_sf_correct: bool | None = None


def _ensure_log_dir() -> None:
    _LOG.mkdir(parents=True, exist_ok=True)


def record_conflict(
    *,
    symbol: str,
    sf_sig: int,
    sf_tier: str,
    ml_signal: int,
    ml_confidence: float,
    ml_mode: str,
    outcome: str,
    sf_win_rate: float = 0.0,
) -> None:
    if not symbol or ml_signal == 0 or sf_sig == 0:
        return
    _ensure_log_dir()
    rec = SfMlConflictRecord(
        ts=datetime.now(UTC).isoformat(),
        symbol=symbol,
        sf_sig=sf_sig,
        sf_tier=sf_tier or "",
        ml_signal=ml_signal,
        ml_confidence=ml_confidence,
        ml_mode=ml_mode,
        outcome=outcome,
        sf_win_rate=sf_win_rate,
    )
    with open(_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")


def load_conflicts(limit: int = 5000) -> list[dict[str, Any]]:
    if not _FILE.exists():
        return []
    lines = _FILE.read_text(encoding="utf-8").strip().splitlines()
    out: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def aggregate_for_auto_tune() -> tuple[int, int]:
    """返回 (冲突样本数, SF 在冲突中胜出次数)。"""
    rows = load_conflicts()
    conflicts = [r for r in rows if r.get("outcome") in ("sf_priority", "ml_veto", "ml_boost")]
    sf_won = sum(
        1 for r in conflicts
        if r.get("outcome") in ("sf_priority", "ml_boost")
        or (r.get("outcome") == "ml_veto" and r.get("resolved_sf_correct") is True)
    )
    return len(conflicts), sf_won
