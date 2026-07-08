"""常见期权策略 — 备兑开仓、保护性看跌、跨式、价差等。"""

from dataclasses import dataclass
from typing import Literal

from quanttrader.options.greeks import portfolio_greeks
from quanttrader.options.pricing import black_scholes_price


@dataclass(frozen=True)
class StrategyLeg:
    """策略单腿。"""

    option_type: str
    action: str  # 'buy' or 'sell'
    strike: float
    quantity: int
    price: float


@dataclass(frozen=True)
class StrategyResult:
    """策略分析结果。"""

    name: str
    legs: list[StrategyLeg]
    total_cost: float  # 正=净支出, 负=净收入
    max_profit: float
    max_loss: float
    breakeven: list[float]
    greeks: dict
    description: str


def covered_call(
    S: float,
    K_call: float,
    T: float,
    r: float,
    sigma: float,
) -> StrategyResult:
    """
    备兑开仓 (Covered Call): 买入标的 + 卖出虚值看涨期权。

    参数:
        S: 标的价格
        K_call: 卖出看涨的行权价
        T: 到期时间(年)
        r: 无风险利率
        sigma: 波动率
    """
    call_price = black_scholes_price(S, K_call, T, r, sigma, "call").price

    # 买入标的花费 S，卖出 call 收入 call_price
    net_cost = S - call_price
    max_profit = K_call - net_cost  # 标的涨到行权价
    max_loss = -net_cost  # 标的跌到0
    breakeven = [net_cost]

    positions = [
        {"S": S, "K": K_call, "T": T, "r": r, "sigma": sigma, "option_type": "call", "quantity": -1},
    ]
    g = portfolio_greeks(positions)
    # 加上标的 delta (标的本身 delta=1)
    g["delta"] = round(g["delta"] + 1.0, 4)

    return StrategyResult(
        name="备兑开仓 (Covered Call)",
        legs=[StrategyLeg("call", "sell", K_call, 1, call_price)],
        total_cost=net_cost,
        max_profit=round(max_profit, 2),
        max_loss=round(max_loss, 2),
        breakeven=breakeven,
        greeks=g,
        description=f"买入标的@{S:.2f} + 卖出Call@{K_call}，净支出{net_cost:.2f}",
    )


def protective_put(
    S: float,
    K_put: float,
    T: float,
    r: float,
    sigma: float,
) -> StrategyResult:
    """
    保护性看跌 (Protective Put): 买入标的 + 买入看跌期权（保险）。
    """
    put_price = black_scholes_price(S, K_put, T, r, sigma, "put").price
    net_cost = S + put_price
    max_profit = float("inf")  # 无上限
    max_loss = net_cost - K_put  # 行权价保护
    breakeven = [S + put_price]

    positions = [
        {"S": S, "K": K_put, "T": T, "r": r, "sigma": sigma, "option_type": "put", "quantity": 1},
    ]
    g = portfolio_greeks(positions)
    g["delta"] = round(g["delta"] + 1.0, 4)

    return StrategyResult(
        name="保护性看跌 (Protective Put)",
        legs=[StrategyLeg("put", "buy", K_put, 1, put_price)],
        total_cost=net_cost,
        max_profit=round(max_profit, 2),
        max_loss=round(max_loss, 2),
        breakeven=breakeven,
        greeks=g,
        description=f"买入标的@{S:.2f} + 买入Put@{K_put}，保险成本{put_price:.2f}",
    )


def straddle(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
) -> StrategyResult:
    """
    跨式 (Long Straddle): 买入同价Call + Put。赌大波动。

    max_profit: 理论无上限 (call侧) 或 K - cost (put侧)
    max_loss: 净支出 (价格在K附近到期)
    """
    call_price = black_scholes_price(S, K, T, r, sigma, "call").price
    put_price = black_scholes_price(S, K, T, r, sigma, "put").price
    net_cost = call_price + put_price
    breakeven_up = K + net_cost
    breakeven_down = K - net_cost

    positions = [
        {"S": S, "K": K, "T": T, "r": r, "sigma": sigma, "option_type": "call", "quantity": 1},
        {"S": S, "K": K, "T": T, "r": r, "sigma": sigma, "option_type": "put", "quantity": 1},
    ]
    g = portfolio_greeks(positions)

    return StrategyResult(
        name="跨式 (Long Straddle)",
        legs=[
            StrategyLeg("call", "buy", K, 1, call_price),
            StrategyLeg("put", "buy", K, 1, put_price),
        ],
        total_cost=round(net_cost, 2),
        max_profit=float("inf"),
        max_loss=round(-net_cost, 2),
        breakeven=[breakeven_up, breakeven_down],
        greeks=g,
        description=f"买入Call@{K} + Put@{K}，净支出{net_cost:.2f}，赌大波动",
    )


