"""因子查询层 — 面向分析场景的便捷查询接口。

支持:
    - 按因子名 + 标的 + 日期范围查询
    - 截面查询 (某日全部标的的因子值)
    - 时序查询 (某标的全部日期的因子值)
    - 因子值转 DataFrame (pivot)
    - 多因子合并
"""

from __future__ import annotations

import pandas as pd

from .storage import FactorDB


class FactorQuery:
    """因子查询器，封装常用查询模式。"""

    def __init__(self, db: FactorDB | None = None):
        self.db = db or FactorDB()

    # ── 基础查询 ──────────────────────────────────────────────

    def get_factor(
        self,
        factor_name: str,
        symbols: list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
        params: str = "{}",
    ) -> pd.DataFrame:
        """查询单个因子，返回 DataFrame (index=date, columns=symbols)。"""
        fid = self.db.factor_id_by_name(factor_name, params)
        if fid is None:
            return pd.DataFrame()
        raw = self.db.read_factor_values(fid, symbols)
        if raw.empty:
            return raw
        raw["date"] = pd.to_datetime(raw["date"])
        if start:
            raw = raw[raw["date"] >= start]
        if end:
            raw = raw[raw["date"] <= end]
        pivot = raw.pivot_table(index="date", columns="symbol", values="value")
        return pivot.sort_index()

    def get_factor_long(
        self,
        factor_name: str,
        symbols: list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
        params: str = "{}",
    ) -> pd.DataFrame:
        """返回 long-format DataFrame (symbol, date, value)。"""
        fid = self.db.factor_id_by_name(factor_name, params)
        if fid is None:
            return pd.DataFrame()
        raw = self.db.read_factor_values(fid, symbols)
        if raw.empty:
            return raw
        raw["date"] = pd.to_datetime(raw["date"])
        if start:
            raw = raw[raw["date"] >= start]
        if end:
            raw = raw[raw["date"] <= end]
        return raw.sort_values(["symbol", "date"]).reset_index(drop=True)

    # ── 截面查询 ──────────────────────────────────────────────

    def cross_section(
        self,
        factor_name: str,
        date: str,
        params: str = "{}",
        n: int | None = None,
    ) -> pd.Series:
        """某日截面因子值，按值排序。返回 Series (index=symbol)。"""
        df = self.get_factor(factor_name, params=params)
        if df.empty:
            return pd.Series(dtype=float)
        date = pd.to_datetime(date)
        if date not in df.index:
            return pd.Series(dtype=float)
        cs = df.loc[date].dropna().sort_values(ascending=False)
        if n is not None:
            cs = cs.head(n)
        cs.index.name = "symbol"
        return cs

    # ── 时序查询 ──────────────────────────────────────────────

    def time_series(
        self,
        factor_name: str,
        symbol: str,
        params: str = "{}",
        start: str | None = None,
        end: str | None = None,
    ) -> pd.Series:
        """某标的的因子时序。返回 Series (index=date)。"""
        df = self.get_factor(factor_name, symbols=[symbol], params=params)
        if df.empty or symbol not in df.columns:
            return pd.Series(dtype=float)
        s = df[symbol].dropna()
        if start:
            s = s[s.index >= pd.to_datetime(start)]
        if end:
            s = s[s.index <= pd.to_datetime(end)]
        return s

    # ── 多因子合并 ────────────────────────────────────────────

    def merge_factors(
        self,
        factor_names: list[str],
        symbols: list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        """合并多个因子为一个 DataFrame，列为 (factor, symbol) MultiIndex。"""
        parts = {}
        for name in factor_names:
            df = self.get_factor(name, symbols=symbols, start=start, end=end)
            if not df.empty:
                parts[name] = df
        if not parts:
            return pd.DataFrame()
        return pd.concat(parts, axis=1)

    # ── 统计 ──────────────────────────────────────────────────

    def factor_stats(
        self,
        factor_name: str,
        symbols: list[str] | None = None,
    ) -> pd.DataFrame:
        """因子值的基本统计: mean, std, min, max, coverage。"""
        df = self.get_factor(factor_name, symbols=symbols)
        if df.empty:
            return pd.DataFrame()
        stats = pd.DataFrame(
            {
                "mean": df.mean(),
                "std": df.std(),
                "min": df.min(),
                "max": df.max(),
                "count": df.count(),
                "coverage": df.count() / len(df),
            }
        )
        return stats

    # ── 便利方法 ──────────────────────────────────────────────

    def list_available_factors(self) -> pd.DataFrame:
        return self.db.list_factors()

    def available_symbols(self) -> list[str]:
        return self.db.symbols()

    def get_returns(
        self,
        symbols: list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        """查询未来收益数据。"""
        raw = self.db.read_returns(symbols)
        if raw.empty:
            return raw
        raw["date"] = pd.to_datetime(raw["date"])
        if start:
            raw = raw[raw["date"] >= start]
        if end:
            raw = raw[raw["date"] <= end]
        return raw
