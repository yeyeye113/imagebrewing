"""信号拦截诊断 — 统计 Daemon / 交易循环中各环节 HOLD 原因.

用于定位「零成交」：哪一层拦截最多、占比多少。
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


@dataclass
class BlockerStats:
    """累计各拦截原因出现次数."""

    counts: Counter = field(default_factory=Counter)
    ticks: int = 0
    signals_emitted: int = 0  # 非 HOLD 最终信号次数

    def record(self, reason: str) -> None:
        key = (reason or "unknown").strip()[:120]
        self.counts[key] += 1

    def tick_done(self, *, had_signal: bool) -> None:
        self.ticks += 1
        if had_signal:
            self.signals_emitted += 1

    def top(self, n: int = 8) -> list[tuple[str, int]]:
        return self.counts.most_common(n)

    def summary_lines(self) -> list[str]:
        if self.ticks == 0:
            return ["信号诊断: 尚无 tick 数据"]
        hold_rate = 1.0 - (self.signals_emitted / self.ticks) if self.ticks else 1.0
        lines = [
            f"信号诊断 tick={self.ticks} 出信号={self.signals_emitted} "
            f"HOLD率={hold_rate:.0%} 拦截种类={len(self.counts)}",
        ]
        for reason, cnt in self.top():
            pct = cnt / max(self.ticks, 1) * 100
            lines.append(f"  · {reason}: {cnt} ({pct:.0f}%)")
        return lines

    def to_dict(self) -> dict:
        return {
            "ticks": self.ticks,
            "signals_emitted": self.signals_emitted,
            "hold_rate": round(
                1.0 - self.signals_emitted / self.ticks, 3
            ) if self.ticks else 1.0,
            "blockers": dict(self.counts),
            "top": [{"reason": r, "count": c} for r, c in self.top()],
        }
