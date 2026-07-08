"""多周期共振分析 — 多时间维度趋势确认。

时间周期:
  - 日线 (长期趋势)
  - 4小时 (中期趋势)
  - 1小时 (短期趋势)

功能:
  - 多周期趋势判断
  - 共振信号识别
  - 置信度调整

用法:
    from quanttrader.analysis.multi_timeframe import MultiTimeframeAnalyzer
    analyzer = MultiTimeframeAnalyzer()
    result = analyzer.analyze(prices)
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class TimeframeResult:
    """单周期分析结果。"""

    timeframe: str  # 'daily', '4h', '1h'
    trend: str  # 'bullish', 'bearish', 'neutral'
    strength: float  # 0-1
    sma_alignment: str  # 'bullish', 'bearish', 'mixed'
    momentum: str  # 'positive', 'negative', 'neutral'


@dataclass
class MultiTimeframeResult:
    """多周期共振结果。"""

    daily: TimeframeResult
    h4: TimeframeResult
    h1: TimeframeResult
    resonance: str  # 'strong', 'medium', 'weak', 'none'
    resonance_direction: str  # 'bullish', 'bearish', 'neutral'
    confidence_adjustment: float  # -0.2 to +0.2


class MultiTimeframeAnalyzer:
    """多周期共振分析器。"""

    def __init__(self):
        self.periods = {
            "daily": 20,
            "4h": 30,
            "1h": 60,
        }

    def analyze(self, daily_prices: pd.DataFrame) -> MultiTimeframeResult:
        """分析多周期共振。

        Args:
            daily_prices: 日线数据 (至少60天)

        Returns:
            多周期共振结果
        """
        # 日线分析
        daily_result = self._analyze_timeframe(daily_prices, "daily")

        # 4小时分析 (从日线模拟)
        h4_prices = self._resample_to_4h(daily_prices)
        h4_result = self._analyze_timeframe(h4_prices, "4h")

        # 1小时分析 (从日线模拟)
        h1_prices = self._resample_to_1h(daily_prices)
        h1_result = self._analyze_timeframe(h1_prices, "1h")

        # 共振判断
        resonance, direction, adjustment = self._calculate_resonance(daily_result, h4_result, h1_result)

        return MultiTimeframeResult(
            daily=daily_result,
            h4=h4_result,
            h1=h1_result,
            resonance=resonance,
            resonance_direction=direction,
            confidence_adjustment=adjustment,
        )

    def _analyze_timeframe(self, prices: pd.DataFrame, timeframe: str) -> TimeframeResult:
        """分析单个时间周期。"""
        if prices is None or len(prices) < 10:
            return TimeframeResult(
                timeframe=timeframe, trend="neutral", strength=0, sma_alignment="mixed", momentum="neutral"
            )

        closes = prices["close"].astype(float)

        # SMA计算
        sma5 = closes.rolling(5).mean()
        sma10 = closes.rolling(10).mean()
        sma20 = closes.rolling(20).mean() if len(closes) >= 20 else closes.rolling(len(closes)).mean()

        # 当前值
        sma5_val = float(sma5.iloc[-1]) if len(sma5) > 0 else 0
        sma10_val = float(sma10.iloc[-1]) if len(sma10) > 0 else 0
        sma20_val = float(sma20.iloc[-1]) if len(sma20) > 0 else 0
        current = float(closes.iloc[-1])

        # SMA排列判断
        if sma5_val > sma10_val > sma20_val:
            sma_alignment = "bullish"
        elif sma5_val < sma10_val < sma20_val:
            sma_alignment = "bearish"
        else:
            sma_alignment = "mixed"

        # 动量计算
        ret_5 = (closes.iloc[-1] / closes.iloc[-6] - 1) if len(closes) >= 6 else 0
        ret_10 = (closes.iloc[-1] / closes.iloc[-11] - 1) if len(closes) >= 11 else 0

        if ret_5 > 0 and ret_10 > 0:
            momentum = "positive"
        elif ret_5 < 0 and ret_10 < 0:
            momentum = "negative"
        else:
            momentum = "neutral"

        # 趋势判断
        if sma_alignment == "bullish" and momentum == "positive":
            trend = "bullish"
            strength = 0.8
        elif sma_alignment == "bearish" and momentum == "negative":
            trend = "bearish"
            strength = 0.8
        elif sma_alignment == "bullish" or momentum == "positive":
            trend = "bullish"
            strength = 0.5
        elif sma_alignment == "bearish" or momentum == "negative":
            trend = "bearish"
            strength = 0.5
        else:
            trend = "neutral"
            strength = 0.3

        return TimeframeResult(
            timeframe=timeframe,
            trend=trend,
            strength=strength,
            sma_alignment=sma_alignment,
            momentum=momentum,
        )

    def _resample_to_4h(self, daily_prices: pd.DataFrame) -> pd.DataFrame:
        """从日线模拟4小时数据。"""
        # 简化: 使用日线数据，但缩短周期
        if len(daily_prices) < 30:
            return daily_prices
        return daily_prices.tail(30)

    def _resample_to_1h(self, daily_prices: pd.DataFrame) -> pd.DataFrame:
        """从日线模拟1小时数据。"""
        # 简化: 使用日线数据，但缩短周期
        if len(daily_prices) < 60:
            return daily_prices
        return daily_prices.tail(60)

    def _calculate_resonance(
        self,
        daily: TimeframeResult,
        h4: TimeframeResult,
        h1: TimeframeResult,
    ) -> tuple[str, str, float]:
        """计算共振强度。"""
        # 统计各周期趋势
        trends = [daily.trend, h4.trend, h1.trend]
        bullish_count = trends.count("bullish")
        bearish_count = trends.count("bearish")

        # 共振判断
        if bullish_count == 3:
            resonance = "strong"
            direction = "bullish"
            adjustment = 0.2
        elif bearish_count == 3:
            resonance = "strong"
            direction = "bearish"
            adjustment = 0.2
        elif bullish_count == 2:
            resonance = "medium"
            direction = "bullish"
            adjustment = 0.1
        elif bearish_count == 2:
            resonance = "medium"
            direction = "bearish"
            adjustment = 0.1
        elif bullish_count == 1 and bearish_count == 1:
            resonance = "weak"
            direction = "neutral"
            adjustment = 0
        else:
            resonance = "none"
            direction = "neutral"
            adjustment = -0.1

        return resonance, direction, adjustment

    def get_signal_confirmation(
        self,
        signal: str,
        multi_tf_result: MultiTimeframeResult,
    ) -> tuple[str, float, list[str]]:
        """基于多周期共振确认信号。

        Args:
            signal: 原始信号 (LONG/SHORT/NEUTRAL)
            multi_tf_result: 多周期分析结果

        Returns:
            (confirmed_signal, adjusted_confidence, reasons)
        """
        reasons = []
        adjusted_conf = 0.0

        # 共振确认
        if signal == "LONG":
            if multi_tf_result.resonance_direction == "bullish":
                if multi_tf_result.resonance == "strong":
                    reasons.append("三周期多头共振")
                    adjusted_conf = 0.2
                elif multi_tf_result.resonance == "medium":
                    reasons.append("双周期多头共振")
                    adjusted_conf = 0.1
            elif multi_tf_result.resonance_direction == "bearish":
                reasons.append("周期冲突，趋势向下")
                adjusted_conf = -0.15

        elif signal == "SHORT":
            if multi_tf_result.resonance_direction == "bearish":
                if multi_tf_result.resonance == "strong":
                    reasons.append("三周期空头共振")
                    adjusted_conf = 0.2
                elif multi_tf_result.resonance == "medium":
                    reasons.append("双周期空头共振")
                    adjusted_conf = 0.1
            elif multi_tf_result.resonance_direction == "bullish":
                reasons.append("周期冲突，趋势向上")
                adjusted_conf = -0.15

        return signal, adjusted_conf, reasons
