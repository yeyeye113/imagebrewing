"""波动率计算 — 隐含波动率、历史波动率、波动率曲面。"""

import math
from typing import Literal

import numpy as np
from scipy.optimize import brentq

from quanttrader.options.pricing import black_scholes_price


def implied_volatility(
    market_price: float,
    S: float,
    K: float,
    T: float,
    r: float,
    option_type: Literal["call", "put"] = "call",
    tol: float = 1e-8,
    max_iter: int = 100,
) -> float:
    """
    用 Brent 法求解隐含波动率。

    参数:
        market_price: 市场期权价格
        S, K, T, r: 同 Black-Scholes
        option_type: 'call' 或 'put'

    返回:
        隐含波动率 sigma

    示例:
        >>> iv = implied_volatility(market_price=5.3, S=100, K=105, T=30/365, r=0.03)
        >>> print(f"IV: {iv:.2%}")
    """
    if market_price <= 0:
        raise ValueError("市场价格必须为正数")

    def _objective(sigma: float) -> float:
        try:
            p = black_scholes_price(S, K, T, r, sigma, option_type).price
            return p - market_price
        except (ValueError, ZeroDivisionError):
            return float("inf")

    # 检查上下界是否异号
    try:
        lo = _objective(1e-6)
        hi = _objective(5.0)
    except Exception:
        raise ValueError("无法求解隐含波动率，价格可能超出合理范围")

    if lo * hi > 0:
        # 不异号，尝试更宽范围
        try:
            hi = _objective(10.0)
        except Exception:
            pass
        if lo * hi > 0:
            raise ValueError(f"无法求解隐含波动率: 市场价{market_price}可能不合理 (lo={lo:.4f}, hi={hi:.4f})")

    return float(brentq(_objective, 1e-6, 5.0, xtol=tol, maxiter=max_iter))


def implied_volatility_surface(
    S: float,
    strikes: list[float],
    expiries: list[float],
    r: float,
    market_prices: np.ndarray,
    option_type: Literal["call", "put"] = "call",
) -> dict:
    """
    构建隐含波动率曲面。

    参数:
        S: 当前标的价格
        strikes: 行权价列表
        expiries: 到期时间列表(年)
        r: 无风险利率
        market_prices: 2D数组, shape=(len(strikes), len(expiries))
        option_type: 'call' 或 'put'

    返回:
        dict: {
            'strikes': [...],
            'expiries': [...],
            'iv_surface': 2D np.ndarray,
            'iv_matrix': {strike: {expiry: iv}}
        }
    """
    n_strikes = len(strikes)
    n_expiries = len(expiries)

    if market_prices.shape != (n_strikes, n_expiries):
        raise ValueError(f"market_prices shape {market_prices.shape} 不匹配 ({n_strikes}, {n_expiries})")

    iv_surface = np.full((n_strikes, n_expiries), np.nan)
    iv_matrix: dict[float, dict[float, float | None]] = {}

    for i, K in enumerate(strikes):
        iv_matrix[K] = {}
        for j, T in enumerate(expiries):
            try:
                iv = implied_volatility(market_prices[i, j], S, K, T, r, option_type)
                iv_surface[i, j] = iv
                iv_matrix[K][T] = round(iv, 4)
            except (ValueError, RuntimeError):
                iv_surface[i, j] = np.nan
                iv_matrix[K][T] = None

    return {
        "strikes": strikes,
        "expiries": expiries,
        "iv_surface": iv_surface,
        "iv_matrix": iv_matrix,
    }


def historical_volatility(
    prices: np.ndarray,
    window: int = 20,
    annualize: bool = True,
    trading_days: int = 252,
) -> np.ndarray:
    """
    计算历史波动率（滚动窗口）。

    参数:
        prices: 价格序列 (如收盘价)
        window: 滚动窗口大小
        annualize: True=年化
        trading_days: 年交易日数

    返回:
        波动率序列 (长度 = len(prices) - window + 1)
    """
    if len(prices) < window + 1:
        raise ValueError(f"价格序列长度({len(prices)})不足，需要至少{window + 1}")

    log_returns = np.diff(np.log(prices))
    rolling_std = np.array([np.std(log_returns[i - window : i]) for i in range(window, len(log_returns) + 1)])

    if annualize:
        rolling_std *= math.sqrt(trading_days)

    return rolling_std


def parkinson_volatility(
    highs: np.ndarray,
    lows: np.ndarray,
    window: int = 20,
    annualize: bool = True,
    trading_days: int = 252,
) -> np.ndarray:
    """
    Parkinson 波动率估计（用最高/最低价，更高效）。

    公式: sigma = sqrt(1/(4*N*ln2) * sum(ln(H/L)^2))
    """
    if len(highs) != len(lows):
        raise ValueError("highs 和 lows 长度必须一致")
    if len(highs) < window:
        raise ValueError(f"数据长度不足，需要至少{window}")

    log_hl = np.log(highs / lows) ** 2

    rolling_var = np.array([np.mean(log_hl[i - window : i]) for i in range(window, len(log_hl) + 1)])

    vol = np.sqrt(rolling_var / (4 * math.log(2)))

    if annualize:
        vol *= math.sqrt(trading_days)

    return vol


def garman_klass_volatility(
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    window: int = 20,
    annualize: bool = True,
    trading_days: int = 252,
) -> np.ndarray:
    """
    Garman-Klass 波动率估计（用OHLC数据，效率最高）。

    比 close-to-close 更精确，数据利用率高 5-6 倍。
    """
    if not all(len(arr) == len(opens) for arr in [highs, lows, closes]):
        raise ValueError("所有价格数组长度必须一致")
    if len(opens) < window:
        raise ValueError(f"数据长度不足，需要至少{window}")

    gk = 0.5 * np.log(highs / lows) ** 2 - (2 * math.log(2) - 1) * np.log(closes / opens) ** 2

    rolling_var = np.array([np.mean(gk[i - window : i]) for i in range(window, len(gk) + 1)])

    vol = np.sqrt(np.maximum(rolling_var, 0))

    if annualize:
        vol *= math.sqrt(trading_days)

    return np.asarray(vol)
