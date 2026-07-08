"""新浪期货数据源 — 真实行情获取。

提供:
  - 实时行情: get_realtime(codes) → dict
  - 历史K线: get_history(code, days) → DataFrame
  - 批量行情: get_batch(codes) → dict

数据源: 新浪财经期货 API
"""

from __future__ import annotations

import re
import time
from datetime import datetime

import numpy as np
import pandas as pd
import requests

# 新浪期货代码映射
_SINA_CODES = {
    "I": "I0",  # 铁矿石
    "RB": "RB0",  # 螺纹钢
    "SC": "SC0",  # 原油
    "AU": "AU0",  # 黄金
    "AG": "AG0",  # 白银
    "HC": "HC0",  # 热卷
    "FU": "FU0",  # 燃油
    "CU": "CU0",  # 铜
    "AL": "AL0",  # 铝
    "ZN": "ZN0",  # 锌
    "MA": "MA0",  # 甲醇
    "TA": "TA0",  # PTA
    "SA": "SA0",  # 纯碱
    "M": "M0",  # 豆粕
    "P": "P0",  # 棕榈油
    "BU": "BU0",  # 沥青
    "EG": "EG0",  # 乙二醇
    "EB": "EB0",  # 苯乙烯
    "PP": "PP0",  # 聚丙烯
    "PG": "PG0",  # LPG
}


def get_realtime(codes: list[str]) -> dict[str, dict]:
    """获取实时行情。

    Args:
        codes: 品种代码列表 (如 ['I', 'RB', 'SC'])

    Returns:
        {code: {name, open, high, low, close, volume, time}}
    """
    # 构建新浪代码
    sina_codes = []
    for code in codes:
        sina_code = _SINA_CODES.get(code.upper(), f"{code.upper()}0")
        sina_codes.append(sina_code)

    # 批量请求
    url = f"https://hq.sinajs.cn/list={','.join(sina_codes)}"
    headers = {"Referer": "https://finance.sina.com.cn"}

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = "gbk"
    except Exception as e:
        print(f"获取行情失败: {e}")
        return {}

    # 解析结果
    results = {}
    lines = resp.text.strip().split("\n")

    for i, line in enumerate(lines):
        if i >= len(codes):
            break
        code = codes[i]
        data = _parse_sina_line(line)
        if data:
            results[code] = data

    return results


def _parse_sina_line(line: str) -> dict | None:
    """解析新浪行情数据行。"""
    match = re.search(r'"([^"]+)"', line)
    if not match:
        return None

    parts = match.group(1).split(",")
    if len(parts) < 10:
        return None

    try:
        return {
            "name": parts[0],
            "open": float(parts[2]) if parts[2] else 0,
            "high": float(parts[3]) if parts[3] else 0,
            "low": float(parts[4]) if parts[4] else 0,
            "close": float(parts[5]) if parts[5] else 0,
            "volume": int(float(parts[6])) if parts[6] else 0,
            "time": parts[1] if len(parts) > 1 else "",
        }
    except (ValueError, IndexError):
        return None


def get_history(code: str, days: int = 60) -> pd.DataFrame:
    """获取历史K线数据。

    ⚠️ DEPRECATED: 此函数不再返回合成数据。
    请使用 akshare 真实数据源:
        import akshare as ak
        df = ak.futures_main_sina(symbol=f'{code}0')

    如果需要合成数据用于单元测试，请使用:
        quanttrader.data.synthetic_futures_provider.get_synthetic_history()
    """
    raise NotImplementedError(
        f"sina_futures.get_history('{code}') 已禁用。\n"
        f"原因: 此函数使用几何布朗运动生成合成数据，不可用于训练/回测/paper。\n"
        f"请使用 akshare 真实数据: ak.futures_main_sina(symbol='{code}0')\n"
        f"如需合成数据测试: from quanttrader.data.synthetic_futures_provider import get_synthetic_history"
    )


def get_batch(codes: list[str]) -> dict[str, pd.DataFrame]:
    """批量获取历史数据。

    ⚠️ DEPRECATED: 此函数已禁用。请使用 akshare 真实数据源。
    """
    raise NotImplementedError(
        "sina_futures.get_batch() 已禁用。请使用 akshare: ak.futures_main_sina(symbol=code)"
    )


# 便捷函数
def current_price(code: str) -> float:
    """获取当前价格。"""
    data = get_realtime([code])
    if code in data:
        return data[code]["close"]
    return 0.0


def price_range(code: str) -> tuple[float, float]:
    """获取今日高低点。"""
    data = get_realtime([code])
    if code in data:
        return data[code]["low"], data[code]["high"]
    return 0.0, 0.0
