"""置信度门槛策略 — 修复「0.75 永远达不到」导致零成交。

SymbolFilter tier 信号天然置信度约 0.5–1.0；策略参数 min_confidence 若被
auto_tune 抬到 0.75，会拦死所有实盘信号。本模块：
  1. 将 strategy_params.min_confidence 钳制在 [0.35, 0.60]
  2. tier1/tier2 使用更低有效门槛（白名单历史实证优先）
"""
from __future__ import annotations

from typing import Any

DEFAULT_MIN_CONFIDENCE = 0.50
MAX_MIN_CONFIDENCE = 0.60
MIN_MIN_CONFIDENCE = 0.35

# tier 有效门槛上限（只能放宽，不能比全局策略更严）
TIER_CONFIDENCE_CEILING: dict[str, float] = {
    "tier1": 0.40,
    "tier2": 0.45,
    "tier3": 0.50,
    "": 0.50,
}


def clamp_strategy_min_confidence(raw: float | None) -> float:
    """钳制持久化参数，迁移旧版 0.75 等不可达阈值。"""
    try:
        v = float(raw if raw is not None else DEFAULT_MIN_CONFIDENCE)
    except (TypeError, ValueError):
        v = DEFAULT_MIN_CONFIDENCE
    return min(max(v, MIN_MIN_CONFIDENCE), MAX_MIN_CONFIDENCE)


def effective_min_confidence(
    strategy_params: dict[str, Any] | None = None,
    tier: str = "",
) -> float:
    """返回当前 tier 下信号所需最低置信度 (0–1)。"""
    p = strategy_params or {}
    base = clamp_strategy_min_confidence(p.get("min_confidence"))
    tier_key = (tier or "").strip().lower()
    tier_cap = TIER_CONFIDENCE_CEILING.get(tier_key, base)
    return min(base, tier_cap)


def passes_confidence_gate(
    confidence: float,
    strategy_params: dict[str, Any] | None = None,
    tier: str = "",
) -> bool:
    return float(confidence) >= effective_min_confidence(strategy_params, tier)


def migrate_strategy_params(params: dict[str, Any]) -> dict[str, Any]:
    """就地修正 min_confidence 并写回说明。"""
    out = dict(params)
    old = out.get("min_confidence")
    new = clamp_strategy_min_confidence(old)
    if old != new:
        out["min_confidence"] = new
        out["min_confidence_migrated_from"] = old
    return out
