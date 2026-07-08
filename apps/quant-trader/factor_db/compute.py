"""因子计算引擎 — 从价格数据计算各类因子并入库。

内置因子:
    momentum_Nd    — N 日动量 (收益率)
    mean_rev_Nd    — N 日均值回归 (价格 / MA - 1)
    volatility_Nd  — N 日波动率 (年化)
    rsi_Nd         — N 日 RSI
    vol_ratio_Nd   — N 日成交量比 (当日成交量 / MA(volume))
    turnover_Nd    — N 日换手率代理 (累计收益 / 波动率)
    skewness_Nd    — N 日收益偏度
    kurtosis_Nd    — N 日收益峰度

Usage::

    from quanttrader.factor_db.compute import compute_factors, FACTOR_REGISTRY

    # 一次性计算所有内置因子并入库
    compute_factors(prices_df, symbols=["AAPL", "GOOGL"], db=my_db)

    # 只算部分因子
    compute_factors(prices_df, symbols=["AAPL"], db=my_db,
                    factors=["momentum_20d", "rsi_14d"])
"""

from __future__ import annotations

import json
from collections.abc import Callable

import numpy as np
import pandas as pd

from .storage import FactorDB

# ── 因子注册表 ─────────────────────────────────────────────────

FACTOR_REGISTRY: dict[str, Callable] = {}


def _register(name: str):
    """装饰器：注册因子计算函数。函数签名: (close, volume, params) -> Series"""

    def decorator(fn):
        FACTOR_REGISTRY[name] = fn
        return fn

    return decorator


# ── 内置因子 ──────────────────────────────────────────────────


@_register("momentum_{window}d")
def _momentum(close: pd.Series, _vol: pd.Series, window: int) -> pd.Series:
    """N 日动量 = 过去 N 日收益率。"""
    return close.pct_change(window)


@_register("mean_rev_{window}d")
def _mean_rev(close: pd.Series, _vol: pd.Series, window: int) -> pd.Series:
    """N 日均值回归 = price / MA - 1。正值表示价格高于均线（可能回归）。"""
    ma = close.rolling(window).mean()
    return close / ma - 1


@_register("volatility_{window}d")
def _volatility(close: pd.Series, _vol: pd.Series, window: int) -> pd.Series:
    """N 日年化波动率。"""
    ret = close.pct_change()
    return ret.rolling(window).std() * np.sqrt(252)


@_register("rsi_{window}d")
def _rsi(close: pd.Series, _vol: pd.Series, window: int) -> pd.Series:
    """N 日 RSI (0-100)。"""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(span=window, min_periods=window).mean()
    avg_loss = loss.ewm(span=window, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


@_register("vol_ratio_{window}d")
def _vol_ratio(_close: pd.Series, volume: pd.Series, window: int) -> pd.Series:
    """N 日成交量比 = 当日成交量 / N日均量。"""
    if volume is None or volume.empty:
        return pd.Series(np.nan, index=_close.index)
    ma_vol = volume.rolling(window).mean()
    return volume / ma_vol.replace(0, np.nan)


@_register("skewness_{window}d")
def _skewness(close: pd.Series, _vol: pd.Series, window: int) -> pd.Series:
    """N 日收益偏度。"""
    ret = close.pct_change()
    return ret.rolling(window).skew()


@_register("kurtosis_{window}d")
def _kurtosis(close: pd.Series, _vol: pd.Series, window: int) -> pd.Series:
    """N 日收益峰度。"""
    ret = close.pct_change()
    return ret.rolling(window).kurt()


# ── 核心 API ──────────────────────────────────────────────────


def _expand_name(template: str, window: int) -> str:
    return template.replace("{window}", str(window))


def _params_dict(window: int) -> str:
    return json.dumps({"window": window})


DEFAULT_WINDOWS = [5, 10, 20, 60]


def compute_factors(
    prices: pd.DataFrame,
    symbols: list[str] | None = None,
    db: FactorDB | None = None,
    factors: list[str] | None = None,
    windows: list[int] | None = None,
    compute_returns: bool = True,
) -> dict[str, int]:
    """计算因子并写入数据库。

    Args:
        prices: MultiIndex columns (symbol, field) 或 wide-format，
                至少需含 close 列。支持两种格式:
                1. columns = MultiIndex [(symbol, 'close'), (symbol, 'volume'), ...]
                2. columns = ['close'] 单标的
        symbols: 要计算的标的列表 (None=全部)
        db: FactorDB 实例 (None=使用默认路径)
        factors: 要计算的因子模板名 (None=全部)
        windows: 窗口列表 (None=[5,10,20,60])
        compute_returns: 是否同时计算未来收益

    Returns:
        {expanded_factor_name: factor_id}
    """
    if db is None:
        db = FactorDB()
    if windows is None:
        windows = DEFAULT_WINDOWS

    # 解析 prices 为 {(symbol, field): Series} 形式
    data = _parse_prices(prices)
    all_symbols = symbols or sorted({s for s, _ in data.keys()})

    factor_ids: dict[str, int] = {}

    # 选择要计算的因子模板
    templates = factors if factors else list(FACTOR_REGISTRY.keys())

    for tmpl in templates:
        fn = FACTOR_REGISTRY.get(tmpl)
        if fn is None:
            continue
        for w in windows:
            expanded = _expand_name(tmpl, w)
            fid = db.upsert_factor(
                expanded,
                _params_dict(w),
                f"{tmpl} with window={w}",
            )
            frames = []
            for sym in all_symbols:
                close = data.get((sym, "close"))
                vol = data.get((sym, "volume"))
                if close is None:
                    continue
                vals = fn(close, vol, w)
                if vals.dropna().empty:
                    continue
                sub = pd.DataFrame(
                    {
                        "symbol": sym,
                        "date": vals.index,
                        "value": vals.values,
                    }
                ).dropna(subset=["value"])
                if not sub.empty:
                    frames.append(sub)

            if frames:
                combined = pd.concat(frames, ignore_index=True)
                db.write_factor_values(fid, combined)
            factor_ids[expanded] = fid

    # 计算未来收益
    if compute_returns:
        _compute_returns(data, all_symbols, db)

    return factor_ids


def _compute_returns(data: dict, symbols: list[str], db: FactorDB) -> None:
    """从 close 价格计算未来 1/5/10/20 日收益率并入库。"""
    horizons = {"ret_1d": 1, "ret_5d": 5, "ret_10d": 10, "ret_20d": 20}
    frames = []
    for sym in symbols:
        close = data.get((sym, "close"))
        if close is None:
            continue
        ret_df = pd.DataFrame({"symbol": sym, "date": close.index})
        for col, h in horizons.items():
            ret_df[col] = close.pct_change(h).shift(-h).values
        frames.append(ret_df)
    if frames:
        combined = pd.concat(frames, ignore_index=True)
        db.write_returns(combined)


def _parse_prices(
    prices: pd.DataFrame,
) -> dict[tuple[str, str], pd.Series]:
    """将 prices DataFrame 解析为 {(symbol, field): Series}。

    支持:
        1. MultiIndex columns: (symbol, 'close')
        2. 单标的 flat columns: 'close', 'volume'
    """
    data: dict[tuple[str, str], pd.Series] = {}

    if isinstance(prices.columns, pd.MultiIndex):
        for col in prices.columns:
            sym, field = col[0], col[1]
            data[(sym, field)] = prices[col]
    else:
        # 单标的模式 — 用 "__default__" 作 symbol
        sym = "__default__"
        for field in ["close", "volume", "open", "high", "low"]:
            if field in prices.columns:
                data[(sym, field)] = prices[field]

    return data
