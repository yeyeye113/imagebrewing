"""Investment horizon presets — short / medium / long term.

Maps each horizon to strategy params, risk, sizing, and data window so users
don't have to tune everything manually.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

HORIZON_PRESETS: dict[str, dict] = {
    "scalp": {
        "label": "短打 (数小时~数日)",
        "description": "专注市场动向,多笔小赚、达标即止盈(+5%),紧止损(-4%)快出。",
        "interval": "1d",
        "start_offset_years": 1,
        "strategy": {"name": "momentum", "lookback": 10, "trend_filter": 30},
        "risk": {
            "stop_loss": 0.04,
            "take_profit": 0.05,
            "trailing_stop": 0.03,
            "max_drawdown": 0.12,
            "risk_per_trade": 0.005,
        },
        "sizing": {
            "max_position_pct": 0.20,
            "max_total_exposure": 0.65,
            "cash_reserve_pct": 0.35,
            "max_weight_per_symbol": 0.20,
        },
        "order_size": 0.15,
        "news_weight": 0.45,
    },
    "short": {
        "label": "短线 (数日~数周)",
        "description": "快进快出,紧止损,小仓位,适合波动交易。",
        "interval": "1d",
        "start_offset_years": 1,
        "strategy": {"name": "rsi", "period": 14, "oversold": 30, "overbought": 70},
        "risk": {
            "stop_loss": 0.05,
            "take_profit": 0.10,
            "trailing_stop": 0.08,
            "max_drawdown": 0.15,
            "risk_per_trade": 0.005,
        },
        "sizing": {
            "max_position_pct": 0.20,
            "max_total_exposure": 0.60,
            "cash_reserve_pct": 0.30,
            "max_weight_per_symbol": 0.20,
        },
        "order_size": 0.15,
        "news_weight": 0.40,
    },
    "medium": {
        "label": "中线 (数周~数月)",
        "description": "趋势+均值回归平衡,标准风控,适合大多数策略验证。",
        "interval": "1d",
        "start_offset_years": 3,
        "strategy": {"name": "sma_cross", "fast": 20, "slow": 50},
        "risk": {
            "stop_loss": 0.08,
            "take_profit": 0.0,
            "trailing_stop": 0.15,
            "max_drawdown": 0.25,
            "risk_per_trade": 0.01,
        },
        "sizing": {
            "max_position_pct": 0.30,
            "max_total_exposure": 0.80,
            "cash_reserve_pct": 0.20,
            "max_weight_per_symbol": 0.25,
        },
        "order_size": 0.25,
        "news_weight": 0.25,
    },
    "long": {
        "label": "长线 (数月~数年)",
        "description": "宽止损+移动止盈,较大仓位上限,动量/趋势为主。",
        "interval": "1d",
        "start_offset_years": 5,
        "strategy": {"name": "momentum", "lookback": 120, "trend_filter": 200},
        "risk": {
            "stop_loss": 0.12,
            "take_profit": 0.0,
            "trailing_stop": 0.20,
            "max_drawdown": 0.30,
            "risk_per_trade": 0.015,
        },
        "sizing": {
            "max_position_pct": 0.35,
            "max_total_exposure": 0.85,
            "cash_reserve_pct": 0.15,
            "max_weight_per_symbol": 0.30,
        },
        "order_size": 0.30,
        "news_weight": 0.15,
    },
}


@dataclass
class HorizonInfo:
    name: str
    label: str
    description: str
    preset: dict


def list_horizons() -> list[HorizonInfo]:
    return [
        HorizonInfo(name=k, label=v["label"], description=v["description"], preset=v)
        for k, v in HORIZON_PRESETS.items()
    ]


def get_horizon(name: str) -> dict:
    key = (name or "medium").lower()
    if key not in HORIZON_PRESETS:
        raise ValueError(f"Unknown horizon {name!r}; choose: {list(HORIZON_PRESETS)}")
    return deepcopy(HORIZON_PRESETS[key])


def apply_horizon(cfg, horizon: str) -> None:
    """Merge horizon preset into a Config instance (in-place). Preset wins."""
    preset = get_horizon(horizon)
    cfg.horizon = horizon
    cfg.interval = preset.get("interval", cfg.interval)
    cfg.strategy = {**cfg.strategy, **preset.get("strategy", {})}
    cfg.risk = {**cfg.risk, **preset.get("risk", {})}
    cfg.sizing = {**cfg.sizing, **preset.get("sizing", {})}
    cfg.order_size = preset.get("order_size", cfg.order_size)
