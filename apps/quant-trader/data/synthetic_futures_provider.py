"""合成数据提供器 — 仅用于单元测试。

⚠️ 合成数据禁止用于训练、回测、OOS、paper。
仅允许用于:
  - 单元测试
  - 模块功能验证
  - 集成测试

所有返回的 DataFrame 都包含 source_type=synthetic 标记。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from datetime import datetime


def get_synthetic_history(code: str, days: int = 60, seed: int | None = None) -> pd.DataFrame:
    """获取合成历史数据 (仅用于测试)。

    ⚠️ 返回的 DataFrame 包含 source_type=synthetic 标记。
    任何训练/回测/paper 流程发现此标记必须 BLOCK。

    Args:
        code: 品种代码
        days: 天数
        seed: 随机种子 (None=基于代码生成)

    Returns:
        DataFrame with source_type='synthetic' 标记
    """
    if seed is None:
        seed = int(abs(hash(code)) % (2**31))

    rng = np.random.RandomState(seed)

    base_prices = {
        "I": 824, "RB": 3544, "SC": 612, "AU": 575, "AG": 8159,
        "HC": 3731, "FU": 3492, "CU": 79280, "M": 3200, "A": 4500,
        "NI": 130000, "SI": 12000, "BU": 3600, "AL": 19000, "ZN": 22000,
    }
    base = base_prices.get(code.upper(), 3000)

    mu = 0.0002
    sigma = 0.02
    returns = rng.normal(mu, sigma, days)
    cumulative = np.cumsum(returns[::-1])
    prices = base * np.exp(-cumulative[::-1])
    prices = np.append(prices, base)

    highs = prices * (1 + np.abs(rng.randn(len(prices)) * 0.008))
    lows = prices * (1 - np.abs(rng.randn(len(prices)) * 0.008))
    opens = prices * (1 + rng.randn(len(prices)) * 0.003)
    volumes = rng.randint(50000, 300000, len(prices))

    for i in range(len(prices)):
        highs[i] = max(highs[i], opens[i], prices[i])
        lows[i] = min(lows[i], opens[i], prices[i])

    dates = pd.date_range(end=datetime.now(), periods=len(prices), freq="D")

    df = pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": prices,
        "volume": volumes,
    }, index=dates)

    # 标记为合成数据
    df.attrs["source_type"] = "synthetic"
    df.attrs["is_synthetic"] = True
    df.attrs["allowed_for_training"] = False
    df.attrs["allowed_for_backtest"] = False
    df.attrs["allowed_for_paper"] = False
    df.attrs["source_name"] = "sina_futures_synthetic"
    df.attrs["code"] = code

    return df


def is_synthetic(df: pd.DataFrame | None) -> bool:
    """检查 DataFrame 是否为合成数据。"""
    if df is None:
        return False
    return df.attrs.get("is_synthetic", False) or df.attrs.get("source_type") == "synthetic"


def assert_not_synthetic(df: pd.DataFrame | None, context: str = "") -> None:
    """断言数据不是合成数据。如果是合成数据，抛出 RuntimeError。"""
    if is_synthetic(df):
        raise RuntimeError(
            f"合成数据 BLOCKED{': ' + context if context else ''}。"
            f"合成数据禁止用于训练/回测/paper。"
            f"请使用 akshare 真实数据: ak.futures_main_sina(symbol=code)"
        )
