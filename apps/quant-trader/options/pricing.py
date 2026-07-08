"""Black-Scholes 期权定价模型。"""

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
from scipy.stats import norm


@dataclass(frozen=True)
class OptionPrice:
    """定价结果。"""

    price: float
    option_type: str  # 'call' or 'put'
    S: float  # 标的价格
    K: float  # 行权价
    T: float  # 到期时间(年)
    r: float  # 无风险利率
    sigma: float  # 波动率
    d1: float
    d2: float


def _d1(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """计算 d1。"""
    return (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))


def _d2(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """计算 d2。"""
    return _d1(S, K, T, r, sigma) - sigma * math.sqrt(T)


def black_scholes_price(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: Literal["call", "put"] = "call",
) -> OptionPrice:
    """
    Black-Scholes 期权定价。

    参数:
        S: 标的资产价格
        K: 行权价格
        T: 到期时间(年), e.g. 30天 = 30/365
        r: 无风险利率, e.g. 0.03
        sigma: 年化波动率, e.g. 0.25
        option_type: 'call' or 'put'

    返回:
        OptionPrice dataclass

    示例:
        >>> p = black_scholes_price(S=100, K=105, T=30/365, r=0.03, sigma=0.25, option_type='call')
        >>> print(f"Call Price: {p.price:.4f}")
    """
    if T <= 0:
        raise ValueError("到期时间 T 必须为正数")
    if sigma <= 0:
        raise ValueError("波动率 sigma 必须为正数")
    if S <= 0 or K <= 0:
        raise ValueError("标的价格和行权价必须为正数")

    d1 = _d1(S, K, T, r, sigma)
    d2 = _d2(S, K, T, r, sigma)

    if option_type == "call":
        price = S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    elif option_type == "put":
        price = K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    else:
        raise ValueError(f"未知期权类型: {option_type}, 仅支持 'call' 或 'put'")

    return OptionPrice(
        price=price,
        option_type=option_type,
        S=S,
        K=K,
        T=T,
        r=r,
        sigma=sigma,
        d1=d1,
        d2=d2,
    )


def black_scholes_vectorized(
    S: np.ndarray,
    K: np.ndarray,
    T: np.ndarray,
    r: float,
    sigma: np.ndarray,
    option_type: Literal["call", "put"] = "call",
) -> np.ndarray:
    """
    向量化 Black-Scholes 定价（用于批量计算）。

    参数: 与 black_scholes_price 相同，但 S/K/T/sigma 为等长数组。
    返回: 价格数组
    """
    if any(len(arr) != len(S) for arr in [K, T, sigma]):
        raise ValueError("S, K, T, sigma 数组长度必须一致")

    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)

    if option_type == "call":
        return np.asarray(S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2))
    else:
        return np.asarray(K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1))


def binomial_tree_price(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    N: int = 100,
    option_type: Literal["call", "put"] = "call",
    american: bool = False,
) -> float:
    """
    二叉树定价（支持美式期权）。

    参数:
        N: 步数，越大越精确
        american: True=美式期权
    """
    dt = T / N
    u = math.exp(sigma * math.sqrt(dt))
    d = 1 / u
    p = (math.exp(r * dt) - d) / (u - d)

    # 终端价格
    ST = S * u ** np.arange(N, -1, -1) * d ** np.arange(0, N + 1)

    if option_type == "call":
        values = np.maximum(ST - K, 0)
    else:
        values = np.maximum(K - ST, 0)

    # 回溯
    for i in range(N - 1, -1, -1):
        values = math.exp(-r * dt) * (p * values[:-1] + (1 - p) * values[1:])
        if american:
            Si = S * u ** np.arange(i, -1, -1) * d ** np.arange(0, i + 1)
            if option_type == "call":
                exercise = np.maximum(Si - K, 0)
            else:
                exercise = np.maximum(K - Si, 0)
            values = np.maximum(values, exercise)

    return float(values[0])
