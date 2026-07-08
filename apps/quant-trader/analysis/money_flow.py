"""资金流向分析 — 监控主力资金动向。

数据源:
  - 成交量分析
  - 大单统计
  - 持仓变化

功能:
  - 资金流入/流出判断
  - 主力动向分析
  - 信号确认

用法:
    from quanttrader.analysis.money_flow import MoneyFlowAnalyzer
    analyzer = MoneyFlowAnalyzer()
    result = analyzer.analyze(prices)
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class MoneyFlowResult:
    """资金流向结果。"""

    flow_direction: str  # 'inflow', 'outflow', 'neutral'
    flow_strength: float  # 0-1
    volume_trend: str  # 'rising', 'falling', 'stable'
    signal: str  # 'bullish', 'bearish', 'neutral'
    description: str


class MoneyFlowAnalyzer:
    """资金流向分析器。"""

    def __init__(self, lookback: int = 20):
        self.lookback = lookback

    def analyze(self, prices: pd.DataFrame) -> MoneyFlowResult:
        """分析资金流向。

        Args:
            prices: DataFrame with 'close', 'volume' columns

        Returns:
            资金流向结果
        """
        if prices is None or len(prices) < self.lookback:
            return MoneyFlowResult(
                flow_direction="neutral",
                flow_strength=0,
                volume_trend="stable",
                signal="neutral",
                description="数据不足",
            )

        closes = prices["close"].astype(float)
        volumes = prices["volume"].astype(float) if "volume" in prices.columns else pd.Series(0, index=prices.index)

        # 成交量趋势
        volume_trend = self._analyze_volume_trend(volumes)

        # 资金流向
        flow_direction, flow_strength = self._analyze_money_flow(closes, volumes)

        # 信号判断
        signal, description = self._generate_signal(flow_direction, flow_strength, volume_trend)

        return MoneyFlowResult(
            flow_direction=flow_direction,
            flow_strength=flow_strength,
            volume_trend=volume_trend,
            signal=signal,
            description=description,
        )

    def _analyze_volume_trend(self, volumes: pd.Series) -> str:
        """分析成交量趋势。"""
        if volumes.sum() == 0:
            return "stable"

        recent_5 = volumes.tail(5).mean()
        recent_20 = volumes.tail(self.lookback).mean()

        if recent_5 > recent_20 * 1.3:
            return "rising"
        elif recent_5 < recent_20 * 0.7:
            return "falling"
        else:
            return "stable"

    def _analyze_money_flow(self, closes: pd.Series, volumes: pd.Series) -> tuple[str, float]:
        """分析资金流向。"""
        if volumes.sum() == 0:
            return "neutral", 0

        # 计算资金流向指标
        # 价格上涨时的成交量 vs 价格下跌时的成交量
        price_change = closes.diff()
        up_volume = volumes[price_change > 0].sum()
        down_volume = volumes[price_change < 0].sum()
        total_volume = up_volume + down_volume

        if total_volume == 0:
            return "neutral", 0

        # 资金流入比例
        inflow_ratio = up_volume / total_volume

        # 判断流向
        if inflow_ratio > 0.6:
            return "inflow", inflow_ratio
        elif inflow_ratio < 0.4:
            return "outflow", 1 - inflow_ratio
        else:
            return "neutral", 0.5

    def _generate_signal(
        self,
        flow_direction: str,
        flow_strength: float,
        volume_trend: str,
    ) -> tuple[str, str]:
        """生成信号。"""
        # 资金流入 + 成交量放大
        if flow_direction == "inflow" and volume_trend == "rising":
            return "bullish", f"资金流入(强度{flow_strength:.1f})且成交量放大"

        # 资金流出 + 成交量放大
        if flow_direction == "outflow" and volume_trend == "rising":
            return "bearish", f"资金流出(强度{flow_strength:.1f})且成交量放大"

        # 资金流入 + 成交量萎缩
        if flow_direction == "inflow" and volume_trend == "falling":
            return "neutral", "资金流入但成交量萎缩，趋势可能减弱"

        # 资金流出 + 成交量萎缩
        if flow_direction == "outflow" and volume_trend == "falling":
            return "neutral", "资金流出但成交量萎缩，下跌动能减弱"

        return "neutral", "资金流向不明确"

    def get_signal_adjustment(self, flow_result: MoneyFlowResult) -> tuple[float, list[str]]:
        """基于资金流向调整信号。

        Returns:
            (confidence_adjustment, reasons)
        """
        reasons = []
        adjustment = 0.0

        if flow_result.signal == "bullish":
            if flow_result.flow_strength > 0.7:
                adjustment = 0.15
                reasons.append("强资金流入")
            elif flow_result.flow_strength > 0.5:
                adjustment = 0.05
                reasons.append("资金流入")

        elif flow_result.signal == "bearish":
            if flow_result.flow_strength > 0.7:
                adjustment = -0.15
                reasons.append("强资金流出")
            elif flow_result.flow_strength > 0.5:
                adjustment = -0.05
                reasons.append("资金流出")

        return adjustment, reasons
