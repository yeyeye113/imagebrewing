"""VaR 风险价值模块 — 计算在险价值.

方法:
  1. 历史模拟法
  2. 参数法 (正态分布)
  3. 蒙特卡洛模拟法
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .log import get_logger

logger = get_logger("var")


@dataclass
class VaRResult:
    """VaR 计算结果."""
    method: str              # 计算方法
    confidence_level: float  # 置信水平
    var_1d: float            # 1 日 VaR
    var_1w: float            # 1 周 VaR
    var_1m: float            # 1 月 VaR
    cvar_1d: float           # 1 日 CVaR (条件 VaR)
    max_loss_1d: float       # 1 日最大亏损
    volatility: float        # 波动率
    skewness: float          # 偏度
    kurtosis: float          # 峰度


def calculate_historical_var(
    returns: pd.Series,
    confidence_level: float = 0.95,
    holding_period: int = 1,
) -> float:
    """历史模拟法计算 VaR.

    Args:
        returns: 收益率序列
        confidence_level: 置信水平
        holding_period: 持有期 (天)

    Returns:
        float: VaR 值
    """
    if returns is None or len(returns) < 30:
        return 0.0

    # 排序收益率
    sorted_returns = returns.sort_values()

    # 计算分位数
    index = int(len(sorted_returns) * (1 - confidence_level))
    var = abs(float(sorted_returns.iloc[index]))

    # 调整持有期
    var = var * np.sqrt(holding_period)

    return float(var)


def calculate_parametric_var(
    returns: pd.Series,
    confidence_level: float = 0.95,
    holding_period: int = 1,
) -> float:
    """参数法计算 VaR (假设正态分布).

    Args:
        returns: 收益率序列
        confidence_level: 置信水平
        holding_period: 持有期 (天)

    Returns:
        float: VaR 值
    """
    if returns is None or len(returns) < 30:
        return 0.0

    from scipy import stats

    # 计算均值和标准差
    mu = returns.mean()
    sigma = returns.std()

    # 计算分位数
    z = stats.norm.ppf(1 - confidence_level)
    var = abs(mu + z * sigma)

    # 调整持有期
    var = var * np.sqrt(holding_period)

    return float(var)


def calculate_monte_carlo_var(
    returns: pd.Series,
    confidence_level: float = 0.95,
    holding_period: int = 1,
    simulations: int = 10000,
) -> float:
    """蒙特卡洛模拟法计算 VaR.

    Args:
        returns: 收益率序列
        confidence_level: 置信水平
        holding_period: 持有期 (天)
        simulations: 模拟次数

    Returns:
        float: VaR 值
    """
    if returns is None or len(returns) < 30:
        return 0.0

    # 计算均值和标准差
    mu = returns.mean()
    sigma = returns.std()

    # 蒙特卡洛模拟
    np.random.seed(42)
    simulated_returns = np.random.normal(mu, sigma, (simulations, holding_period))

    # 计算持有期累计收益
    cumulative_returns = np.prod(1 + simulated_returns, axis=1) - 1

    # 计算分位数
    index = int(simulations * (1 - confidence_level))
    sorted_returns = np.sort(cumulative_returns)
    var = abs(sorted_returns[index])

    return float(var)


def calculate_cvar(
    returns: pd.Series,
    confidence_level: float = 0.95,
    holding_period: int = 1,
) -> float:
    """计算条件 VaR (CVaR).

    Args:
        returns: 收益率序列
        confidence_level: 置信水平
        holding_period: 持有期 (天)

    Returns:
        float: CVaR 值
    """
    if returns is None or len(returns) < 30:
        return 0.0

    # 排序收益率
    sorted_returns = returns.sort_values()

    # 计算分位数
    index = int(len(sorted_returns) * (1 - confidence_level))

    # CVaR = 尾部平均值
    tail_returns = sorted_returns.iloc[:index]
    cvar = abs(tail_returns.mean())

    # 调整持有期
    cvar = cvar * np.sqrt(holding_period)

    return float(cvar)


def calculate_var(
    prices: pd.DataFrame,
    confidence_level: float = 0.95,
    method: str = "historical",
) -> VaRResult:
    """计算 VaR.

    Args:
        prices: OHLCV 数据
        confidence_level: 置信水平
        method: 计算方法 ("historical" | "parametric" | "monte_carlo")

    Returns:
        VaRResult: VaR 计算结果
    """
    if prices is None or len(prices) < 30:
        return VaRResult(
            method=method,
            confidence_level=confidence_level,
            var_1d=0,
            var_1w=0,
            var_1m=0,
            cvar_1d=0,
            max_loss_1d=0,
            volatility=0,
            skewness=0,
            kurtosis=0,
        )

    # 计算收益率
    returns = prices['close'].pct_change().dropna()

    if len(returns) < 30:
        return VaRResult(
            method=method,
            confidence_level=confidence_level,
            var_1d=0,
            var_1w=0,
            var_1m=0,
            cvar_1d=0,
            max_loss_1d=0,
            volatility=0,
            skewness=0,
            kurtosis=0,
        )

    # 根据方法计算 VaR
    if method == "historical":
        var_1d = calculate_historical_var(returns, confidence_level, 1)
        var_1w = calculate_historical_var(returns, confidence_level, 5)
        var_1m = calculate_historical_var(returns, confidence_level, 20)
    elif method == "parametric":
        var_1d = calculate_parametric_var(returns, confidence_level, 1)
        var_1w = calculate_parametric_var(returns, confidence_level, 5)
        var_1m = calculate_parametric_var(returns, confidence_level, 20)
    elif method == "monte_carlo":
        var_1d = calculate_monte_carlo_var(returns, confidence_level, 1)
        var_1w = calculate_monte_carlo_var(returns, confidence_level, 5)
        var_1m = calculate_monte_carlo_var(returns, confidence_level, 20)
    else:
        var_1d = calculate_historical_var(returns, confidence_level, 1)
        var_1w = calculate_historical_var(returns, confidence_level, 5)
        var_1m = calculate_historical_var(returns, confidence_level, 20)

    # 计算 CVaR
    cvar_1d = calculate_cvar(returns, confidence_level, 1)

    # 计算最大亏损
    max_loss_1d = abs(float(returns.min()))

    # 计算统计指标
    volatility = float(returns.std())
    skewness = float(returns.skew())
    kurtosis = float(returns.kurtosis())

    return VaRResult(
        method=method,
        confidence_level=confidence_level,
        var_1d=round(var_1d, 4),
        var_1w=round(var_1w, 4),
        var_1m=round(var_1m, 4),
        cvar_1d=round(cvar_1d, 4),
        max_loss_1d=round(max_loss_1d, 4),
        volatility=round(volatility, 4),
        skewness=round(skewness, 4),
        kurtosis=round(kurtosis, 4),
    )


def get_var_signal(prices: pd.DataFrame) -> dict:
    """获取 VaR 风险信号.

    Returns:
        dict: {
            "risk_level": str,       # "low" | "medium" | "high"
            "var_1d": float,
            "var_1w": float,
            "cvar_1d": float,
            "volatility": float,
            "reason": str,
        }
    """
    var_result = calculate_var(prices, confidence_level=0.95, method="historical")

    # 判断风险等级
    if var_result.var_1d < 0.02:
        risk_level = "low"
        reason = f"低风险 VaR={var_result.var_1d*100:.1f}%"
    elif var_result.var_1d < 0.05:
        risk_level = "medium"
        reason = f"中等风险 VaR={var_result.var_1d*100:.1f}%"
    else:
        risk_level = "high"
        reason = f"高风险 VaR={var_result.var_1d*100:.1f}%"

    return {
        "risk_level": risk_level,
        "var_1d": var_result.var_1d,
        "var_1w": var_result.var_1w,
        "cvar_1d": var_result.cvar_1d,
        "volatility": var_result.volatility,
        "reason": reason,
    }
