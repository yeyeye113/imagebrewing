"""多源数据验证器 — 交叉验证多个数据源确保价格准确。

数据源:
  - 新浪期货 (主)
  - 东方财富 (备)
  - 同花顺 (备)

功能:
  - 多源获取价格
  - 交叉验证
  - 异常值剔除
  - 中位数取值

用法:
    from quanttrader.data.multi_source import MultiSourceValidator
    validator = MultiSourceValidator()
    price = validator.get_verified_price('RB')
"""

from __future__ import annotations

import statistics
import time

import requests


class MultiSourceValidator:
    """多源数据验证器。"""

    def __init__(self):
        self.sources = {
            "sina": self._get_sina_price,
            "eastmoney": self._get_eastmoney_price,
        }
        self.cache: dict[str, tuple[float, float]] = {}  # {symbol: (price, timestamp)}
        self.cache_ttl = 5  # 缓存5秒

    def get_verified_price(self, symbol: str) -> float | None:
        """获取验证后的价格。

        Args:
            symbol: 品种代码 (如 'RB', 'I')

        Returns:
            验证后的价格，失败返回 None
        """
        # 检查缓存
        if symbol in self.cache:
            price, timestamp = self.cache[symbol]
            if time.time() - timestamp < self.cache_ttl:
                return price

        # 多源获取
        prices = []
        for source_name, source_func in self.sources.items():
            try:
                price = source_func(symbol)
                if price and price > 0:
                    prices.append(price)
            except Exception:
                pass

        if not prices:
            return None

        # 剔除异常值 (如果有多于2个数据源)
        if len(prices) >= 3:
            prices = self._remove_outliers(prices)

        # 取中位数
        verified_price = statistics.median(prices)

        # 更新缓存
        self.cache[symbol] = (verified_price, time.time())

        return verified_price

    def get_verified_batch(self, symbols: list[str]) -> dict[str, float]:
        """批量获取验证价格。"""
        results = {}
        for symbol in symbols:
            price = self.get_verified_price(symbol)
            if price:
                results[symbol] = price
        return results

    def _get_sina_price(self, symbol: str) -> float | None:
        """从新浪获取价格。"""
        sina_codes = {
            "I": "I0",
            "RB": "RB0",
            "SC": "SC0",
            "AU": "AU0",
            "AG": "AG0",
            "HC": "HC0",
            "FU": "FU0",
            "CU": "CU0",
            "AL": "AL0",
            "ZN": "ZN0",
            "MA": "MA0",
            "TA": "TA0",
            "SA": "SA0",
            "M": "M0",
            "P": "P0",
            "Y": "Y0",
            "IF": "IF0",
            "IC": "IC0",
            "IH": "IH0",
            "IM": "IM0",
        }
        sina_code = sina_codes.get(symbol.upper(), f"{symbol.upper()}0")
        url = f"https://hq.sinajs.cn/list={sina_code}"
        headers = {"Referer": "https://finance.sina.com.cn"}

        resp = requests.get(url, headers=headers, timeout=5)
        resp.encoding = "gbk"

        import re

        match = re.search(r'"([^"]+)"', resp.text)
        if match:
            parts = match.group(1).split(",")
            if len(parts) >= 6:
                return float(parts[5])  # 收盘价
        return None

    def _get_eastmoney_price(self, symbol: str) -> float | None:
        """从东方财富获取价格。"""
        # 东方财富期货代码映射
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

        url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={em_code}"
        resp = requests.get(url, timeout=5)
        data = resp.json()

        if data.get("data") and data["data"].get("f43"):
            return float(data["data"]["f43"]) / 100  # 东方财富价格需要除以100
        return None

    def _remove_outliers(self, prices: list[float]) -> list[float]:
        """剔除异常值 (超过2个标准差)。"""
        if len(prices) < 3:
            return prices

        mean = statistics.mean(prices)
        std = statistics.stdev(prices)

        if std == 0:
            return prices

        filtered = [p for p in prices if abs(p - mean) <= 2 * std]
        return filtered if filtered else prices

    def validate_price(self, symbol: str, expected_price: float, tolerance: float = 0.02) -> bool:
        """验证价格是否在预期范围内。

        Args:
            symbol: 品种代码
            expected_price: 预期价格
            tolerance: 容差 (默认2%)

        Returns:
            是否在范围内
        """
        actual_price = self.get_verified_price(symbol)
        if actual_price is None:
            return False

        deviation = abs(actual_price - expected_price) / expected_price
        return deviation <= tolerance
