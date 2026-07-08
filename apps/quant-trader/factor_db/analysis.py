"""因子分析层 — IC 分析、分组回测、因子衰减。

功能:
    ic_analysis         — 因子 IC/IR 时间序列 + 统计摘要
    group_backtest      — 按因子值分组，计算各组未来收益
    factor_decay        — 因子自相关 / 衰减分析
    factor_correlation  — 多因子相关性矩阵
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .query import FactorQuery
from .storage import FactorDB


def ic_analysis(
    db: FactorDB | None = None,
    factor: str = "momentum_20d",
    horizon: int = 5,
    ret_col: str | None = None,
    method: str = "rank",
    min_coverage: float = 0.5,
) -> pd.DataFrame:
    """因子 IC (Information Coefficient) 分析。

    Args:
        db: FactorDB 实例
        factor: 因子名
        horizon: 未来收益天数 (1/5/10/20)
        ret_col: 收益列名 (None=自动选 ret_{horizon}d)
        method: "rank" (Spearman) 或 "normal" (Pearson)
        min_coverage: 最低截面覆盖率 (低于此日跳过)

    Returns:
        DataFrame 含 columns: [date, ic, n_stocks]
        + 附加属性: ic_mean, ic_std, ir, ic_positive_pct, ic_abs_gt_003_pct
    """
    if db is None:
        db = FactorDB()
    q = FactorQuery(db)

    # 获取因子值 (long format)
    factor_df = q.get_factor_long(factor)
    if factor_df.empty:
        return pd.DataFrame()

    # 获取收益
    ret_col = ret_col or f"ret_{horizon}d"
    returns_df = q.get_returns()
    if returns_df.empty:
        return pd.DataFrame()

    returns_df["date"] = pd.to_datetime(returns_df["date"])
    factor_df["date"] = pd.to_datetime(factor_df["date"])

    # 按日期计算截面 IC
    dates = sorted(factor_df["date"].unique())
    results = []

    for dt in dates:
        f_day = factor_df[factor_df["date"] == dt][["symbol", "value"]].dropna()
        r_day = returns_df[returns_df["date"] == dt][["symbol", ret_col]].dropna()
        merged = f_day.merge(r_day, on="symbol", how="inner")

        n = len(merged)
        if n < 5 or n / max(len(f_day), 1) < min_coverage:
            continue

        if method == "rank":
            ic = merged["value"].rank().corr(merged[ret_col].rank())
        else:
            ic = merged["value"].corr(merged[ret_col])

        if pd.notna(ic):
            results.append({"date": dt, "ic": ic, "n_stocks": n})

    if not results:
        return pd.DataFrame()

    ic_df = pd.DataFrame(results).set_index("date")

    # 附加统计
    ic_series = ic_df["ic"]
    ic_df.attrs["ic_mean"] = ic_series.mean()
    ic_df.attrs["ic_std"] = ic_series.std()
    ic_df.attrs["ir"] = ic_series.mean() / ic_series.std() if ic_series.std() > 0 else 0
    ic_df.attrs["ic_positive_pct"] = (ic_series > 0).mean()
    ic_df.attrs["ic_abs_gt_003_pct"] = (ic_series.abs() > 0.03).mean()
    ic_df.attrs["n_days"] = len(ic_series)

    return ic_df


def group_backtest(
    db: FactorDB | None = None,
    factor: str = "momentum_20d",
    horizon: int = 5,
    n_groups: int = 5,
    ret_col: str | None = None,
) -> pd.DataFrame:
    """分组回测 — 按因子值分 N 组，计算各组平均未来收益。

    Args:
        db: FactorDB 实例
        factor: 因子名
        horizon: 未来收益天数
        n_groups: 分组数 (默认5=五分位)
        ret_col: 收益列名

    Returns:
        DataFrame, index=group (1=bottom, N=top),
        columns: [mean_ret, cum_ret, sharpe, win_rate]
    """
    if db is None:
        db = FactorDB()
    q = FactorQuery(db)

    factor_df = q.get_factor_long(factor)
    if factor_df.empty:
        return pd.DataFrame()

    ret_col = ret_col or f"ret_{horizon}d"
    returns_df = q.get_returns()
    if returns_df.empty:
        return pd.DataFrame()

    returns_df["date"] = pd.to_datetime(returns_df["date"])
    factor_df["date"] = pd.to_datetime(factor_df["date"])

    # 按日期分组
    dates = sorted(factor_df["date"].unique())
    group_returns: dict[int, list[float]] = {g: [] for g in range(1, n_groups + 1)}

    for dt in dates:
        f_day = factor_df[factor_df["date"] == dt][["symbol", "value"]].dropna()
        r_day = returns_df[returns_df["date"] == dt][["symbol", ret_col]].dropna()
        merged = f_day.merge(r_day, on="symbol", how="inner")

        if len(merged) < n_groups * 2:
            continue

        # 按因子值排序分组
        merged = merged.sort_values("value")
        merged["group"] = pd.qcut(merged["value"], n_groups, labels=range(1, n_groups + 1))
        merged["group"] = merged["group"].astype(int)

        for g, sub in merged.groupby("group"):
            avg = sub[ret_col].mean()
            if pd.notna(avg):
                group_returns[g].append(avg)

    if not any(group_returns.values()):
        return pd.DataFrame()

    rows = []
    for g in range(1, n_groups + 1):
        rets = group_returns[g]
        if not rets:
            rows.append(
                {"group": g, "mean_ret": np.nan, "cum_ret": np.nan, "sharpe": np.nan, "win_rate": np.nan, "n_days": 0}
            )
            continue
        arr = np.array(rets)
        cum = float(np.prod(1 + arr) - 1)
        sharpe = float(arr.mean() / arr.std() * np.sqrt(252)) if arr.std() > 0 else 0
        rows.append(
            {
                "group": g,
                "mean_ret": float(arr.mean()),
                "cum_ret": cum,
                "sharpe": sharpe,
                "win_rate": float((arr > 0).mean()),
                "n_days": len(arr),
            }
        )

    result = pd.DataFrame(rows).set_index("group")
    # 长-短组收益差
    if len(result) >= 2:
        long_short = result.loc[n_groups, "mean_ret"] - result.loc[1, "mean_ret"]
        result.attrs["long_short_spread"] = long_short
        result.attrs["monotonic"] = _is_monotonic(result["mean_ret"].values)

    return result


def factor_decay(
    db: FactorDB | None = None,
    factor: str = "momentum_20d",
    max_lag: int = 20,
) -> pd.DataFrame:
    """因子自相关衰减分析 — 评估因子值的时间持续性。

    Returns:
        DataFrame, index=lag, columns: [autocorr, half_life]
    """
    if db is None:
        db = FactorDB()
    q = FactorQuery(db)

    factor_df = q.get_factor(factor)
    if factor_df.empty:
        return pd.DataFrame()

    # 取所有标的的平均因子值时序
    avg_ts = factor_df.mean(axis=1).dropna()
    if len(avg_ts) < max_lag + 2:
        return pd.DataFrame()

    lags = range(1, min(max_lag + 1, len(avg_ts)))
    corrs = [avg_ts.autocorr(lag=lag) for lag in lags]

    result = pd.DataFrame({"lag": list(lags), "autocorr": corrs}).set_index("lag")

    # 估算半衰期
    first_neg = next((i for i, c in enumerate(corrs) if c <= 0), len(corrs))
    if first_neg > 0:
        result.attrs["half_life_lag"] = first_neg
    else:
        result.attrs["half_life_lag"] = max_lag

    return result


def factor_correlation(
    db: FactorDB | None = None,
    factors: list[str] | None = None,
    symbols: list[str] | None = None,
) -> pd.DataFrame:
    """多因子截面相关性矩阵 (Spearman rank correlation 均值)。"""
    if db is None:
        db = FactorDB()
    q = FactorQuery(db)

    if factors is None:
        available = q.list_available_factors()
        factors = available["name"].tolist()[:10]  # 最多取10个

    if len(factors) < 2:
        return pd.DataFrame()

    # 获取每个因子的 pivot
    pivots = {}
    for f in factors:
        p = q.get_factor(f, symbols=symbols)
        if not p.empty:
            pivots[f] = p

    if len(pivots) < 2:
        return pd.DataFrame()

    # 按日期计算截面 rank correlation 均值
    common_dates: set | None = None
    for p in pivots.values():
        idx = set(p.index)
        common_dates = idx if common_dates is None else common_dates & idx
    common_date_list = sorted(common_dates) if common_dates else []

    if not common_date_list:
        return pd.DataFrame()

    n = len(pivots)
    corr_matrix = pd.DataFrame(np.nan, index=factors[:n], columns=factors[:n])

    for i, f1 in enumerate(factors[:n]):
        for j, f2 in enumerate(factors[:n]):
            if i >= j:
                continue
            p1, p2 = pivots[f1], pivots[f2]
            corrs = []
            for dt in common_date_list:
                if dt in p1.index and dt in p2.index:
                    s1 = p1.loc[dt].dropna()
                    s2 = p2.loc[dt].dropna()
                    common_sym = s1.index.intersection(s2.index)
                    if len(common_sym) >= 5:
                        c = s1[common_sym].rank().corr(s2[common_sym].rank())
                        if pd.notna(c):
                            corrs.append(c)
            if corrs:
                corr_matrix.loc[f1, f2] = np.mean(corrs)
                corr_matrix.loc[f2, f1] = np.mean(corrs)

    np.fill_diagonal(corr_matrix.values, 1.0)
    return corr_matrix


def _is_monotonic(values: np.ndarray) -> bool:
    """检查序列是否单调递增。"""
    return bool(np.all(np.diff(values) >= -1e-10))
