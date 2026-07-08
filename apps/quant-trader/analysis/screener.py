"""可迭代筛选管线 — 链式过滤器 + 多维评分 + 弹性阈值.

设计原则:
  - 每个筛选器独立, 可插拔
  - 支持链式组合: screener.add_filter(...).add_filter(...)
  - 筛选结果可追溯: 记录每一步通过/淘汰原因
  - 阈值可动态调整: 根据市场环境自适应
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .factors import multi_factor_score
from .indicators import indicator_summary
from .volume import volume_summary

# ═══════════════════════════════════════════════════════════════════════
# 筛选器接口
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class ScreenFilter:
    """单个筛选器定义."""
    name: str
    description: str
    check: Callable[[pd.DataFrame, dict], tuple[bool, float, str]]
    # check 函数: (通过?, 得分0-100, 原因)
    weight: float = 1.0
    enabled: bool = True
    threshold: float = 50.0  # 通过阈值

    def run(self, df: pd.DataFrame, context: dict) -> tuple[bool, float, str]:
        if not self.enabled:
            return True, 50.0, "已跳过"
        try:
            passed, score, reason = self.check(df, context)
            return passed, score, reason
        except Exception as e:
            return False, 0, f"异常: {e}"


@dataclass
class FilterResult:
    """单个筛选器的结果."""
    name: str
    passed: bool
    score: float
    reason: str
    weight: float
    elapsed_ms: float = 0


@dataclass
class ScreenResult:
    """单标的筛选结果."""
    symbol: str
    name: str
    passed: bool
    composite_score: float
    grade: str
    signal: str
    filters: list[FilterResult] = field(default_factory=list)
    factor_scores: dict = field(default_factory=dict)
    indicators: dict = field(default_factory=dict)
    volume_info: dict = field(default_factory=dict)
    top_signals: list[str] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)
    elapsed_s: float = 0

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "passed": self.passed,
            "composite_score": round(self.composite_score, 1),
            "grade": self.grade,
            "signal": self.signal,
            "filters": [
                {"name": f.name, "passed": f.passed, "score": round(f.score, 1),
                 "reason": f.reason, "elapsed_ms": round(f.elapsed_ms, 1)}
                for f in self.filters
            ],
            "factor_scores": self.factor_scores,
            "indicators": self.indicators,
            "volume_info": self.volume_info,
            "top_signals": self.top_signals,
            "rejection_reasons": self.rejection_reasons,
            "elapsed_s": round(self.elapsed_s, 2),
        }


# ═══════════════════════════════════════════════════════════════════════
# 内置筛选器
# ═══════════════════════════════════════════════════════════════════════

def _filter_trend(df: pd.DataFrame, ctx: dict) -> tuple[bool, float, str]:
    """趋势筛选: 价格 > MA20 且 MA20 > MA60."""
    from .indicators import calc_ma_alignment
    close = df["close"]
    ma = calc_ma_alignment(close, [20, 60])
    price = float(close.iloc[-1])
    ma20 = ma["ma_values"].get("ma20", 0)
    ma60 = ma["ma_values"].get("ma60", 0)

    if price > ma20 > ma60:
        return True, 80, f"多头排列: 价{price:.2f} > MA20({ma20:.2f}) > MA60({ma60:.2f})"
    elif price > ma20:
        return True, 60, f"价在MA20之上, 但MA20<MA60"
    else:
        return False, 35, f"价{price:.2f} < MA20({ma20:.2f}), 趋势偏弱"


def _filter_momentum(df: pd.DataFrame, ctx: dict) -> tuple[bool, float, str]:
    """动量筛选: 近20日收益 > 0."""
    close = df["close"]
    if len(close) < 20:
        return False, 40, "数据不足"
    ret = float(close.iloc[-1] / close.iloc[-20] - 1)
    if ret > 0.05:
        return True, 80, f"20日涨{ret*100:.1f}%, 动量强劲"
    elif ret > 0:
        return True, 60, f"20日涨{ret*100:.1f}%, 温和上涨"
    else:
        return False, 35, f"20日跌{ret*100:.1f}%, 动量不足"


def _filter_volume(df: pd.DataFrame, ctx: dict) -> tuple[bool, float, str]:
    """成交量筛选: 量比适中, OBV 正向."""
    from .volume import calc_obv_slope, calc_volume_ratio
    if "volume" not in df.columns:
        return True, 50, "无成交量数据"
    close = df["close"]
    volume = df["volume"]
    vr = calc_volume_ratio(volume)
    obv = calc_obv_slope(close, volume)

    score = vr["score"] * 0.4 + obv["score"] * 0.6
    if score >= 60:
        return True, score, f"量比{vr['ratio']:.1f}({vr['level']}) · 资金{obv['direction']}"
    elif score >= 45:
        return True, score, f"成交量中性"
    else:
        return False, score, f"量比{vr['ratio']:.1f} · 资金{obv['direction']}({obv['strength']})"


def _filter_rsi(df: pd.DataFrame, ctx: dict) -> tuple[bool, float, str]:
    """RSI 筛选: 非超买区间."""
    close = df["close"]
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = float((100 - 100 / (1 + rs)).iloc[-1]) if len(rs) > 14 else 50

    if rsi > 80:
        return False, 25, f"RSI={rsi:.0f} 严重超买"
    elif rsi > 70:
        return True, 40, f"RSI={rsi:.0f} 超买区, 谨慎追高"
    elif rsi < 30:
        return True, 75, f"RSI={rsi:.0f} 超卖区, 潜在反弹"
    elif rsi < 40:
        return True, 65, f"RSI={rsi:.0f} 偏低, 有回升空间"
    else:
        return True, 55, f"RSI={rsi:.0f} 中性区间"


def _filter_volatility(df: pd.DataFrame, ctx: dict) -> tuple[bool, float, str]:
    """波动率筛选: 非极端波动."""
    from .indicators import calc_atr
    atr = calc_atr(df)
    if atr["volatility_regime"] == "extreme":
        return False, 30, f"波动率极高(分位{atr['atr_percentile']:.0f}%), 风险大"
    elif atr["volatility_regime"] == "high":
        return True, 45, f"波动率偏高(分位{atr['atr_percentile']:.0f}%)"
    else:
        return True, atr["score"], f"波动率{atr['volatility_regime']}(分位{atr['atr_percentile']:.0f}%)"


def _filter_macd(df: pd.DataFrame, ctx: dict) -> tuple[bool, float, str]:
    """MACD 筛选: 金叉或多头."""
    from .indicators import calc_macd
    macd = calc_macd(df["close"])
    if macd["cross"] == "golden":
        return True, 80, "MACD 金叉"
    elif macd["histogram"] > 0:
        return True, 65, "MACD 柱状图为正"
    elif macd["cross"] == "death":
        return False, 30, "MACD 死叉"
    else:
        return True, 50, "MACD 中性"


def _filter_multi_factor(df: pd.DataFrame, ctx: dict) -> tuple[bool, float, str]:
    """多因子综合筛选."""
    weights = ctx.get("factor_weights")
    result = multi_factor_score(df, weights)
    composite = result["composite"]
    if composite >= 65 or composite >= 50:
        return True, composite, f"多因子{composite:.0f}分({result['grade']}) {result['signal']}"
    else:
        return False, composite, f"多因子{composite:.0f}分({result['grade']}) {result['signal']}"


# ═══════════════════════════════════════════════════════════════════════
# 可迭代筛选器
# ═══════════════════════════════════════════════════════════════════════

class IterativeScreener:
    """可迭代筛选管线.

    用法:
        screener = IterativeScreener()
        screener.add_filter("趋势", _filter_trend, threshold=50)
        screener.add_filter("动量", _filter_momentum, threshold=50)
        result = screener.screen("600519", "贵州茅台", prices)
    """

    def __init__(self, min_pass_ratio: float = 0.6):
        self.filters: list[ScreenFilter] = []
        self.min_pass_ratio = min_pass_ratio

    def add_filter(
        self,
        name: str,
        check: Callable[[pd.DataFrame, dict], tuple[bool, float, str]],
        description: str = "",
        weight: float = 1.0,
        threshold: float = 50.0,
        enabled: bool = True,
    ) -> IterativeScreener:
        """添加筛选器 (链式调用)."""
        self.filters.append(ScreenFilter(
            name=name, description=description, check=check,
            weight=weight, threshold=threshold, enabled=enabled,
        ))
        return self

    def remove_filter(self, name: str) -> IterativeScreener:
        """移除筛选器."""
        self.filters = [f for f in self.filters if f.name != name]
        return self

    def set_threshold(self, name: str, threshold: float) -> IterativeScreener:
        """调整筛选器阈值."""
        for f in self.filters:
            if f.name == name:
                f.threshold = threshold
        return self

    def screen(
        self,
        symbol: str,
        name: str,
        df: pd.DataFrame,
        context: dict | None = None,
    ) -> ScreenResult:
        """执行筛选."""
        t0 = time.time()
        ctx = context or {}
        filter_results: list[FilterResult] = []
        rejection_reasons: list[str] = []

        if df is None or len(df) < 20:
            return ScreenResult(
                symbol=symbol, name=name, passed=False,
                composite_score=0, grade="F", signal="数据不足",
                rejection_reasons=["数据不足"],
                elapsed_s=time.time() - t0,
            )

        # 执行所有筛选器
        for f in self.filters:
            ft = time.time()
            passed, score, reason = f.run(df, ctx)
            elapsed = (time.time() - ft) * 1000

            filter_results.append(FilterResult(
                name=f.name, passed=passed, score=score,
                reason=reason, weight=f.weight, elapsed_ms=elapsed,
            ))

            if not passed:
                rejection_reasons.append(f"{f.name}: {reason}")

        # 计算综合分 (加权)
        total_weight = sum(f.weight for f in self.filters if f.enabled)
        if total_weight > 0:
            weighted_sum = sum(
                r.score * r.weight for r, f in zip(filter_results, self.filters)
                if f.enabled
            )
            composite = weighted_sum / total_weight
        else:
            composite = 50

        # 判断是否通过
        enabled_filters = [r for r, f in zip(filter_results, self.filters) if f.enabled]
        passed_count = sum(1 for r in enabled_filters if r.passed)
        pass_ratio = passed_count / max(len(enabled_filters), 1)
        passed = pass_ratio >= self.min_pass_ratio

        # 多因子评分
        factor_result = multi_factor_score(df, ctx.get("factor_weights"))
        composite = composite * 0.5 + factor_result["composite"] * 0.5

        # 评级
        if composite >= 75:
            grade, signal = "A", "强烈看多"
        elif composite >= 62:
            grade, signal = "B", "偏多"
        elif composite >= 45:
            grade, signal = "C", "中性"
        elif composite >= 30:
            grade, signal = "D", "偏空"
        else:
            grade, signal = "E", "强烈看空"

        # 指标摘要
        indicators = indicator_summary(df)
        volume_info = volume_summary(df)

        return ScreenResult(
            symbol=symbol,
            name=name,
            passed=passed,
            composite_score=round(composite, 1),
            grade=grade,
            signal=signal,
            filters=filter_results,
            factor_scores=factor_result,
            indicators={
                "macd": indicators.get("macd", {}),
                "kdj": indicators.get("kdj", {}),
                "ma_alignment": indicators.get("ma_alignment", {}),
                "ichimoku": indicators.get("ichimoku", {}),
                "composite": indicators.get("composite_score", 50),
            },
            volume_info={
                "volume_ratio": volume_info.get("volume_ratio", {}),
                "obv_slope": volume_info.get("obv_slope", {}),
                "money_flow": volume_info.get("money_flow", {}),
                "composite": volume_info.get("composite_score", 50),
            },
            top_signals=factor_result.get("top_signals", []),
            rejection_reasons=rejection_reasons,
            elapsed_s=round(time.time() - t0, 3),
        )

    def screen_batch(
        self,
        symbols: list[tuple[str, str, pd.DataFrame]],
        context: dict | None = None,
        top_n: int = 10,
    ) -> list[ScreenResult]:
        """批量筛选, 返回 Top N."""
        results = []
        for symbol, name, df in symbols:
            result = self.screen(symbol, name, df, context)
            results.append(result)

        # 按综合分排序
        results.sort(key=lambda x: x.composite_score, reverse=True)
        return results[:top_n]


# ═══════════════════════════════════════════════════════════════════════
# 默认筛选器配置
# ═══════════════════════════════════════════════════════════════════════

def default_screener(
    min_pass_ratio: float = 0.5,
    factor_weights: dict[str, float] | None = None,
) -> IterativeScreener:
    """创建默认筛选器 (7 个维度)."""
    screener = IterativeScreener(min_pass_ratio=min_pass_ratio)

    screener.add_filter("趋势", _filter_trend, weight=1.2, threshold=50)
    screener.add_filter("动量", _filter_momentum, weight=1.0, threshold=50)
    screener.add_filter("成交量", _filter_volume, weight=0.8, threshold=45)
    screener.add_filter("RSI", _filter_rsi, weight=0.8, threshold=40)
    screener.add_filter("波动率", _filter_volatility, weight=0.7, threshold=40)
    screener.add_filter("MACD", _filter_macd, weight=1.0, threshold=45)
    screener.add_filter("多因子", _filter_multi_factor, weight=1.5, threshold=50)

    return screener
