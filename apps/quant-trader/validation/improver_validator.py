"""改进验证器 — 每次改动后对比回测，确保不降低预测准确性。

用法:
    from quanttrader.validation.improver_validator import validate_improvement
    result = validate_improvement(
        symbol="600519",
        baseline_params={"fast": 20, "slow": 60},
        improved_params={"fast": 20, "slow": 60, "news_weight": 0.15},
        strategy_name="sma_cross",
    )
    print(result)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


@dataclass
class ValidationResult:
    """验证结果 — 对比 baseline vs improved。"""

    symbol: str
    metric: str
    baseline_value: float
    improved_value: float
    change_pct: float  # (improved - baseline) / |baseline| * 100
    passed: bool  # True = 改进有效且不降质
    baseline_stats: dict = field(default_factory=dict)
    improved_stats: dict = field(default_factory=dict)
    reason: str = ""

    def summary(self) -> str:
        arrow = "↑" if self.change_pct > 0 else ("↓" if self.change_pct < 0 else "→")
        status = "PASS" if self.passed else "FAIL"
        return (
            f"[{status}] {self.symbol} {self.metric}: "
            f"{self.baseline_value:.4f} → {self.improved_value:.4f} "
            f"({self.change_pct:+.2f}% {arrow}) {self.reason}"
        )


def _load_prices(symbol: str, source: str = "akshare") -> pd.DataFrame | None:
    """加载行情数据。"""
    try:
        from quanttrader.data.base import BarRequest, get_feed

        req = BarRequest(symbol=symbol, start="", end="", interval="1d")
        prices = get_feed(source).history(req)
        if prices is not None and len(prices) >= 60:
            return prices
    except Exception:
        pass
    # fallback synthetic
    try:
        from quanttrader.data.base import BarRequest, get_feed

        req = BarRequest(symbol=symbol, start="", end="", interval="1d")
        return get_feed("synthetic").history(req)
    except Exception:
        return None


def _run_backtest(
    prices: pd.DataFrame, strategy_name: str, params: dict, risk: dict | None = None, cash: float = 100_000
) -> dict:
    """运行回测，返回 stats。"""
    from quanttrader.engine.backtest import Backtester
    from quanttrader.engine.risk import RiskConfig
    from quanttrader.strategy.base import get_strategy

    risk_cfg = RiskConfig(**risk) if risk else RiskConfig()
    strat = get_strategy(strategy_name, **params)
    bt = Backtester(cash=cash, risk=risk_cfg)
    result = bt.run(prices, strat)
    return result.stats


def validate_improvement(
    symbol: str,
    strategy_name: str,
    baseline_params: dict,
    improved_params: dict,
    metric: str = "sharpe",
    risk: dict | None = None,
    source: str = "akshare",
    min_improvement_pct: float = 0.1,  # 至少提升0.1%才认为有效
) -> ValidationResult:
    """验证改进：对比 baseline vs improved 的指定指标。

    通过条件:
      1. improved 的 metric >= baseline (不降质)
      2. 改善幅度 >= min_improvement_pct (有效果)
    """
    prices = _load_prices(symbol, source)
    if prices is None:
        return ValidationResult(
            symbol=symbol,
            metric=metric,
            baseline_value=0,
            improved_value=0,
            change_pct=0,
            passed=False,
            reason="数据加载失败",
        )

    baseline_stats = _run_backtest(prices, strategy_name, baseline_params, risk)
    improved_stats = _run_backtest(prices, strategy_name, improved_params, risk)

    bv = baseline_stats.get(metric, 0)
    iv = improved_stats.get(metric, 0)

    if abs(bv) < 1e-9:
        change_pct = 0.0 if abs(iv) < 1e-9 else 100.0
    else:
        change_pct = (iv - bv) / abs(bv) * 100

    passed = (iv >= bv) and (change_pct >= min_improvement_pct)
    reason = ""
    if iv < bv:
        reason = f"降质了({metric}下降)"
    elif change_pct < min_improvement_pct:
        reason = f"改善不足({change_pct:.2f}% < {min_improvement_pct}%)"

    return ValidationResult(
        symbol=symbol,
        metric=metric,
        baseline_value=bv,
        improved_value=iv,
        change_pct=change_pct,
        passed=passed,
        baseline_stats=baseline_stats,
        improved_stats=improved_stats,
        reason=reason,
    )


def validate_multi_metrics(
    symbol: str,
    strategy_name: str,
    baseline_params: dict,
    improved_params: dict,
    metrics: list[str] | None = None,
    risk: dict | None = None,
    source: str = "akshare",
) -> dict[str, ValidationResult]:
    """多指标验证 — 所有指标都不能降质。"""
    if metrics is None:
        metrics = ["sharpe", "total_return", "max_drawdown"]

    results = {}
    for m in metrics:
        # max_drawdown 是负数，越小越好（绝对值越大越差）
        if m == "max_drawdown":
            r = validate_improvement(symbol, strategy_name, baseline_params, improved_params, m, risk, source)
            # max_drawdown: improved 应该 >= baseline (负数，越大=回撤越小)
            r.passed = r.improved_value >= r.baseline_value
        else:
            r = validate_improvement(symbol, strategy_name, baseline_params, improved_params, m, risk, source)
        results[m] = r

    return results


def save_validation_report(results: dict[str, ValidationResult], path: str = "logs/validation_report.json"):
    """保存验证报告到文件。"""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    report = {
        "results": {
            k: {
                "symbol": v.symbol,
                "metric": v.metric,
                "baseline": v.baseline_value,
                "improved": v.improved_value,
                "change_pct": round(v.change_pct, 2),
                "passed": v.passed,
                "reason": v.reason,
            }
            for k, v in results.items()
        },
        "all_passed": all(r.passed for r in results.values()),
    }
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
