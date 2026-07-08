"""希腊字母（Greeks）计算 — Delta, Gamma, Vega, Theta, Rho。"""

import math
from dataclasses import dataclass
from typing import Literal

from scipy.stats import norm


@dataclass(frozen=True)
class Greeks:
    """期权希腊字母。"""

    delta: float
    gamma: float
    vega: float  # per 1% vol move
    theta: float  # per day
    rho: float  # per 1% rate move
    option_type: str
    S: float
    K: float
    T: float
    r: float
    sigma: float


def compute_greeks(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: Literal["call", "put"] = "call",
) -> Greeks:
    """
    计算 Black-Scholes 希腊字母。

    参数:
        S: 标的价格
        K: 行权价
        T: 到期时间(年)
        r: 无风险利率
        sigma: 年化波动率
        option_type: 'call' 或 'put'

    返回:
        Greeks dataclass

    单位说明:
        - Delta: 价格变动1单位，期权价格变动
        - Gamma: 标的价格变动1单位，Delta变动
        - Vega: 波动率变动1%(如25%→26%)，期权价格变动
        - Theta: 每天的时间价值衰减
        - Rho: 利率变动1%，期权价格变动
    """
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        raise ValueError("S, K, T, sigma 必须为正数")

    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    sqrt_T = math.sqrt(T)
    exp_rT = math.exp(-r * T)
    pdf_d1 = norm.pdf(d1)
    cdf_d1 = norm.cdf(d1)
    cdf_d2 = norm.cdf(d2)

    # Gamma (call = put)
    gamma = pdf_d1 / (S * sigma * sqrt_T)

    # Vega (call = put), 除以100得到 per 1% vol
    vega = S * pdf_d1 * sqrt_T / 100.0

    if option_type == "call":
        delta = cdf_d1
        theta = (-(S * pdf_d1 * sigma) / (2 * sqrt_T) - r * K * exp_rT * cdf_d2) / 365.0
        rho = K * T * exp_rT * cdf_d2 / 100.0
    elif option_type == "put":
        delta = cdf_d1 - 1
        theta = (-(S * pdf_d1 * sigma) / (2 * sqrt_T) + r * K * exp_rT * norm.cdf(-d2)) / 365.0
        rho = -K * T * exp_rT * norm.cdf(-d2) / 100.0
    else:
        raise ValueError(f"未知期权类型: {option_type}")

    return Greeks(
        delta=delta,
        gamma=gamma,
        vega=vega,
        theta=theta,
        rho=rho,
        option_type=option_type,
        S=S,
        K=K,
        T=T,
        r=r,
        sigma=sigma,
    )


def greeks_table(
    S: float,
    strikes: list[float],
    T: float,
    r: float,
    sigma: float,
    option_type: Literal["call", "put"] = "call",
) -> list[dict]:
    """
    生成多行权价的希腊字母表格（便于查看风险敞口）。

    返回: list of dict, 每个 dict 包含 strike 和各 Greeks
    """
    rows = []
    for K in strikes:
        g = compute_greeks(S, K, T, r, sigma, option_type)
        rows.append(
            {
                "strike": K,
                "delta": round(g.delta, 4),
                "gamma": round(g.gamma, 4),
                "vega": round(g.vega, 4),
                "theta": round(g.theta, 4),
                "rho": round(g.rho, 4),
            }
        )
    return rows


def portfolio_greeks(positions: list[dict]) -> dict:
    """
    计算组合希腊字母。

    参数:
        positions: list of dict, 每个 dict 包含:
            - S, K, T, r, sigma
            - option_type: 'call' or 'put'
            - quantity: 合约数量 (正=多头, 负=空头)

    示例:
        >>> portfolio_greeks([
        ...     {"S": 100, "K": 105, "T": 30/365, "r": 0.03, "sigma": 0.25, "option_type": "call", "quantity": 1},
        ...     {"S": 100, "K": 95, "T": 30/365, "r": 0.03, "sigma": 0.25, "option_type": "put", "quantity": -1},
        ... ])
    """
    totals = {"delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0, "rho": 0.0}

    for pos in positions:
        qty = pos.get("quantity", 1)
        g = compute_greeks(
            pos["S"],
            pos["K"],
            pos["T"],
            pos["r"],
            pos["sigma"],
            pos.get("option_type", "call"),
        )
        totals["delta"] += g.delta * qty
        totals["gamma"] += g.gamma * qty
        totals["vega"] += g.vega * qty
        totals["theta"] += g.theta * qty
        totals["rho"] += g.rho * qty

    return {k: round(v, 6) for k, v in totals.items()}
