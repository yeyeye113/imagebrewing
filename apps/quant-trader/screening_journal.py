"""筛选日志 + 权重配置 + 基于偏差反馈的自我迭代.

持久化到 ``prediction_logs/screening_journal.jsonl`` 与 ``screening_config.json``。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_WEIGHTS: dict[str, float] = {
    "tech": 0.82,
    "news": 0.08,
    "wuxing": 0.05,
    "meta": 0.05,
}


@dataclass
class ScreeningWeights:
    tech: float = 0.82
    news: float = 0.08
    wuxing: float = 0.05
    meta: float = 0.05

    def normalized(self) -> ScreeningWeights:
        s = self.tech + self.news + self.wuxing + self.meta
        if s <= 0:
            return ScreeningWeights()
        return ScreeningWeights(
            tech=self.tech / s,
            news=self.news / s,
            wuxing=self.wuxing / s,
            meta=self.meta / s,
        )

    def to_dict(self) -> dict[str, float]:
        n = self.normalized()
        return {"tech": round(n.tech, 4), "news": round(n.news, 4),
                "wuxing": round(n.wuxing, 4), "meta": round(n.meta, 4)}


@dataclass
class ScreeningRunLog:
    timestamp: str
    kind: str  # stock | future | both
    weights: dict[str, float]
    n_results: int
    avg_final_score: float
    avg_tech_score: float
    top_symbols: list[str] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class ScreeningJournal:
    def __init__(self, log_dir: str = ""):
        base = Path(log_dir) if log_dir else Path(__file__).resolve().parent / "prediction_logs"
        base.mkdir(parents=True, exist_ok=True)
        self._dir = base
        self._config_path = base / "screening_config.json"
        self._journal_path = base / "screening_journal.jsonl"

    def load_weights(self) -> ScreeningWeights:
        if not self._config_path.exists():
            return ScreeningWeights()
        try:
            data = json.loads(self._config_path.read_text(encoding="utf-8"))
            w = data.get("weights", DEFAULT_WEIGHTS)
            return ScreeningWeights(
                tech=float(w.get("tech", 0.82)),
                news=float(w.get("news", 0.08)),
                wuxing=float(w.get("wuxing", 0.05)),
                meta=float(w.get("meta", 0.05)),
            ).normalized()
        except Exception:
            return ScreeningWeights()

    def save_weights(self, weights: ScreeningWeights, note: str = "") -> dict:
        w = weights.normalized()
        payload = {
            "updated_at": datetime.now().isoformat(),
            "weights": w.to_dict(),
            "note": note,
        }
        self._config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    def log_run(self, entry: ScreeningRunLog) -> None:
        with self._journal_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

    def recent_runs(self, limit: int = 30) -> list[dict]:
        if not self._journal_path.exists():
            return []
        lines = self._journal_path.read_text(encoding="utf-8").strip().splitlines()
        out = []
        for line in lines[-limit:]:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return list(reversed(out))

    def iterate_weights(
        self,
        deviation_global: dict[str, Any] | None = None,
        strategy_global_wr: float | None = None,
    ) -> tuple[ScreeningWeights, str]:
        """根据预测偏差统计微调 tech/news/wuxing 比例."""
        cur = self.load_weights()
        reason_parts: list[str] = []
        tech, news, wx, meta = cur.tech, cur.news, cur.wuxing, cur.meta

        dg = deviation_global or {}
        dir_acc = float(dg.get("direction_accuracy", 0.5) or 0.5)
        n_filled = int(dg.get("n_filled", 0) or 0)

        if strategy_global_wr is not None and n_filled >= 3:
            if strategy_global_wr < 0.45:
                tech = min(0.88, tech + 0.02)
                wx = max(0.02, wx - 0.01)
                reason_parts.append(f"高手策略验证胜率偏低({strategy_global_wr:.0%})→强化技术面")
            elif strategy_global_wr > 0.58:
                reason_parts.append(f"高手策略验证胜率良好({strategy_global_wr:.0%})")

        if n_filled >= 5:
            if dir_acc < 0.45:
                shift = min(0.04, news + wx)
                tech += shift * 0.75
                news = max(0.03, news - shift * 0.5)
                wx = max(0.02, wx - shift * 0.25)
                reason_parts.append(f"方向准确率偏低({dir_acc:.0%})→提高技术面权重")
            elif dir_acc > 0.62:
                news = min(0.12, news + 0.01)
                tech = max(0.75, tech - 0.01)
                reason_parts.append(f"方向准确率较好({dir_acc:.0%})→略增技术面权重")

        recent = self.recent_runs(5)
        if recent:
            avg_n = sum(r.get("n_results", 0) for r in recent) / len(recent)
            if avg_n < 2:
                tech = max(0.78, tech - 0.02)
                news = min(0.10, news + 0.01)
                reason_parts.append("近期筛出标的过少→略放宽技术面门槛")

        new_w = ScreeningWeights(tech=tech, news=news, wuxing=wx, meta=meta).normalized()
        note = "; ".join(reason_parts) if reason_parts else "权重已归一化，暂无调整"
        self.save_weights(new_w, note=note)
        self.log_run( ScreeningRunLog(
            timestamp=datetime.now().isoformat(),
            kind="iterate",
            weights=new_w.to_dict(),
            n_results=0,
            avg_final_score=0,
            avg_tech_score=0,
            note=note,
        ))
        return new_w, note
