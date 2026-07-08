"""Parameter optimization with overfitting safeguards.

`grid_search` finds the best parameters on a price series. `walk_forward`
repeatedly optimizes on a training window and evaluates on the *next* unseen
window, so you measure out-of-sample (OOS) performance — the only number that
matters for real trading. A big gap between in-sample and OOS results is the
classic signature of curve-fitting.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any

import pandas as pd

from ..strategy.base import get_strategy
from .backtest import Backtester
from .futures_backtest import FuturesBacktestConfig, FuturesBacktester
from .risk import RiskConfig


def _expand_grid(grid: dict) -> list[dict]:
    if not grid:
        return [{}]
    keys = list(grid.keys())
    combos = itertools.product(*[grid[k] for k in keys])
    return [dict(zip(keys, c)) for c in combos]


def _score(stats: dict, metric: str, min_trades: int = 0) -> float:
    # 交易样本不足时统计不可信（如单笔持有伪装成的高 Sharpe），判为无效，杜绝「低交易假最优」。
    if min_trades:
        n_trades = stats.get("n_trades")
        if n_trades is not None and n_trades < min_trades:
            return float("-inf")
    val = stats.get(metric)
    if val is None:
        return float("-inf")
    try:
        f = float(val)
    except (TypeError, ValueError):
        return float("-inf")
    return f if f == f else float("-inf")  # guard NaN


@dataclass
class OptResult:
    best_params: dict
    best_score: float
    metric: str
    results: list  # list of (params, stats), sorted best-first


def _valid_params(strategy_name: str, params: dict) -> bool:
    """Skip invalid parameter combos before backtest (e.g. fast >= slow)."""
    name = (strategy_name or "").lower()
    fast = params.get("fast")
    slow = params.get("slow")
    if fast is not None and slow is not None:
        try:
            if int(fast) >= int(slow):
                return False
        except (TypeError, ValueError):
            return False
    if name == "macd":
        sig = params.get("signal")
        if fast is not None and sig is not None:
            try:
                if int(fast) >= int(sig):
                    return False
            except (TypeError, ValueError):
                pass
    return True


def _run_backtest(prices, strategy_name, params, metric_engine, risk, futures_cfg, **bt_kwargs):
    """Run equity Backtester or FuturesBacktester and return stats dict."""
    strat = get_strategy(strategy_name, **params)
    if metric_engine == "futures":
        cfg = FuturesBacktestConfig(**(futures_cfg or {}))
        return FuturesBacktester(cfg).run(prices, strat).stats
    return Backtester(risk=risk, **bt_kwargs).run(prices, strat).stats


def grid_search(
    prices: pd.DataFrame,
    strategy_name: str,
    param_grid: dict,
    metric: str = "sharpe",
    risk: RiskConfig | None = None,
    engine: str = "equity",
    futures: dict | None = None,
    min_trades: int = 0,
    **bt_kwargs,
) -> OptResult:
    """Evaluate every parameter combination; return them ranked by `metric`."""
    rows = []
    for params in _expand_grid(param_grid):
        if not _valid_params(strategy_name, params):
            continue
        try:
            stats = _run_backtest(
                prices, strategy_name, params, engine, risk, futures, **bt_kwargs
            )
            rows.append((params, stats))
        except Exception:
            continue
    rows.sort(key=lambda r: _score(r[1], metric, min_trades), reverse=True)
    if not rows:
        raise RuntimeError("No parameter combination produced a valid result.")
    best_params, best_stats = rows[0]
    # best_score 用真实分数（不二次惩罚）；交易是否充足由 stats["n_trades"] 透传给上层展示。
    return OptResult(best_params, _score(best_stats, metric), metric, rows)


@dataclass
class WalkForwardResult:
    metric: str
    folds: list  # list of dicts: train_params, is_score, oos_stats
    avg_oos_return: float
    avg_oos_sharpe: float
    overfit_gap: float  # mean(in-sample score) - mean(OOS score)


def walk_forward(
    prices: pd.DataFrame,
    strategy_name: str,
    param_grid: dict,
    n_splits: int = 4,
    metric: str = "sharpe",
    risk: RiskConfig | None = None,
    engine: str = "equity",
    futures: dict | None = None,
    min_trades: int = 0,
    **bt_kwargs,
) -> WalkForwardResult:
    """Rolling train/test optimization.

    Splits the series into `n_splits + 1` contiguous blocks; for each step,
    optimize on the cumulative history and test on the following block.
    """
    n = len(prices)
    if n < (n_splits + 1) * 20:
        raise ValueError("Not enough bars for the requested number of splits.")

    # Use positional splits — robust to datetime vs string vs integer indices.
    bounds = [int(n * i / (n_splits + 1)) for i in range(n_splits + 2)]
    folds = []
    is_scores, oos_scores, oos_rets, oos_sharpes = [], [], [], []

    for k in range(1, n_splits + 1):
        train = prices.iloc[: bounds[k]]
        test = prices.iloc[bounds[k] : bounds[k + 1]]
        if len(test) < 10:
            continue

        opt = grid_search(
            train, strategy_name, param_grid, metric=metric, risk=risk,
            engine=engine, futures=futures, min_trades=min_trades, **bt_kwargs,
        )
        strat = get_strategy(strategy_name, **opt.best_params)
        if engine == "futures":
            oos_stats = FuturesBacktester(
                FuturesBacktestConfig(**(futures or {}))
            ).run(test, strat).stats
        else:
            oos_stats = Backtester(risk=risk, **bt_kwargs).run(test, strat).stats
        oos = type("O", (), {"stats": oos_stats})()

        is_scores.append(opt.best_score)
        oos_scores.append(_score(oos.stats, metric))
        oos_rets.append(oos.stats.get("total_return", 0.0))
        oos_sharpes.append(oos.stats.get("sharpe", 0.0))
        folds.append(
            {
                "train_bars": len(train),
                "test_bars": len(test),
                "best_params": opt.best_params,
                "is_score": opt.best_score,
                "oos_stats": oos.stats,
            }
        )

    if not folds:
        raise RuntimeError("Walk-forward produced no usable folds.")

    def mean(xs: list[float]) -> float:
        return sum(xs) / len(xs) if xs else 0.0

    return WalkForwardResult(
        metric=metric,
        folds=folds,
        avg_oos_return=mean(oos_rets),
        avg_oos_sharpe=mean(oos_sharpes),
        overfit_gap=mean(is_scores) - mean(oos_scores),
    )


# Sensible default grids per strategy for the CLI `optimize` command.
# 参数网格值为 int/float 混合列表, 显式标注避免推断成 dict[str, object]
DEFAULT_GRIDS: dict[str, dict[str, Any]] = {
    "sma_cross": {"fast": [5, 10, 20, 30], "slow": [50, 100, 150, 200]},
    "rsi": {"period": [7, 14, 21], "oversold": [20, 30], "overbought": [70, 80]},
    "bollinger": {"period": [10, 20, 30], "num_std": [1.5, 2.0, 2.5]},
    "momentum": {"lookback": [20, 60, 90, 120], "trend_filter": [0, 100, 200]},
    "macd": {"fast": [8, 12], "slow": [21, 26], "signal": [7, 9]},
    "trend_follow": {"fast": [10, 20, 30], "slow": [50, 60, 90]},
    "deep_dip": {"ma_long": [40, 60], "entry_dev": [-0.05, -0.08, -0.10, -0.12], "max_hold": [15, 20, 30]},
    "supertrend": {"period": [10, 14], "multiplier": [2.5, 3.0, 3.5]},
    "kdj": {"period": [9, 14]},
    "volume_breakout": {"lookback": [15, 20, 30], "vol_multiplier": [1.5, 2.0]},
    "ichimoku": {"tenkan": [9, 12], "kijun": [26, 30]},
    "vwap_cross": {"period": [15, 20, 30]},
    "ma_ribbon": {"slow_tail": [40, 60, 80]},
}

STRATEGY_LABELS: dict[str, str] = {
    "sma_cross": "SMA交叉",
    "rsi": "RSI",
    "bollinger": "布林带",
    "momentum": "动量",
    "macd": "MACD",
    "trend_follow": "趋势跟随",
    "deep_dip": "深超跌",
    "supertrend": "SuperTrend",
    "kdj": "KDJ",
    "volume_breakout": "放量突破",
    "ichimoku": "一目均衡",
    "vwap_cross": "VWAP交叉",
    "ma_ribbon": "均线带",
}

STRATEGY_GROUPS: dict[str, str] = {
    "sma_cross": "classic",
    "rsi": "classic",
    "bollinger": "classic",
    "momentum": "classic",
    "macd": "tech",
    "trend_follow": "tech",
    "supertrend": "tech",
    "kdj": "tech",
    "volume_breakout": "tech",
    "ichimoku": "tech",
    "vwap_cross": "tech",
    "ma_ribbon": "tech",
    "deep_dip": "mean_rev",
}

STRATEGY_TIPS: dict[str, list[str]] = {
    "sma_cross": [
        "快慢均线差距过小会贴近噪声，样本外易失效",
        "趋势不明显时交叉频繁，建议配合更长 slow 周期",
    ],
    "rsi": [
        "超买超卖阈值在震荡市有效，单边趋势市易过早离场",
        "period 过短会放大假信号",
    ],
    "bollinger": [
        "num_std 越小越敏感，适合波动率稳定的标的",
        "突破型行情下布林带均值回归可能连续亏损",
    ],
    "momentum": [
        "lookback 需与标的波动周期匹配",
        "trend_filter>0 可过滤逆势动量信号，降低回撤",
    ],
    "macd": [
        "fast/slow 组合不宜与 SMA 交叉参数完全重合",
        "signal 过短会增加换手与滑点成本",
    ],
    "trend_follow": [
        "适合期货 CTA / 趋势明显的权益标的",
        "fast 接近 slow 时信号滞后与噪声并存",
    ],
    "deep_dip": [
        "entry_dev 越深抄底越少但单笔质量可能更高",
        "max_hold 防止长期套牢，需与 ma_exit 配合观察",
    ],
    "supertrend": [
        "multiplier 越大止损越宽，适合高波动品种",
        "震荡市易被反复洗出，关注 overfit_gap",
    ],
    "kdj": [
        "短周期 KDJ 对噪声敏感，建议 Walk-Forward 验证",
    ],
    "volume_breakout": [
        "vol_multiplier 过低会产生大量假突破",
        "lookback 需覆盖至少一个完整波动周期",
    ],
    "ichimoku": [
        "senkou_b 周期决定云图宽度，过长会减少信号",
        "TK 金叉需价格在云图之上才有效",
    ],
    "vwap_cross": [
        "无 volume 列时策略不产出信号",
        "period 过短对噪声敏感",
    ],
    "ma_ribbon": [
        "slow_tail 控制最长均线周期，影响趋势确认滞后",
        "震荡市均线缠绕时易频繁切换",
    ],
}

OPTIMIZE_METRICS = ["sharpe", "total_return", "sortino", "cagr"]


def grid_combo_count(grid: dict) -> int:
    if not grid:
        return 1
    n = 1
    for vals in grid.values():
        n *= len(vals)
    return n


def optimize_catalog() -> dict:
    """Metadata for dashboard: grids, labels, analysis tips."""
    group_labels = {
        "classic": "经典",
        "tech": "技术",
        "mean_rev": "均值回归",
    }
    strategies: dict[str, dict] = {}
    for name, grid in DEFAULT_GRIDS.items():
        strategies[name] = {
            "label": STRATEGY_LABELS.get(name, name),
            "group": STRATEGY_GROUPS.get(name, "other"),
            "group_label": group_labels.get(STRATEGY_GROUPS.get(name, ""), "其他"),
            "grid": grid,
            "combo_count": grid_combo_count(grid),
            "metrics": list(OPTIMIZE_METRICS),
            "tips": STRATEGY_TIPS.get(name, []),
        }
    return {
        "strategies": strategies,
        "metrics": list(OPTIMIZE_METRICS),
        "group_labels": group_labels,
    }
