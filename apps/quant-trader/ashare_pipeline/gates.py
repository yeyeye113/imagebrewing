"""三关筛选逻辑: 策略共振, 趋势强度 (五行/卦象预筛已下线)."""
from __future__ import annotations

import pandas as pd

from ..log import get_logger
from ..strategy.base import get_strategy
from .constants import RESONANCE_CORE_STRATEGIES, RESONANCE_WINDOWS

logger = get_logger("pipeline")


def sector_preselect(
    symbols: list[tuple[str, str, str, str]],
    use_wuxing: bool = True,
    max_symbols: int = 18,
) -> tuple[list[tuple[str, str, str, str]], dict]:
    """按池容量裁剪标的（五行定向预筛已下线）。"""
    _ = use_wuxing
    filtered = list(symbols)[:max_symbols]
    summary = {
        "n_before": len(symbols),
        "n_after": len(filtered),
        "preselect_cut": "技术面池",
        "hot_sectors": [],
    }
    return filtered, summary


def check_resonance(prices: pd.DataFrame, kind: str = "stock") -> tuple[bool, dict]:
    """轻量共振关: 多窗口策略信号共识 (无全量回测)."""
    if prices is None or len(prices) < 120:
        return False, {}
    windows = [w for w in RESONANCE_WINDOWS if len(prices) >= w]
    if not windows:
        windows = [min(120, len(prices))]
    results: dict[str, bool] = {}
    bullish = bearish = 0
    for w_size in windows:
        window_data = prices.iloc[-w_size:]
        for sname, sparams, label in RESONANCE_CORE_STRATEGIES:
            key = f"{w_size}d/{label}"
            try:
                sig = int(get_strategy(sname, **sparams).generate(window_data).iloc[-1])
                results[key] = sig == 1
                if sig == 1:
                    bullish += 1
                elif sig == -1:
                    bearish += 1
            except Exception:
                results[key] = False
    pass_rate = sum(results.values()) / max(len(results), 1)
    min_rate = 0.55 if kind == "future" else 0.62
    passed = pass_rate >= min_rate and bullish > bearish
    return passed, results


def check_trend(prices: pd.DataFrame, kind: str = "stock") -> tuple[bool, float]:
    """近20日涨幅>0 且 收盘价 > 60日均线（期货略放宽）"""
    if prices is None or len(prices) < 60:
        return False, 0.0
    close = prices["close"]
    ret_20d = float(close.iloc[-1] / close.iloc[-20] - 1) if len(close) >= 20 else 0.0
    ma60 = close.rolling(60).mean()
    above_ma = float(close.iloc[-1]) > float(ma60.iloc[-1]) if len(ma60) > 0 and pd.notna(ma60.iloc[-1]) else False
    if kind == "future":
        ma20 = close.rolling(20).mean()
        above_ma20 = (
            float(close.iloc[-1]) > float(ma20.iloc[-1])
            if len(ma20) > 0 and pd.notna(ma20.iloc[-1]) else False
        )
        passed = (ret_20d > 0 and above_ma) or (above_ma20 and ret_20d > -0.02)
    else:
        passed = ret_20d > 0 and above_ma
    trend_score = min(max(ret_20d * 100 + 50, 0), 100)
    return passed, trend_score


def check_wuxing_gate(
    symbol: str,
    name: str,
    sector: str,
    element: str,
    kind: str = "stock",
    div_reading=None,
    bazi_reading=None,
) -> tuple[bool, dict]:
    """五行/卦象关已下线 — 恒通过并返回中性分。"""
    _ = (symbol, name, sector, kind, div_reading, bazi_reading)
    neutral_wx = {"score": 50, "element": element or "", "relation": ""}
    neutral_bazi = {"score": 50, "chang_sheng": "", "nayin": ""}
    return True, {
        "wuxing": neutral_wx,
        "bazi": neutral_bazi,
        "divination": None,
        "wx_pass": True,
        "bagua_pass": True,
        "skipped": True,
    }
