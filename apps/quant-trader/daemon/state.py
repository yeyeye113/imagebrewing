"""DaemonState 持久化状态模块。"""

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path


@dataclass
class DaemonState:
    """JSON-serializable state that survives daemon restarts."""

    date: str = ""  # "2026-06-18"
    day_trades: int = 0
    day_pnl: float = 0.0
    consecutive_losses: int = 0
    peak_equity: float = 0.0
    last_decision_at: str = ""
    halt_until: float = 0.0  # Unix timestamp
    halt_reason: str = ""
    total_trades: int = 0
    total_pnl: float = 0.0
    wins: int = 0  # ✅ 命中追踪
    version: int = 1

    @property
    def win_rate(self) -> float | None:
        if self.total_trades <= 0:
            return None
        return self.wins / self.total_trades

    @classmethod
    def load(cls, path: Path) -> "DaemonState":
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return cls(**{f.name: data.get(f.name, getattr(cls, f.name)) for f in fields(cls)})
            except Exception:
                pass
        return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
