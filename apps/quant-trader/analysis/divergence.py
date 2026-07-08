"""量价背离检测 — 识别趋势反转信号。

背离类型:
  - 顶背离: 价格新高，成交量萎缩
  - 底背离: 价格新低，成交量萎缩
  - 量价同步: 价格和成交量同向

功能:
  - 检测背离信号
  - 判断背离强度
  - 提供交易建议

用法:
    from quanttrader.analysis.divergence import DivergenceDetector
    detector = DivergenceDetector()
    result = detector.detect(prices, volumes)
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class DivergenceResult:
    """背离检测结果。"""

    divergence_type: str  # 'top', 'bottom', 'none'
    strength: float  # 0-1
    signal: str  # 'bearish', 'bullish', 'neutral'
    description: str
    price_pattern: str  # 'new_high', 'new_low', 'range'
    volume_pattern: str  # 'declining', 'rising', 'stable'


class DivergenceDetector:
    """量价背离检测器。"""

    def __init__(self, lookback: int = 20):
        self.lookback = lookback

    def detect(self, prices: pd.DataFrame) -> DivergenceResult:
        """检测量价背离。

        Args:
            prices: DataFrame with 'close' and 'volume' columns

        Returns:
            背离检测结果
        """
        if prices is None or len(prices) < self.lookback:
            return DivergenceResult(
                divergence_type="none",
                strength=0,
                signal="neutral",
                description="数据不足",
                price_pattern="range",
                volume_pattern="stable",
            )

        closes = prices["close"].astype(float)
        volumes = prices["volume"].astype(float) if "volume" in prices.columns else pd.Series(0, index=prices.index)

        # 价格模式
        price_pattern = self._analyze_price_pattern(closes)

        # 成交量模式
        volume_pattern = self._analyze_volume_pattern(volumes)

        # 背离检测
        divergence_type, strength, signal, description = self._detect_divergence(
            closes, volumes, price_pattern, volume_pattern
        )

        return DivergenceResult(
            divergence_type=divergence_type,
            strength=strength,
            signal=signal,
            description=description,
            price_pattern=price_pattern,
            volume_pattern=volume_pattern,
        )

    def _analyze_price_pattern(self, closes: pd.Series) -> str:
        """分析价格模式。"""
        recent = closes.tail(self.lookback)
        current = float(closes.iloc[-1])
        recent_high = float(recent.max())
        recent_low = float(recent.min())

        # 判断是否创新高/新低
        if current >= recent_high * 0.99:
            return "new_high"
        elif current <= recent_low * 1.01:
            return "new_low"
        else:
            return "range"

    def _analyze_volume_pattern(self, volumes: pd.Series) -> str:
        """分析成交量模式。"""
        if volumes.sum() == 0:
            return "stable"

        recent = volumes.tail(self.lookback)
        recent_5 = volumes.tail(5).mean()
        recent_20 = recent.mean()

        if recent_5 < recent_20 * 0.7:
            return "declining"
        elif recent_5 > recent_20 * 1.3:
            return "rising"
        else:
            return "stable"

    def _detect_divergence(
        self,
        closes: pd.Series,
        volumes: pd.Series,
        price_pattern: str,
        volume_pattern: str,
    ) -> tuple[str, float, str, str]:
        """检测背离。"""
        # 顶背离: 价格新高 + 成交量萎缩
        if price_pattern == "new_high" and volume_pattern == "declining":
            strength = self._calculate_divergence_strength(closes, volumes, "top")
            return "top", strength, "bearish", f"顶背离: 价格创新高但成交量萎缩(强度{strength:.1f})"

        # 底背离: 价格新低 + 成交量萎缩
        if price_pattern == "new_low" and volume_pattern == "declining":
            strength = self._calculate_divergence_strength(closes, volumes, "bottom")
            return "bottom", strength, "bullish", f"底背离: 价格创新低但成交量萎缩(强度{strength:.1f})"

        # 量价同步
        if price_pattern == "new_high" and volume_pattern == "rising":
            return "none", 0.5, "bullish", "量价同步: 价格新高放量，趋势确认"

        if price_pattern == "new_low" and volume_pattern == "rising":
            return "none", 0.5, "bearish", "量价同步: 价格新低放量，趋势确认"

        return "none", 0, "neutral", "无明显背离"

    def _calculate_divergence_strength(
        self,
        closes: pd.Series,
        volumes: pd.Series,
        divergence_type: str,
    ) -> float:
        """计算背离强度。"""
        recent_closes = closes.tail(self.lookback)
        recent_volumes = volumes.tail(self.lookback)

        # 价格变化幅度
        if divergence_type == "top":
            price_change = (float(closes.iloc[-1]) - float(recent_closes.min())) / float(recent_closes.min())
        else:
            price_change = (float(recent_closes.max()) - float(closes.iloc[-1])) / float(recent_closes.max())

        # 成交量变化幅度
        vol_recent = float(recent_volumes.tail(5).mean())
        vol_avg = float(recent_volumes.mean())
        vol_change = abs(vol_recent - vol_avg) / vol_avg if vol_avg > 0 else 0

        # 强度计算 (0-1)
        strength = min(1.0, (price_change * 10 + vol_change) / 2)
        return round(strength, 2)

    def get_signal_adjustment(self, divergence_result: DivergenceResult) -> tuple[float, list[str]]:
        """基于背离结果调整信号。

        Returns:
            (confidence_adjustment, reasons)
        """
        reasons = []
        adjustment = 0.0

        if divergence_result.divergence_type == "top":
            if divergence_result.strength > 0.7:
                adjustment = -0.2
                reasons.append("强顶背离，趋势可能反转")
            elif divergence_result.strength > 0.4:
                adjustment = -0.1
                reasons.append("中等顶背离，注意风险")

        elif divergence_result.divergence_type == "bottom":
            if divergence_result.strength > 0.7:
                adjustment = 0.15
                reasons.append("强底背离，可能反弹")
            elif divergence_result.strength > 0.4:
                adjustment = 0.05
                reasons.append("中等底背离，关注反弹")

        return adjustment, reasons
