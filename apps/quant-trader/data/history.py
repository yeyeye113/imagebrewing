"""历史数据获取器 — 获取真实历史K线数据。

数据源:
  - 新浪期货历史K线
  - 东方财富历史K线

功能:
  - 获取真实历史数据
  - 数据清洗和插值
  - 缓存机制

用法:
    from quanttrader.data.history import HistoryDataFetcher
    fetcher = HistoryDataFetcher()
    df = fetcher.get_history('RB', days=60)
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import requests


class HistoryDataFetcher:
    """历史数据获取器。"""

    def __init__(self, cache_dir: str = "data/cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl = 3600  # 缓存1小时

    def get_history(self, symbol: str, days: int = 60) -> pd.DataFrame | None:
        """获取历史K线数据。

        Args:
            symbol: 品种代码
            days: 获取天数

        Returns:
            DataFrame with OHLCV data
        """
        # 检查缓存
        cache_file = self.cache_dir / f"{symbol}_{days}.csv"
        if cache_file.exists():
            mtime = cache_file.stat().st_mtime
            if time.time() - mtime < self.cache_ttl:
                try:
                    return pd.read_csv(cache_file, index_col=0, parse_dates=True)
                except Exception:
                    pass

        # 尝试从各数据源获取
        df = None

        # 源1: 新浪期货
        try:
            df = self._fetch_sina_history(symbol, days)
        except Exception:
            pass

        # 源2: 东方财富
        if df is None or len(df) < days * 0.5:
            try:
                df = self._fetch_eastmoney_history(symbol, days)
            except Exception:
                pass

        # 缓存结果
        if df is not None and len(df) > 0:
            df.to_csv(cache_file)

        return df

    def _fetch_sina_history(self, symbol: str, days: int) -> pd.DataFrame | None:
        """从新浪获取历史数据。"""
        # 新浪期货历史K线API
        sina_codes = {
            "I": "I0",
            "RB": "RB0",
            "SC": "SC0",
            "AU": "AU0",
            "AG": "AG0",
            "HC": "HC0",
            "FU": "FU0",
            "CU": "CU0",
        }
        sina_code = sina_codes.get(symbol.upper(), f"{symbol.upper()}0")

        # 使用新浪的历史K线接口
        url = f"https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var=/InnerFuturesNewService.getDailyKLine?symbol={sina_code}"
        resp = requests.get(url, timeout=10)
        resp.encoding = "gbk"

        # 解析JSONP响应
        import json
        import re

        match = re.search(r"=(\[.+\])", resp.text)
        if not match:
            return None

        data = json.loads(match.group(1))

        # 转换为DataFrame
        records = []
        for item in data[-days:]:
            if len(item) >= 5:
                records.append(
                    {
                        "date": item[0],
                        "open": float(item[1]),
                        "high": float(item[2]),
                        "low": float(item[3]),
                        "close": float(item[4]),
                        "volume": int(float(item[5])) if len(item) > 5 else 0,
                    }
                )

        if not records:
            return None

        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        return df

    def _fetch_eastmoney_history(self, symbol: str, days: int) -> pd.DataFrame | None:
        """从东方财富获取历史数据。"""
        em_codes = {
            "I": "115.I0",
            "RB": "115.RB0",
            "SC": "142.SC0",
            "AU": "113.AU0",
            "AG": "113.AG0",
            "HC": "115.HC0",
            "CU": "113.CU0",
            "AL": "113.AL0",
            "ZN": "113.ZN0",
        }
        em_code = em_codes.get(symbol.upper())
        if not em_code:
            return None

        url = f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={em_code}&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58&klt=101&fqt=1&end=20500101&lmt={days}"
        resp = requests.get(url, timeout=10)
        data = resp.json()

        if not data.get("data") or not data["data"].get("klines"):
            return None

        records = []
        for line in data["data"]["klines"]:
            parts = line.split(",")
            if len(parts) >= 6:
                records.append(
                    {
                        "date": parts[0],
                        "open": float(parts[1]),
                        "close": float(parts[2]),
                        "high": float(parts[3]),
                        "low": float(parts[4]),
                        "volume": int(float(parts[5])),
                    }
                )

        if not records:
            return None

        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        return df

    def fill_missing_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """填充缺失数据。"""
        # 前向填充
        df = df.ffill()

        # 后向填充 (如果开头有缺失)
        df = df.bfill()

        # 确保OHLC关系正确
        for col in ["open", "high", "low", "close"]:
            if col in df.columns:
                df[col] = df[col].clip(lower=0)

        return df

    def validate_data(self, df: pd.DataFrame) -> bool:
        """验证数据质量。"""
        if df is None or len(df) < 10:
            return False

        # 检查是否有缺失值
        if df.isnull().any().any():
            return False

        # 检查OHLC关系
        for _, row in df.iterrows():
            if row["high"] < row["low"]:
                return False
            if row["high"] < row["open"] or row["high"] < row["close"]:
                return False
            if row["low"] > row["open"] or row["low"] > row["close"]:
                return False

        return True
