from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path

import yaml


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into a copy of *base*.

    For dict values the merge is recursive; for everything else the
    override wins.  Lists are replaced, not extended.
    """
    merged = copy.deepcopy(base)
    for key, val in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(val, dict):
            merged[key] = _deep_merge(merged[key], val)
        else:
            merged[key] = copy.deepcopy(val)
    return merged


@dataclass
class Config:
    symbol: str = "AAPL"
    symbols: list = field(default_factory=list)  # multi-asset portfolio backtest
    allocation: str = "equal"  # "equal" | "inverse_vol"
    data_source: str = "synthetic"
    data_path: str = ""  # path to CSV when data_source == "csv"
    start: str = "2022-01-01"
    end: str = "2024-01-01"
    interval: str = "1d"
    strategy: dict = field(default_factory=lambda: {"name": "sma_cross", "fast": 20, "slow": 50})
    cash: float = 100_000.0
    order_size: float = 0.25  # per-signal fraction of usable cash (capped by sizing)
    commission: float = 0.0005
    slippage: float = 0.0005
    lot_size: int = 1  # set to 100 for A-share whole-lot backtests
    # Position limits — prevent all-in. See engine/position_sizing.py.
    sizing: dict = field(
        default_factory=lambda: {
            "max_position_pct": 0.30,  # 单票最多占净值 30%
            "max_total_exposure": 0.80,  # 总仓位不超过 80%
            "cash_reserve_pct": 0.20,  # 至少保留 20% 现金
            "max_weight_per_symbol": 0.25,  # 组合中单票权重上限 25%
            "allow_leverage": False,  # 禁止杠杆：永不超过手头现金
            "target_volatility": 0.0,  # 波动率目标(年化, 0=关闭, 如 0.20)
            "vol_lookback": 20,  # 估计已实现波动率的回看根数
        }
    )
    # Risk-management rules (fractions; 0 disables). See engine/risk.py.
    risk: dict = field(
        default_factory=lambda: {
            "stop_loss": 0.0,
            "take_profit": 0.0,
            "trailing_stop": 0.0,
            "max_drawdown": 0.0,
            "risk_per_trade": 0.01,
        }
    )
    broker: dict = field(default_factory=lambda: {"name": "paper", "paper": True, "poll_seconds": 60})
    # Investment horizon: short | medium | long — auto-tunes strategy/risk/sizing.
    horizon: str = "medium"
    news: dict = field(default_factory=lambda: {"source": "auto", "enabled": False, "limit": 20})
    _source_path: str = ""  # path this config was loaded from (for --apply)

    @classmethod
    def load(cls, path: str | None) -> Config:
        if not path:
            return cls()
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}

        # ── _extends: inherit from a base config file ──
        base_ref = data.pop("_extends", None)
        if base_ref:
            base_path = (p.parent / base_ref).resolve()
            if not base_path.exists():
                raise FileNotFoundError(
                    f"Base config not found: {base_path} (referenced by _extends in {path})"
                )
            base_data = yaml.safe_load(base_path.read_text(encoding="utf-8")) or {}
            # Remove _extends from base too (in case of chaining)
            base_data.pop("_extends", None)
            data = _deep_merge(base_data, data)

        known = {f for f in cls.__dataclass_fields__ if not f.startswith("_")}
        cfg = cls(**{k: v for k, v in data.items() if k in known})
        cfg._source_path = str(p)
        return cfg
