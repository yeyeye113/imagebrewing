"""数字化胜率面板 — 记录综合分/胜率随时间变化."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


def _avg(values: list[float | None]) -> float | None:
    xs = [v for v in values if v is not None]
    return round(sum(xs) / len(xs), 4) if xs else None


@dataclass
class LivePanelSnapshot:
    timestamp: str
    avg_final_score: float = 0.0
    avg_tech_score: float = 0.0
    avg_win_rate_3d: float | None = None
    avg_win_rate_5d: float | None = None
    avg_win_rate_7d: float | None = None
    avg_win_rate_30d: float | None = None
    calibrated_direction_accuracy: float | None = None
    n_symbols: int = 0
    top_symbols: list[str] = field(default_factory=list)
    session_window: str = "idle"
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class LivePanelTracker:
    """Append-only JSONL history for dashboard sparklines."""

    def __init__(self, log_dir: str = "") -> None:
        base = Path(log_dir) if log_dir else Path(__file__).resolve().parent / "prediction_logs"
        base.mkdir(parents=True, exist_ok=True)
        self._path = base / "live_panel.jsonl"

    def record_from_results(
        self,
        results: list[Any],
        *,
        timestamp: str | None = None,
        calibrated_accuracy: float | None = None,
        session_window: str = "idle",
        note: str = "",
    ) -> LivePanelSnapshot:
        ts = timestamp or datetime.now().isoformat()
        snap = LivePanelSnapshot(
            timestamp=ts,
            avg_final_score=round(
                sum(getattr(r, "final_score", 0) for r in results) / max(len(results), 1), 1
            ),
            avg_tech_score=round(
                sum(getattr(r, "tech_score", 0) for r in results) / max(len(results), 1), 1
            ),
            avg_win_rate_3d=_avg([getattr(r, "win_rate_3d", None) for r in results]),
            avg_win_rate_5d=_avg([getattr(r, "win_rate_5d", None) for r in results]),
            avg_win_rate_7d=_avg([getattr(r, "win_rate_7d", None) for r in results]),
            avg_win_rate_30d=_avg([getattr(r, "win_rate_30d", None) for r in results]),
            calibrated_direction_accuracy=calibrated_accuracy,
            n_symbols=len(results),
            top_symbols=[getattr(r, "symbol", "") for r in results[:5]],
            session_window=session_window,
            note=note,
        )
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(snap.to_dict(), ensure_ascii=False) + "\n")
        self._trim_file(max_lines=400)
        return snap

    def _trim_file(self, max_lines: int = 400) -> None:
        if not self._path.exists():
            return
        lines = self._path.read_text(encoding="utf-8").strip().splitlines()
        if len(lines) <= max_lines:
            return
        keep = lines[-max_lines:]
        self._path.write_text("\n".join(keep) + "\n", encoding="utf-8")

    def history(self, limit: int = 48) -> list[dict]:
        if not self._path.exists():
            return []
        lines = self._path.read_text(encoding="utf-8").strip().splitlines()
        out: list[dict] = []
        for line in lines[-limit:]:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return out

    def latest(self) -> dict | None:
        h = self.history(1)
        return h[0] if h else None

    def summary(self) -> dict:
        hist = self.history(48)
        if not hist:
            return {"count": 0, "latest": None, "trend": {}}
        latest = hist[-1]
        prev = hist[-2] if len(hist) >= 2 else latest

        def _delta(key: str) -> float | None:
            a, b = latest.get(key), prev.get(key)
            if a is None or b is None:
                return None
            return round(float(a) - float(b), 4)

        return {
            "count": len(hist),
            "latest": latest,
            "trend": {
                "final_score_delta": _delta("avg_final_score"),
                "tech_score_delta": _delta("avg_tech_score"),
                "win_rate_7d_delta": _delta("avg_win_rate_7d"),
            },
            "history": hist,
        }
