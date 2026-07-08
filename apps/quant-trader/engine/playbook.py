"""Playbook (多策略资金分桶) backtester.

A *playbook* splits capital into several **sleeves** (资金桶). Each sleeve runs
its own strategy / risk / sizing over its own basket of symbols. The sleeves'
equity curves are summed (plus idle cash) into one portfolio curve.

This lets you express a real trading plan like:
  - 主力(80%)：短期多笔、赚钱就跑、专注市场动向(动量趋势) ；
  - 卫星(20%)：定向参与新闻趋势利好。
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field

import pandas as pd

from ..strategy.base import get_strategy
from .metrics import infer_periods_per_year, performance_summary
from .portfolio_backtest import MultiBacktester
from .position_sizing import SizingConfig
from .risk import RiskConfig


@dataclass
class Sleeve:
    name: str
    weight: float  # fraction of total capital (0..1)
    strategy: str
    symbols: list[str]
    params: dict = field(default_factory=dict)
    allocation: str = "equal"  # within-sleeve allocation across its symbols
    risk: dict = field(default_factory=dict)
    sizing: dict = field(default_factory=dict)
    order_size: float = 0.2
    description: str = ""


@dataclass
class PlaybookResult:
    equity_curve: pd.Series
    per_sleeve: dict  # name -> {weight, stats, n_trades, symbols, equity_curve, ...}
    stats: dict
    weights: dict  # name -> weight
    idle_cash_pct: float


# Built-in playbook templates. Symbols are filled in by build_playbook().
PLAYBOOK_PRESETS: dict[str, dict] = {
    "short_momentum_news": {
        "label": "短打动量 + 新闻定向",
        "description": "主力短期多笔、赚钱就跑、专注市场动向；小仓定向参与新闻趋势利好。",
        "sleeves": [
            {
                "name": "主力·市场动向短打",
                "weight": 0.8,
                "strategy": "momentum",
                "params": {"lookback": 10, "trend_filter": 30},
                "allocation": "equal",
                "risk": {
                    "stop_loss": 0.04,
                    "take_profit": 0.05,
                    "trailing_stop": 0.03,
                    "max_drawdown": 0.12,
                    "risk_per_trade": 0.005,
                },
                "sizing": {
                    "max_position_pct": 0.20,
                    "max_total_exposure": 0.70,
                    "cash_reserve_pct": 0.30,
                    "max_weight_per_symbol": 0.25,
                    "allow_leverage": False,
                },
                "order_size": 0.20,
                "description": "快进快出，价格上穿短期动量就进，达到 +5% 就止盈，靠多笔小赚累积；紧止损 -4% 快出。",
            },
            {
                "name": "卫星·动量顺势",
                "weight": 0.2,
                "strategy": "news_blend",
                "params": {
                    "base": "momentum",
                    "lookback": 15,
                    "trend_filter": 40,
                    "news_weight": 0.5,
                    "confirm_bullish": True,
                    "block_bearish": True,
                    "sentiment": 0.0,
                },
                "allocation": "equal",
                "risk": {
                    "stop_loss": 0.06,
                    "take_profit": 0.10,
                    "trailing_stop": 0.06,
                    "max_drawdown": 0.15,
                    "risk_per_trade": 0.005,
                },
                "sizing": {
                    "max_position_pct": 0.15,
                    "max_total_exposure": 0.50,
                    "cash_reserve_pct": 0.50,
                    "max_weight_per_symbol": 0.20,
                    "allow_leverage": False,
                },
                "order_size": 0.15,
                "description": "卫星仓动量顺势：与主仓同逻辑但仓位更轻，目标 +10% 兑现；sentiment 可由请求体注入（新闻拉取已下线）。",
            },
        ],
    },
}


def list_playbooks() -> list[dict]:
    return [
        {
            "name": k,
            "label": v["label"],
            "description": v["description"],
            "sleeves": [
                {
                    "name": s["name"],
                    "weight": s["weight"],
                    "strategy": s["strategy"],
                    "description": s.get("description", ""),
                }
                for s in v["sleeves"]
            ],
        }
        for k, v in PLAYBOOK_PRESETS.items()
    ]


def build_playbook(
    name: str, symbols: list[str], news_symbols: list[str] | None = None, sentiment: float | None = None
) -> tuple[list[Sleeve], dict]:
    """Instantiate a preset playbook with the user's symbols.

    - symbols       : basket for the momentum/main sleeves
    - news_symbols  : optional separate basket for the news sleeve (defaults to symbols)
    - sentiment     : optional live news sentiment to inject into the news sleeve
    """
    key = (name or "short_momentum_news").lower()
    if key not in PLAYBOOK_PRESETS:
        raise ValueError(f"Unknown playbook {name!r}; choose: {list(PLAYBOOK_PRESETS)}")
    preset = deepcopy(PLAYBOOK_PRESETS[key])
    sleeves: list[Sleeve] = []
    for sd in preset["sleeves"]:
        is_news = sd["strategy"] == "news_blend"
        syms = (news_symbols or symbols) if is_news else symbols
        params = dict(sd.get("params", {}))
        if is_news and sentiment is not None:
            params["sentiment"] = float(sentiment)
        sleeves.append(
            Sleeve(
                name=sd["name"],
                weight=sd["weight"],
                strategy=sd["strategy"],
                symbols=list(syms),
                params=params,
                allocation=sd.get("allocation", "equal"),
                risk=dict(sd.get("risk", {})),
                sizing=dict(sd.get("sizing", {})),
                order_size=sd.get("order_size", 0.2),
                description=sd.get("description", ""),
            )
        )
    return sleeves, preset


def run_playbook(
    prices_by_symbol: dict[str, pd.DataFrame],
    sleeves: list[Sleeve],
    cash: float = 100_000.0,
    commission: float = 0.0005,
    slippage: float = 0.0005,
    lot_size: int = 1,
) -> PlaybookResult:
    if not sleeves:
        raise ValueError("No sleeves provided.")
    total_w = sum(s.weight for s in sleeves)
    if total_w > 1.0 + 1e-9:
        raise ValueError(f"Sleeve weights sum to {total_w:.2f} (>1). Reduce them or enable leverage.")

    curves = []
    per_sleeve: dict = {}
    weights: dict = {}

    for sl in sleeves:
        syms = [s for s in sl.symbols if s in prices_by_symbol and not prices_by_symbol[s].empty]
        if not syms or sl.weight <= 0:
            continue
        try:
            risk = RiskConfig(**sl.risk) if sl.risk else RiskConfig()
        except TypeError as e:
            raise ValueError(f"Sleeve {sl.name!r} bad risk config: {e}")
        try:
            sizing = SizingConfig(**sl.sizing) if sl.sizing else SizingConfig()
        except TypeError as e:
            raise ValueError(f"Sleeve {sl.name!r} bad sizing config: {e}")

        def factory(sl=sl):
            return get_strategy(sl.strategy, **sl.params)

        mbt = MultiBacktester(
            cash=cash * sl.weight,
            allocation=sl.allocation,
            order_size=sl.order_size,
            commission=commission,
            slippage=slippage,
            lot_size=lot_size,
            risk=risk,
            sizing=sizing,
        )
        res = mbt.run({s: prices_by_symbol[s] for s in syms}, factory)
        curves.append(res.equity_curve.rename(sl.name))
        weights[sl.name] = sl.weight
        per_sleeve[sl.name] = {
            "weight": sl.weight,
            "description": sl.description,
            "strategy": sl.strategy,
            "symbols": syms,
            "stats": res.stats,
            "n_trades": res.n_trades,
            "equity_curve": res.equity_curve,
        }

    if not curves:
        raise RuntimeError("No sleeve produced a usable equity curve (check symbols).")

    combined = pd.concat(curves, axis=1).sort_index().ffill()
    for name in combined.columns:
        combined[name] = combined[name].fillna(cash * weights[name])
    portfolio_curve = combined.sum(axis=1)
    used_w = sum(weights.values())
    idle = cash * (1.0 - used_w)
    if idle > 0:
        portfolio_curve = portfolio_curve + idle
    portfolio_curve.name = "equity"

    return PlaybookResult(
        equity_curve=portfolio_curve,
        per_sleeve=per_sleeve,
        stats=performance_summary(
            portfolio_curve, periods_per_year=infer_periods_per_year(portfolio_curve.index)
        ),
        weights=weights,
        idle_cash_pct=max(0.0, 1.0 - used_w),
    )
