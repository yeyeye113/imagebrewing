"""SymbolFilter × ML 协调器 — 解决 ML 否决 SF 导致零成交。

原则:
  1. SymbolFilter 白名单 tier 是主信号源 (历史实证准确率)
  2. ML(v15) OOS≈55% 时不应硬否决 tier1/tier2 组合
  3. v14 edge 门槛按 tier 自动放宽/收紧
  4. 参数从 logs/strategy_params.json 读取并由 tracker.auto_tune 持续更新

模式 (ml_mode):
  advisory  — ML 只调置信度, 不否决 SF (默认, 适合 ML OOS 弱于 SF)
  confirm   — ML 强反对(conf≥阈值) 且 SF 为 tier3 时才否决
  off       — 跳过 ML
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from ..log import get_logger

logger = get_logger("sf_ml")

DEFAULT_MIN_EDGE = 0.006
TIER_MIN_EDGE = {
    "tier1": 0.004,
    "tier2": 0.006,
    "tier3": 0.008,
    "": 0.006,
}


@dataclass
class SfMlParams:
    """SF+ML 协调参数 (可持久化到 strategy_params.json)."""
    ml_mode: str = "advisory"
    ml_veto_confidence: float = 0.80
    use_v15: bool = False
    min_edge_default: float = DEFAULT_MIN_EDGE
    min_edge_by_tier: dict[str, float] = field(default_factory=lambda: dict(TIER_MIN_EDGE))
    sf_priority_tiers: tuple[str, ...] = ("tier1", "tier2")
    ml_oos_accuracy: float = 0.0

    @classmethod
    def from_strategy_params(cls, params: dict[str, Any] | None) -> SfMlParams:
        p = params or {}
        sf_ml = p.get("sf_ml", {})
        tier_edges = dict(TIER_MIN_EDGE)
        tier_edges.update(sf_ml.get("min_edge_by_tier", {}))
        return cls(
            ml_mode=str(sf_ml.get("ml_mode", p.get("ml_mode", "advisory"))),
            ml_veto_confidence=float(sf_ml.get("ml_veto_confidence", 0.80)),
            use_v15=bool(sf_ml.get("use_v15", False)),
            min_edge_default=float(sf_ml.get("min_edge_default", DEFAULT_MIN_EDGE)),
            min_edge_by_tier=tier_edges,
            sf_priority_tiers=tuple(sf_ml.get("sf_priority_tiers", ["tier1", "tier2"])),
            ml_oos_accuracy=float(sf_ml.get("ml_oos_accuracy", 0.0)),
        )


@dataclass
class SfMlDecision:
    """协调后的决策."""
    sig: int = 0
    label: str = "HOLD"
    confidence: float = 0.0
    reason: str = ""
    edge_approved: bool = False
    edge_info: str = ""
    min_edge: float = DEFAULT_MIN_EDGE
    ml_signal: int = 0
    ml_confidence: float = 0.0
    ml_mode: str = "advisory"
    conflict: bool = False
    outcome: str = "hold"  # hold | pass | edge_block | ml_veto | sf_priority | ml_boost

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def load_sf_ml_params() -> SfMlParams:
    try:
        from ..tracker import load_strategy_params
        return SfMlParams.from_strategy_params(load_strategy_params())
    except Exception as e:
        logger.debug("load_sf_ml_params fallback: %s", e)
        return SfMlParams()


def min_edge_for_tier(tier: str, params: SfMlParams | None = None) -> float:
    p = params or SfMlParams()
    return float(p.min_edge_by_tier.get(tier or "", p.min_edge_default))


def _check_v14_edge(
    sig: int,
    current_price: float,
    predicted_high: float,
    predicted_low: float,
    min_edge: float,
) -> tuple[bool, str]:
    if sig == 1:
        edge = (predicted_high - current_price) / current_price
        if edge >= min_edge:
            return True, f"v14_edge={edge:.2%}>={min_edge:.2%}"
        return False, f"v14 edge不足: long={edge:.2%} < {min_edge:.2%}"
    if sig == -1:
        edge = (current_price - predicted_low) / current_price
        if edge >= min_edge:
            return True, f"v14_edge={edge:.2%}>={min_edge:.2%}"
        return False, f"v14 edge不足: short={edge:.2%} < {min_edge:.2%}"
    return False, "无方向"


def _run_ml_v15(prices: pd.DataFrame, symbol: str) -> dict:
    try:
        from ..ml.ml_v15_signal import is_available, predict
        if not is_available():
            return {"signal": 0, "confidence": 0.0}
        return predict(prices, symbol)
    except Exception as e:
        logger.debug("v15 predict skip: %s", e)
        return {"signal": 0, "confidence": 0.0}


def evaluate_sf_ml(
    *,
    symbol: str,
    sf_sig: int,
    sf_label: str,
    sf_confidence: float,
    sf_tier: str,
    sf_win_rate: float,
    sf_sample: int,
    prices: pd.DataFrame,
    hl_pred: Any | None,
    params: SfMlParams | None = None,
    sf_reason: str = "",
) -> SfMlDecision:
    """协调 SymbolFilter 信号 + v14 edge + 可选 ML v15."""
    p = params or load_sf_ml_params()
    dec = SfMlDecision(ml_mode=p.ml_mode)

    if sf_sig == 0:
        dec.reason = sf_reason or "SymbolFilter HOLD"
        dec.outcome = "hold"
        return dec

    dec.sig = sf_sig
    dec.label = sf_label
    dec.confidence = sf_confidence
    dec.reason = sf_reason
    dec.min_edge = min_edge_for_tier(sf_tier, p)

    # ── v14 edge (按 tier 自动门槛) ──
    if hl_pred is not None:
        try:
            cp = float(prices["close"].iloc[-1])
            ph = float(getattr(hl_pred, "predicted_high", cp * 1.02))
            pl = float(getattr(hl_pred, "predicted_low", cp * 0.98))
            ok, info = _check_v14_edge(sf_sig, cp, ph, pl, dec.min_edge)
            dec.edge_info = info
            if not ok:
                # tier1 白名单: edge 略不足时降级置信度而非直接否决
                if sf_tier == "tier1" and sf_win_rate >= 0.70 and sf_sample >= 20:
                    dec.edge_approved = True
                    dec.confidence *= 0.85
                    dec.reason += f" | edge软通过(tier1) {info}"
                    dec.outcome = "sf_priority"
                else:
                    dec.sig = 0
                    dec.label = "HOLD"
                    dec.confidence = 0.0
                    dec.reason = info
                    dec.outcome = "edge_block"
                    return dec
            else:
                dec.edge_approved = True
                dec.reason += f" | {info}"
        except Exception as e:
            logger.debug("edge check skip: %s", e)
            dec.edge_approved = True
    else:
        dec.edge_approved = True

    # ── ML v15 (可选, 默认 advisory 不否决 SF) ──
    if p.ml_mode == "off" or not p.use_v15:
        if dec.outcome == "hold":
            dec.outcome = "pass"
        return dec

    ml = _run_ml_v15(prices, symbol)
    dec.ml_signal = int(ml.get("signal", 0))
    dec.ml_confidence = float(ml.get("confidence", 0.0))

    if dec.ml_signal == 0:
        dec.outcome = "pass"
        return dec

    if dec.ml_signal == sf_sig:
        dec.confidence = min(1.0, dec.confidence * (1.0 + dec.ml_confidence * 0.1))
        dec.reason += f" | ML确认({dec.ml_confidence:.0%})"
        dec.outcome = "ml_boost"
        return dec

    # ML 与 SF 冲突
    dec.conflict = True
    tier = (sf_tier or "").lower()

    # advisory: SF 优先, ML 仅记录
    if p.ml_mode == "advisory":
        dec.reason += f" | ML冲突({dec.ml_confidence:.0%})→SF优先[{tier}]"
        dec.outcome = "sf_priority"
        return dec

    # confirm: tier1/tier2 仍优先; 仅 tier3 + 高置信 ML 可否决
    if tier in p.sf_priority_tiers:
        dec.reason += f" | ML反对但{ tier }优先保留"
        dec.outcome = "sf_priority"
        return dec

    if dec.ml_confidence >= p.ml_veto_confidence:
        dec.sig = 0
        dec.label = "HOLD"
        dec.confidence = 0.0
        dec.reason = f"ML否决SF (conf={dec.ml_confidence:.0%} tier={tier})"
        dec.outcome = "ml_veto"
        return dec

    dec.reason += f" | ML弱反对({dec.ml_confidence:.0%})→保留SF"
    dec.outcome = "sf_priority"
    return dec


def auto_tune_sf_ml_params(
    sf_accuracy: float = 0.0,
    ml_accuracy: float = 0.0,
    conflict_count: int = 0,
    sf_won_when_conflict: int = 0,
) -> dict[str, Any]:
    """根据 SF/ML 相对表现生成 sf_ml 调参建议 (写入 strategy_params.sf_ml)."""
    # ML 弱于 SF 或样本不足 → advisory + 关闭 v15 否决
    if ml_accuracy < 0.53 or ml_accuracy < sf_accuracy - 0.05:
        ml_mode = "advisory"
        use_v15 = False
        ml_veto = 0.85
    elif ml_accuracy >= 0.58 and sf_accuracy >= 0.55:
        ml_mode = "confirm"
        use_v15 = True
        ml_veto = 0.75
    else:
        ml_mode = "advisory"
        use_v15 = ml_accuracy >= 0.50
        ml_veto = 0.80

    # 冲突时 SF 更常正确 → 提高 veto 门槛
    if conflict_count >= 5 and sf_won_when_conflict / max(conflict_count, 1) >= 0.6:
        ml_mode = "advisory"
        ml_veto = min(0.95, ml_veto + 0.05)

    return {
        "ml_mode": ml_mode,
        "use_v15": use_v15,
        "ml_veto_confidence": round(ml_veto, 2),
        "ml_oos_accuracy": round(ml_accuracy, 3),
        "sf_whitelist_accuracy": round(sf_accuracy, 3),
        "min_edge_by_tier": dict(TIER_MIN_EDGE),
        "min_edge_default": DEFAULT_MIN_EDGE,
        "sf_priority_tiers": ["tier1", "tier2"],
        "conflict_samples": conflict_count,
    }


def merge_sf_ml_into_params(params: dict[str, Any], sf_ml: dict[str, Any]) -> dict[str, Any]:
    """合并 sf_ml 块到 strategy_params."""
    out = dict(params)
    out["sf_ml"] = sf_ml
    out["ml_mode"] = sf_ml.get("ml_mode", "advisory")
    return out
