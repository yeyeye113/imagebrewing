"""期权定价模块 — Black-Scholes定价、希腊字母、策略分析、波动率计算。"""

from quanttrader.options.greeks import compute_greeks, greeks_table
from quanttrader.options.pricing import black_scholes_price, black_scholes_vectorized
from quanttrader.options.strategies import (
    bear_spread,
    bull_spread,
    covered_call,
    iron_condor,
    protective_put,
    straddle,
)
from quanttrader.options.volatility import (
    garman_klass_volatility,
    historical_volatility,
    implied_volatility,
    implied_volatility_surface,
    parkinson_volatility,
)

__all__ = [
    "bear_spread",
    # pricing
    "black_scholes_price",
    "black_scholes_vectorized",
    "bull_spread",
    # greeks
    "compute_greeks",
    # strategies
    "covered_call",
    "garman_klass_volatility",
    "greeks_table",
    "historical_volatility",
    # volatility
    "implied_volatility",
    "implied_volatility_surface",
    "iron_condor",
    "parkinson_volatility",
    "protective_put",
    "straddle",
]
