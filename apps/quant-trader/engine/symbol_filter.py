"""Per-Symbol 分层过滤器 — 只允许高准确率的 品种+方向 组合出信号。

分层机制:
  Tier1: acc>=75% 且 n>=20 → 允许交易，置信度×1.2 (大仓位)
  Tier2: acc>=65% 且 n>=20 → 允许交易，置信度×1.0 (标准仓位)
  Tier3: acc>=60% 且 n>=30 → 允许交易，置信度×0.8 (小仓位)
  其他: → HOLD

用法:
    from quanttrader.engine.symbol_filter import SymbolFilter
    sf = SymbolFilter()
    tier, adj = sf.filter("M", "SELL", 0.7)  # 返回 ("tier1", 1.2) 或 ("", 0)
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ComboRecord:
    """一个 品种+方向 的准确率记录。"""
    symbol: str
    direction: str  # "BUY" or "SELL"
    accuracy: float
    sample_count: int
    tier: str = ""  # "tier1", "tier2", "tier3"
    confidence_mult: float = 1.0
    hold_period: str = "10d"


class SymbolFilter:
    """品种方向分层过滤器。

    根据 strategy_params.json 的 best_combos 自动构建分层白名单。
    """

    def __init__(self, params_path: str | Path | None = None):
        self._whitelist: dict[str, dict[str, ComboRecord]] = {}
        self._params_path = params_path
        self._load()

    def _load(self):
        if self._params_path is None:
            self._params_path = Path(__file__).parent.parent.parent / "logs" / "strategy_params.json"

        path = Path(self._params_path)
        if not path.exists():
            return

        try:
            with open(path, encoding="utf-8") as f:
                params = json.load(f)
        except (json.JSONDecodeError, OSError):
            return

        # 合并 best_combos_10d 和 best_combos_20d
        all_combos = params.get("best_combos_10d", [])
        seen = set()
        for c in all_combos:
            seen.add(c.get("name", ""))

        for c in params.get("best_combos_20d", []):
            if c.get("name", "") not in seen:
                all_combos.append(c)
                seen.add(c.get("name", ""))

        for combo in all_combos:
            name = combo.get("name", "")
            acc = combo.get("acc", 0)
            n = combo.get("n", 0)

            if "+" not in name:
                continue
            parts = name.split("+")
            if len(parts) != 2:
                continue

            symbol_raw, direction = parts
            if direction not in ("BUY", "SELL"):
                continue

            symbol = symbol_raw.rstrip("0")

            # 优先使用JSON中显式设定的tier，否则按阈值分类
            json_tier = combo.get("tier", "")
            if json_tier in ("tier1", "tier2", "tier3"):
                tier = json_tier
                mult = {"tier1": 1.0, "tier2": 0.8, "tier3": 0.5}.get(tier, 0.5)
            else:
                tier, mult = self._classify_tier(acc, n)
            if not tier:
                continue

            if symbol not in self._whitelist:
                self._whitelist[symbol] = {}
            if direction not in self._whitelist[symbol]:
                self._whitelist[symbol][direction] = ComboRecord(
                    symbol=symbol,
                    direction=direction,
                    accuracy=acc,
                    sample_count=n,
                    tier=tier,
                    confidence_mult=mult,
                )

    def _classify_tier(self, acc: float, n: int) -> tuple[str, float]:
        """分层: acc>=75%+n>=20=Tier1, acc>=65%+n>=20=Tier2, acc>=60%+n>=30=Tier3"""
        if acc >= 75.0 and n >= 20:
            return ("tier1", 1.2)
        elif acc >= 65.0 and n >= 20:
            return ("tier2", 1.0)
        elif acc >= 60.0 and n >= 30:
            return ("tier3", 0.8)
        return ("", 0.0)

    def filter(self, symbol: str, direction: str, confidence: float) -> tuple[str, float]:
        """过滤信号并返回分层信息。

        Returns:
            (tier, confidence_multiplier):
              tier非空 = 允许, tier="" = HOLD
        """
        if direction in ("HOLD", "NEUTRAL", ""):
            return ("pass", 1.0)

        symbol_upper = symbol.upper().rstrip("0")
        direction_upper = direction.upper()

        if symbol_upper in self._whitelist:
            rec = self._whitelist[symbol_upper].get(direction_upper)
            if rec:
                return (rec.tier, rec.confidence_mult)

        return ("", 0.0)

    def get_allowed(self) -> dict[str, list[str]]:
        result = {}
        for symbol, dirs in self._whitelist.items():
            result[symbol] = list(dirs.keys())
        return result

    def summary(self) -> str:
        lines = ["[SymbolFilter] 分层白名单:"]
        for tier_label in ["tier1", "tier2", "tier3"]:
            items = []
            for symbol, dirs in sorted(self._whitelist.items()):
                for d, rec in dirs.items():
                    if rec.tier == tier_label:
                        items.append(f"{symbol}+{d}(acc={rec.accuracy:.0f}% n={rec.sample_count})")
            if items:
                lines.append(f"  {tier_label.upper()}: {' | '.join(items)}")
        if not self._whitelist:
            lines.append("  (空)")
        return "\n".join(lines)

    def reload(self):
        self._whitelist.clear()
        self._load()