def bull_spread(
    S: float,
    K_low: float,
    K_high: float,
    T: float,
    r: float,
    sigma: float,
    option_type: Literal["call", "put"] = "call",
) -> StrategyResult:
    """
    牛市价差 (Bull Spread):
    - Call: 买低K + 卖高K
    - Put: 买低K + 卖高K

    适用于温和看涨。
    """
    long_price = black_scholes_price(S, K_low, T, r, sigma, option_type).price
    short_price = black_scholes_price(S, K_high, T, r, sigma, option_type).price
    net_cost = long_price - short_price  # 通常为正
    max_profit = (K_high - K_low) - net_cost
    max_loss = -net_cost

    if option_type == "call":
        breakeven = [K_low + net_cost]
    else:
        breakeven = [K_high - net_cost]

    positions = [
        {"S": S, "K": K_low, "T": T, "r": r, "sigma": sigma, "option_type": option_type, "quantity": 1},
        {"S": S, "K": K_high, "T": T, "r": r, "sigma": sigma, "option_type": option_type, "quantity": -1},
    ]
    g = portfolio_greeks(positions)

    return StrategyResult(
        name=f"牛市{option_type.upper()}价差 (Bull {option_type.title()} Spread)",
        legs=[
            StrategyLeg(option_type, "buy", K_low, 1, long_price),
            StrategyLeg(option_type, "sell", K_high, 1, short_price),
        ],
        total_cost=round(net_cost, 2),
        max_profit=round(max_profit, 2),
        max_loss=round(max_loss, 2),
        breakeven=breakeven,
        greeks=g,
        description=f"买{option_type}@{K_low} + 卖{option_type}@{K_high}，温和看涨",
    )


def bear_spread(
    S: float,
    K_low: float,
    K_high: float,
    T: float,
    r: float,
    sigma: float,
    option_type: Literal["call", "put"] = "call",
) -> StrategyResult:
    """
    熊市价差 (Bear Spread):
    - Call: 卖低K + 买高K
    - Put: 卖低K + 买高K

    适用于温和看跌。
    """
    long_price = black_scholes_price(S, K_high, T, r, sigma, option_type).price
    short_price = black_scholes_price(S, K_low, T, r, sigma, option_type).price
    net_credit = short_price - long_price  # 通常为正
    max_profit = net_credit
    max_loss = -(K_high - K_low) + net_credit

    if option_type == "call":
        breakeven = [K_low + net_credit]
    else:
        breakeven = [K_high - net_credit]

    positions = [
        {"S": S, "K": K_low, "T": T, "r": r, "sigma": sigma, "option_type": option_type, "quantity": -1},
        {"S": S, "K": K_high, "T": T, "r": r, "sigma": sigma, "option_type": option_type, "quantity": 1},
    ]
    g = portfolio_greeks(positions)

    return StrategyResult(
        name=f"熊市{option_type.upper()}价差 (Bear {option_type.title()} Spread)",
        legs=[
            StrategyLeg(option_type, "sell", K_low, 1, short_price),
            StrategyLeg(option_type, "buy", K_high, 1, long_price),
        ],
        total_cost=round(-net_credit, 2),  # 负数表示净收入
        max_profit=round(max_profit, 2),
        max_loss=round(max_loss, 2),
        breakeven=breakeven,
        greeks=g,
        description=f"卖{option_type}@{K_low} + 买{option_type}@{K_high}，温和看跌",
    )


def iron_condor(
    S: float,
    K1: float,
    K2: float,
    K3: float,
    K4: float,
    T: float,
    r: float,
    sigma: float,
) -> StrategyResult:
    """
    铁秃鹰 (Iron Condor): 卖宽跨式 + 买宽跨式保护。
    K1 < K2 < S < K3 < K4

    适用于低波动率环境，价格在区间内震荡。
    """
    if not (K1 < K2 < S < K3 < K4):
        raise ValueError(f"要求 K1({K1}) < K2({K2}) < S({S}) < K3({K3}) < K4({K4})")

    # 卖 Put@K2, 买 Put@K1, 卖 Call@K3, 买 Call@K4
    sell_put = black_scholes_price(S, K2, T, r, sigma, "put").price
    buy_put = black_scholes_price(S, K1, T, r, sigma, "put").price
    sell_call = black_scholes_price(S, K3, T, r, sigma, "call").price
    buy_call = black_scholes_price(S, K4, T, r, sigma, "call").price

    net_credit = (sell_put - buy_put) + (sell_call - buy_call)
    spread_width_put = K2 - K1
    spread_width_call = K4 - K3
    max_loss = -min(spread_width_put, spread_width_call) + net_credit

    breakeven_up = K3 + net_credit
    breakeven_down = K2 - net_credit

    positions = [
        {"S": S, "K": K2, "T": T, "r": r, "sigma": sigma, "option_type": "put", "quantity": -1},
        {"S": S, "K": K1, "T": T, "r": r, "sigma": sigma, "option_type": "put", "quantity": 1},
        {"S": S, "K": K3, "T": T, "r": r, "sigma": sigma, "option_type": "call", "quantity": -1},
        {"S": S, "K": K4, "T": T, "r": r, "sigma": sigma, "option_type": "call", "quantity": 1},
    ]
    g = portfolio_greeks(positions)

    return StrategyResult(
        name="铁秃鹰 (Iron Condor)",
        legs=[
            StrategyLeg("put", "sell", K2, 1, sell_put),
            StrategyLeg("put", "buy", K1, 1, buy_put),
            StrategyLeg("call", "sell", K3, 1, sell_call),
            StrategyLeg("call", "buy", K4, 1, buy_call),
        ],
        total_cost=round(-net_credit, 2),
        max_profit=round(net_credit, 2),
        max_loss=round(max_loss, 2),
        breakeven=[breakeven_down, breakeven_up],
        greeks=g,
        description=(
            f"卖Put@{K2}+买Put@{K1}+卖Call@{K3}+买Call@{K4}，净收入{net_credit:.2f}，价格在[{K2},{K3}]区间获利"
        ),
    )
