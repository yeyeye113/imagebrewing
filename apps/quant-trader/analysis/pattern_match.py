"""历史案例匹配 — 查找相似形态预测未来走势。

功能:
  - 提取价格形态特征
  - 查找历史相似案例
  - 统计后续走势概率

用法:
    from quanttrader.analysis.pattern_match import PatternMatcher
    matcher = PatternMatcher()
    result = matcher.find_similar(prices)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class SimilarCase:
    """相似案例。"""

    date: str
    similarity: float
    future_return: float
    future_direction: str  # 'up', 'down', 'flat'


@dataclass
class PatternMatchResult:
    """形态匹配结果。"""

    similar_cases: list[SimilarCase]
    avg_return: float
    win_rate: float
    predicted_direction: str
    confidence: float
    description: str


class PatternMatcher:
    """历史形态匹配器。"""

    def __init__(self, pattern_length: int = 20, min_similarity: float = 0.7):
        self.pattern_length = pattern_length
        self.min_similarity = min_similarity

    def find_similar(self, prices: pd.DataFrame, symbol: str = "") -> PatternMatchResult:
        """查找相似形态。

        Args:
            prices: 历史价格数据
            symbol: 品种代码

        Returns:
            形态匹配结果
        """
        if prices is None or len(prices) < self.pattern_length * 2:
            return PatternMatchResult(
                similar_cases=[],
                avg_return=0,
                win_rate=0,
                predicted_direction="neutral",
                confidence=0,
                description="数据不足",
            )

        closes = prices["close"].astype(float).values

        # 提取当前形态
        current_pattern = closes[-self.pattern_length :]
        current_features = self._extract_features(current_pattern)

        # 查找相似案例
        similar_cases = []
        for i in range(self.pattern_length, len(closes) - self.pattern_length):
            past_pattern = closes[i - self.pattern_length : i]
            past_features = self._extract_features(past_pattern)

            # 计算相似度
            similarity = self._calculate_similarity(current_features, past_features)

            if similarity >= self.min_similarity:
                # 计算后续走势
                future_return = closes[i + self.pattern_length] / closes[i] - 1
                future_direction = "up" if future_return > 0.01 else ("down" if future_return < -0.01 else "flat")

                similar_cases.append(
                    SimilarCase(
                        date=str(prices.index[i]),
                        similarity=similarity,
                        future_return=future_return,
                        future_direction=future_direction,
                    )
                )

        # 统计结果
        if not similar_cases:
            return PatternMatchResult(
                similar_cases=[],
                avg_return=0,
                win_rate=0,
                predicted_direction="neutral",
                confidence=0,
                description="未找到相似案例",
            )

        avg_return = np.mean([c.future_return for c in similar_cases])
        win_rate = sum(1 for c in similar_cases if c.future_return > 0) / len(similar_cases)
        predicted_direction = "bullish" if avg_return > 0.01 else ("bearish" if avg_return < -0.01 else "neutral")
        confidence = min(1.0, len(similar_cases) / 10)  # 案例越多置信度越高

        return PatternMatchResult(
            similar_cases=sorted(similar_cases, key=lambda x: x.similarity, reverse=True)[:5],
            avg_return=avg_return,
            win_rate=win_rate,
            predicted_direction=predicted_direction,
            confidence=confidence,
            description=f"找到{len(similar_cases)}个相似案例，平均收益{avg_return * 100:.1f}%，胜率{win_rate * 100:.0f}%",
        )

    def _extract_features(self, pattern: np.ndarray) -> dict[str, float]:
        """提取形态特征。"""
        if len(pattern) < 5:
            return {}

        # 归一化
        normalized = (pattern - pattern.mean()) / (pattern.std() if pattern.std() > 0 else 1)

        # 特征提取
        features = {
            "return": (pattern[-1] / pattern[0] - 1),
            "volatility": pattern.std() / pattern.mean() if pattern.mean() > 0 else 0,
            "trend": np.polyfit(range(len(pattern)), normalized, 1)[0],
            "max_drawdown": (pattern.max() - pattern.min()) / pattern.max() if pattern.max() > 0 else 0,
            "skew": float(pd.Series(normalized).skew()),
            "kurtosis": float(pd.Series(normalized).kurtosis()),
        }

        return features

    def _calculate_similarity(self, features1: dict[str, float], features2: dict[str, float]) -> float:
        """计算特征相似度。"""
        if not features1 or not features2:
            return 0

        # 计算各特征的相似度
        similarities = []
        for key in features1:
            if key in features2:
                # 归一化差异
                diff = abs(features1[key] - features2[key])
                max_val = max(abs(features1[key]), abs(features2[key]), 0.001)
                similarity = 1 - min(1, diff / max_val)
                similarities.append(similarity)

        return np.mean(similarities) if similarities else 0

    def get_signal_adjustment(self, match_result: PatternMatchResult) -> tuple[float, list[str]]:
        """基于形态匹配调整信号。

        Returns:
            (confidence_adjustment, reasons)
        """
        reasons = []
        adjustment = 0.0

        if match_result.confidence > 0.5:
            if match_result.predicted_direction == "bullish":
                if match_result.win_rate > 0.6:
                    adjustment = 0.15
                    reasons.append(f"历史形态看涨(胜率{match_result.win_rate * 100:.0f}%)")
                else:
                    adjustment = 0.05
                    reasons.append("历史形态偏多")

            elif match_result.predicted_direction == "bearish":
                if match_result.win_rate < 0.4:
                    adjustment = -0.15
                    reasons.append(f"历史形态看跌(胜率{match_result.win_rate * 100:.0f}%)")
                else:
                    adjustment = -0.05
                    reasons.append("历史形态偏空")

        return adjustment, reasons
