"""Portfolio stress testing — scenario-based risk analysis.

Applies predefined or custom shock scenarios to positions and measures:
  - PnL impact under each scenario
  - Maximum drawdown per scenario
  - Recovery time estimate

Usage:
    from quanttrader.advanced_risk.stress import StressTest, StressScenario

    # Define portfolio positions
    positions = {"600519": 100, "601318": 200}  # symbol -> qty

    # Load price history
    prices = pd.DataFrame({...})  # columns = symbols, index = dates

    # Run stress test
    st = StressTest(positions=positions, prices=prices)
    results = st.run()
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# ── Built-in Scenarios ──────────────────────────────────────────────


@dataclass
class StressScenario:
    """A named market shock scenario.

    Attributes:
        name: human-readable label.
        shocks: dict mapping symbol -> shock fraction (e.g. -0.30 = 30% drop).
        market_shock: if set, applied to ALL symbols not in `shocks`.
        description: for reporting.
    """

    name: str
    shocks: dict[str, float] = field(default_factory=dict)
    market_shock: float = 0.0
    description: str = ""


# Common historical stress scenarios (Chinese market context)
BUILTIN_SCENARIOS: list[StressScenario] = [
    StressScenario(
        name="2015_crash",
        description="2015 A-share crash: broad -30% to -45% drawdown",
        market_shock=-0.35,
        shocks={
            "601318": -0.40,  # insurance sector hit harder
            "600036": -0.38,
        },
    ),
    StressScenario(
        name="2018_trade_war",
        description="2018 US-China trade war escalation",
        market_shock=-0.25,
        shocks={
            "002230": -0.35,  # tech/export-heavy
        },
    ),
    StressScenario(
        name="2020_covid",
        description="COVID-19 initial shock (Feb-Mar 2020)",
        market_shock=-0.15,
        shocks={
            "601318": -0.25,
            "600519": -0.10,  # consumer staple relatively resilient
        },
    ),
    StressScenario(
        name="rate_hike",
        description="Sudden 50bp rate hike — bond-sensitive sectors drop",
        market_shock=-0.05,
        shocks={
            "601318": -0.15,
            "600036": -0.12,
        },
    ),
    StressScenario(
        name="liquidity_crisis",
        description="Flash crash / liquidity withdrawal: broad -10% in 1 day",
        market_shock=-0.10,
    ),
]


class StressTest:
    """Portfolio stress tester.

    Args:
        positions: dict of {symbol: quantity_held}.
        prices: DataFrame with columns = symbols, index = date (close prices).
        scenarios: list of StressScenario; defaults to BUILTIN_SCENARIOS.
        risk_free_rate: annual risk-free rate for recovery calculations.
    """

    def __init__(
        self,
        positions: dict[str, int | float],
        prices: pd.DataFrame,
        scenarios: list[StressScenario] | None = None,
        risk_free_rate: float = 0.02,
    ):
        self.positions = positions
        self.prices = prices.copy()
        self.scenarios = scenarios or BUILTIN_SCENARIOS
        self.risk_free_rate = risk_free_rate

        # Validate
        missing = set(positions) - set(prices.columns)
        if missing:
            raise ValueError(f"Missing price data for: {missing}")

    def run(self) -> list[dict]:
        """Run all scenarios, return list of result dicts sorted by severity."""
        results = []
        base_pnl = self._portfolio_value(self.prices.iloc[-1])

        for scenario in self.scenarios:
            result = self._run_scenario(scenario, base_pnl)
            results.append(result)

        results.sort(key=lambda r: r["pnl_impact"])
        return results

    def run_single(self, scenario: StressScenario) -> dict:
        """Run a single custom scenario."""
        base_pnl = self._portfolio_value(self.prices.iloc[-1])
        return self._run_scenario(scenario, base_pnl)

    def worst_case(self) -> dict:
        """Run all scenarios and return the single worst case."""
        results = self.run()
        return results[0] if results else {}

    def _run_scenario(self, scenario: StressScenario, base_pnl: float) -> dict:
        """Apply a scenario shock and compute PnL impact."""
        # Build shock vector per symbol
        shock_map = {}
        for sym in self.positions:
            shock_map[sym] = scenario.shocks.get(sym, scenario.market_shock)

        # Post-shock portfolio value
        last_prices = self.prices.iloc[-1]
        stressed_prices = {}
        for sym, price in last_prices.items():
            if sym in self.positions:
                shocked_price = price * (1 + shock_map.get(sym, 0))
                stressed_prices[sym] = shocked_price

        stressed_pnl = self._portfolio_value_from_prices(stressed_prices)
        pnl_impact = stressed_pnl - base_pnl
        pnl_pct = pnl_impact / base_pnl if base_pnl != 0 else 0.0

        # Estimate max drawdown under this scenario
        max_dd = self._estimate_max_dd(scenario)

        # Estimate recovery days (days to recover from this loss at avg return)
        avg_daily_return = self.prices.pct_change().mean().mean()
        recovery_days = self._estimate_recovery(abs(pnl_pct), avg_daily_return)

        return {
            "scenario": scenario.name,
            "description": scenario.description,
            "base_value": base_pnl,
            "stressed_value": stressed_pnl,
            "pnl_impact": pnl_impact,
            "pnl_pct": pnl_pct,
            "max_drawdown_estimate": max_dd,
            "recovery_days_estimate": recovery_days,
            "per_symbol_shock": shock_map,
            "per_symbol_loss": {sym: self.positions[sym] * last_prices[sym] * shock_map[sym] for sym in self.positions},
        }

    def _portfolio_value(self, prices_row: pd.Series) -> float:
        return float(sum(self.positions[sym] * prices_row[sym] for sym in self.positions))

    def _portfolio_value_from_prices(self, price_dict: dict[str, float]) -> float:
        return sum(self.positions[sym] * price_dict[sym] for sym in self.positions)

    def _estimate_max_dd(self, scenario: StressScenario) -> float:
        """Simple heuristic: worst single-day historical loss * scenario multiplier."""
        if self.prices.empty:
            return scenario.market_shock
        returns = self.prices.pct_change().dropna()
        worst_day = returns.min().min()
        # Scale worst day by scenario severity
        scenario_severity = abs(scenario.market_shock)
        return float(worst_day * scenario_severity / max(abs(worst_day), 0.001))

    def _estimate_recovery(self, loss_pct: float, avg_daily_return: float) -> int:
        """Estimate days to recover from loss_pct at avg_daily_return."""
        if avg_daily_return <= 0:
            return 9999  # no recovery expected
        # loss_pct = loss as positive fraction; need to earn it back
        # log(1 + loss_pct) / log(1 + avg_daily_return)
        if loss_pct <= 0:
            return 0
        import math

        days = math.log(1 + loss_pct) / math.log(1 + avg_daily_return)
        return max(0, int(np.ceil(days)))
