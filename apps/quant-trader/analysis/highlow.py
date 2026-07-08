"""关键高低点识别 — 支撑/阻力/枢轴点。

方法:
  1. 局部极值法 — 滑动窗口找局部最高/最低
  2. 枢轴点 (Pivot Point) — 经典 S1/S2/R1/R2
  3. 成交量加权 — 高量价位更有意义
  4. 整数关口 — 心理价位

输入: DataFrame (close, high, low, volume)
输出: HighLowResult (关键价位列表 + 当前位置判断)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class KeyLevel:
    """一个关键价位。"""

    price: float
    kind: str  # "support" | "resistance" | "pivot"
    strength: int  # 1-5, 越高越强
    source: str  # "local_extrema" | "pivot" | "volume_cluster" | "round_number"
    touches: int = 0  # 被触及次数 (局部极值)
    last_touch: str = ""  # 最后触及日期

    def to_text(self) -> str:
        icon = {"support": "🟢", "resistance": "🔴", "pivot": "🟡"}.get(self.kind, "⚪")
        stars = "★" * self.strength + "☆" * (5 - self.strength)
        return f"{icon} ¥{self.price:,.2f} [{self.kind:10s}] {stars} ({self.source})"


@dataclass
class HighLowResult:
    """高低点分析结果。"""

    symbol: str
    current_price: float
    levels: list[KeyLevel] = field(default_factory=list)
    nearest_support: float = 0.0
    nearest_resistance: float = 0.0
    position_pct: float = 0.0  # 当前价在支撑~阻力之间的位置 (0=支撑, 100=阻力)
    atr: float = 0.0  # 14日ATR
    trend: str = ""  # "上升趋势 ↑" | "下降趋势 ↓" | "横盘震荡 ↔"
    trend_score: int = 50  # 趋势强度 (0-100)
    vol_regime: str = "正常"  # "高波动" | "低波动" | "正常"
    vwap: float = 0.0  # VWAP
    swing_high: float = 0.0  # 20日最高
    swing_low: float = 0.0  # 20日最低

    def supports(self) -> list[KeyLevel]:
        return sorted([l for l in self.levels if l.kind == "support"], key=lambda x: x.price, reverse=True)

    def resistances(self) -> list[KeyLevel]:
        return sorted([l for l in self.levels if l.kind == "resistance"], key=lambda x: x.price)

    def to_text(self) -> str:
        lines = [
            "╔══════════════════════════════════════════════╗",
            f"║  📐 {self.symbol} 高低点分析                    ║",
            "╠══════════════════════════════════════════════╣",
            f"║  当前价: ¥{self.current_price:,.2f}                      ║",
            f"║  ATR(14): ¥{self.atr:,.2f}                     ║",
            f"║  趋势: {self.trend:<38s} ║",
            f"║  位置: 支撑{self.nearest_support:,.0f} ← {self.position_pct:.0f}% → 阻力{self.nearest_resistance:,.0f}  ║",
            "╠══════════════════════════════════════════════╣",
            "║  阻力位:                                      ║",
        ]
        for l in self.resistances()[:5]:
            lines.append(f"║    {l.to_text():<42s} ║")
        lines.append("║  支撑位:                                      ║")
        for l in self.supports()[:5]:
            lines.append(f"║    {l.to_text():<42s} ║")
        lines.append("╚══════════════════════════════════════════════╝")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "current_price": self.current_price,
            "atr": round(self.atr, 2),
            "trend": self.trend,
            "nearest_support": self.nearest_support,
            "nearest_resistance": self.nearest_resistance,
            "position_pct": round(self.position_pct, 1),
            "levels": [
                {"price": l.price, "kind": l.kind, "strength": l.strength, "source": l.source, "touches": l.touches}
                for l in self.levels
            ],
        }


# ══════════════════════════════════════════════════════════════════
# 核心算法
# ══════════════════════════════════════════════════════════════════


def _local_extrema(prices: pd.Series, window: int = 5) -> tuple[list[int], list[int]]:
    """找局部极值点的索引。"""
    highs, lows = [], []
    arr = prices.values
    for i in range(window, len(arr) - window):
        if arr[i] == max(arr[i - window : i + window + 1]):
            highs.append(i)
        if arr[i] == min(arr[i - window : i + window + 1]):
            lows.append(i)
    return highs, lows


def _cluster_levels(prices: list[float], tolerance: float) -> list[tuple[float, int]]:
    """将相近价位聚类，返回 (价位, 触及次数)。"""
    if not prices:
        return []
    sorted_p = sorted(prices)
    clusters: list[list[float]] = [[sorted_p[0]]]
    for p in sorted_p[1:]:
        if abs(p - clusters[-1][-1]) <= tolerance:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    return [(float(np.mean(c)), len(c)) for c in clusters]


def _pivot_points(high: float, low: float, close: float) -> dict[str, float]:
    """经典枢轴点计算。"""
    pp = (high + low + close) / 3
    return {
        "R2": pp + (high - low),
        "R1": 2 * pp - low,
        "P": pp,
        "S1": 2 * pp - high,
        "S2": pp - (high - low),
    }


def _fibonacci_levels(high: float, low: float) -> dict[str, float]:
    """斐波那契回撤位。"""
    diff = high - low
    return {
        "Fib_0.0": high,
        "Fib_0.236": high - 0.236 * diff,
        "Fib_0.382": high - 0.382 * diff,
        "Fib_0.5": high - 0.5 * diff,
        "Fib_0.618": high - 0.618 * diff,
        "Fib_0.786": high - 0.786 * diff,
        "Fib_1.0": low,
    }


def _vwap(prices: pd.DataFrame) -> float:
    """成交量加权平均价 (VWAP)。"""
    if "volume" not in prices.columns or prices["volume"].sum() == 0:
        return float(prices["close"].mean())
    typical = (prices["high"] + prices["low"] + prices["close"]) / 3
    return float((typical * prices["volume"]).sum() / prices["volume"].sum())


def _ema(series: pd.Series, span: int) -> pd.Series:
    """指数移动平均。"""
    return series.ewm(span=span, adjust=False).mean()


def _round_numbers(price: float, n: int = 5) -> list[float]:
    """找附近的整数关口。"""
    step = 10 ** (int(np.log10(max(price, 1))) - 1)
    base = round(price / step) * step
    return [base + i * step for i in range(-n, n + 1) if abs(base + i * step - price) / price < 0.1]


def find_highlows(
    df: pd.DataFrame,
    symbol: str = "",
    window: int = 5,
    cluster_tol_pct: float = 0.02,
) -> HighLowResult:
    """分析 DataFrame 找出关键高低点。

    Args:
        df: 必须含 close, high, low 列; volume 可选
        symbol: 标的代码
        window: 局部极值滑动窗口大小
        cluster_tol_pct: 价格聚类容差 (百分比)
    """
    close = df["close"].dropna()
    high = df["high"].dropna()
    low = df["low"].dropna()

    if len(close) < 20:
        return HighLowResult(symbol=symbol, current_price=float(close.iloc[-1]) if len(close) > 0 else 0)

    current = float(close.iloc[-1])
    tol = current * cluster_tol_pct
    levels: list[KeyLevel] = []

    # ① 局部极值
    hi_idx, lo_idx = _local_extrema(close, window=window)
    hi_prices = [float(close.iloc[i]) for i in hi_idx]
    lo_prices = [float(close.iloc[i]) for i in lo_idx]

    for price, touches in _cluster_levels(hi_prices, tol):
        if price > current:
            levels.append(
                KeyLevel(
                    price=price,
                    kind="resistance",
                    strength=min(touches + 1, 5),
                    source="local_extrema",
                    touches=touches,
                )
            )
        else:
            levels.append(
                KeyLevel(
                    price=price, kind="support", strength=min(touches + 1, 5), source="local_extrema", touches=touches
                )
            )

    for price, touches in _cluster_levels(lo_prices, tol):
        if price < current:
            levels.append(
                KeyLevel(
                    price=price, kind="support", strength=min(touches + 1, 5), source="local_extrema", touches=touches
                )
            )
        else:
            levels.append(
                KeyLevel(
                    price=price,
                    kind="resistance",
                    strength=min(touches + 1, 5),
                    source="local_extrema",
                    touches=touches,
                )
            )

    # ② 枢轴点 (用最近一根K线)
    pivots = _pivot_points(float(high.iloc[-1]), float(low.iloc[-1]), float(close.iloc[-1]))
    for name, p in pivots.items():
        kind = "pivot" if name == "P" else ("resistance" if "R" in name else "support")
        strength = 3 if name == "P" else 2
        levels.append(KeyLevel(price=p, kind=kind, strength=strength, source="pivot"))

    # ③ 斐波那契回撤 (用最近20日高低点)
    swing_high = float(high.tail(20).max())
    swing_low = float(low.tail(20).min())
    fibs = _fibonacci_levels(swing_high, swing_low)
    for name, p in fibs.items():
        if name in ("Fib_0.0", "Fib_1.0"):
            continue  # 跳过极值点
        kind = "resistance" if p > current else "support"
        strength = 3 if name in ("Fib_0.382", "Fib_0.618") else 2
        levels.append(KeyLevel(price=p, kind=kind, strength=strength, source="fibonacci"))

    # ④ VWAP (成交量加权平均价)
    vwap = _vwap(df.tail(20))
    vwap_kind = "resistance" if vwap > current else "support"
    levels.append(KeyLevel(price=vwap, kind=vwap_kind, strength=4, source="vwap"))

    # ⑤ 成交量加权价位
    if "volume" in df.columns:
        vol = df["volume"].dropna()
        if len(vol) > 0:
            top_vol_idx = vol.nlargest(min(5, len(vol))).index
            for idx in top_vol_idx:
                p = float(close.loc[idx]) if idx in close.index else 0
                if p > 0:
                    kind = "resistance" if p > current else "support"
                    levels.append(KeyLevel(price=p, kind=kind, strength=3, source="volume_cluster"))

    # ⑥ EMA 动态支撑阻力
    ema20 = float(_ema(close, 20).iloc[-1])
    ema60 = float(_ema(close, 60).iloc[-1]) if len(close) >= 60 else ema20
    for ema_val, ema_name in [(ema20, "EMA20"), (ema60, "EMA60")]:
        if abs(ema_val - current) / current > 0.005:
            kind = "resistance" if ema_val > current else "support"
            strength = 4 if ema_name == "EMA20" else 3
            levels.append(KeyLevel(price=ema_val, kind=kind, strength=strength, source=ema_name.lower()))

    # ⑦ 整数关口
    for rn in _round_numbers(current):
        if abs(rn - current) / current > 0.005:  # 排除太近的
            kind = "resistance" if rn > current else "support"
            levels.append(KeyLevel(price=rn, kind=kind, strength=2, source="round_number"))

    # 去重 (价格相近的合并)
    deduped: list[KeyLevel] = []
    for l in sorted(levels, key=lambda x: x.price):
        if deduped and abs(l.price - deduped[-1].price) < tol:
            # 合并: 取更强的
            if l.strength > deduped[-1].strength:
                deduped[-1] = l
        else:
            deduped.append(l)

    # ATR(14)
    tr = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = float(tr.rolling(14).mean().iloc[-1]) if len(tr) >= 14 else float(tr.mean())

    # 最近支撑/阻力 (按强度排序)
    supports = sorted(
        [l for l in deduped if l.kind == "support" and l.price < current], key=lambda x: (-x.strength, -x.price)
    )
    resistances = sorted(
        [l for l in deduped if l.kind == "resistance" and l.price > current], key=lambda x: (-x.strength, x.price)
    )
    nearest_s = supports[0].price if supports else current * 0.95
    nearest_r = resistances[0].price if resistances else current * 1.05

    # 位置百分比
    span = nearest_r - nearest_s
    pos_pct = ((current - nearest_s) / span * 100) if span > 0 else 50

    # 趋势判断 (多维度)
    sma5 = float(close.tail(5).mean())
    sma10 = float(close.tail(10).mean())
    sma20 = float(close.tail(20).mean())
    sma60 = float(close.tail(min(60, len(close))).mean())
    ema12 = float(_ema(close, 12).iloc[-1])
    ema26 = float(_ema(close, 26).iloc[-1]) if len(close) >= 26 else ema12

    # 趋势强度评分 (0-100)
    trend_score = 50  # 中性起点
    if sma5 > sma10 > sma20:
        trend_score += 20  # 短期多头排列
    elif sma5 < sma10 < sma20:
        trend_score -= 20  # 短期空头排列
    if sma20 > sma60:
        trend_score += 15  # 中期多头
    elif sma20 < sma60:
        trend_score -= 15  # 中期空头
    if ema12 > ema26:
        trend_score += 10  # MACD多头
    elif ema12 < ema26:
        trend_score -= 10  # MACD空头
    if current > sma20:
        trend_score += 5  # 价格在均线上方
    else:
        trend_score -= 5  # 价格在均线下方

    if trend_score >= 70:
        trend = "强上升趋势 ↑↑"
    elif trend_score >= 55:
        trend = "上升趋势 ↑"
    elif trend_score <= 30:
        trend = "强下降趋势 ↓↓"
    elif trend_score <= 45:
        trend = "下降趋势 ↓"
    else:
        trend = "横盘震荡 ↔"

    # 波动率判断
    vol_20 = float(close.pct_change().tail(20).std() * 100)
    vol_regime = "高波动" if vol_20 > 3 else ("低波动" if vol_20 < 1 else "正常")

    # VWAP
    vwap = _vwap(df.tail(20))

    return HighLowResult(
        symbol=symbol,
        current_price=current,
        levels=deduped,
        nearest_support=nearest_s,
        nearest_resistance=nearest_r,
        position_pct=pos_pct,
        atr=atr,
        trend=trend,
        trend_score=trend_score,
        vol_regime=vol_regime,
        vwap=vwap,
        swing_high=swing_high,
        swing_low=swing_low,
    )
