"""智能权重调节系统 — 根据市场环境和近期表现动态调整权重.

核心原理:
  1. 跟踪每个指标的近期准确率
  2. 根据市场环境调整权重
  3. 使用滑动窗口自适应学习
  4. 避免过拟合，保持稳健性
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from .log import get_logger

logger = get_logger("adaptive_weights")


@dataclass
class IndicatorPerformance:
    """单个指标的近期表现."""
    name: str
    total_signals: int = 0
    correct_signals: int = 0
    accuracy: float = 0.5
    recent_accuracy: float = 0.5  # 近期准确率
    weight: float = 1.0


@dataclass
class MarketRegimeWeights:
    """不同市场环境下的权重配置."""
    bull: dict[str, float] = field(default_factory=dict)
    bear: dict[str, float] = field(default_factory=dict)
    sideways: dict[str, float] = field(default_factory=dict)
    volatile: dict[str, float] = field(default_factory=dict)


class AdaptiveWeightManager:
    """智能权重管理器.

    功能:
      1. 跟踪每个指标的近期表现
      2. 根据市场环境动态调整权重
      3. 使用指数衰减加权近期表现
      4. 自动学习最优权重
    """

    def __init__(
        self,
        lookback_window: int = 100,
        decay_factor: float = 0.95,
        min_weight: float = 0.05,
        max_weight: float = 0.30,
        learning_rate: float = 0.01,
    ):
        """
        Args:
            lookback_window: 回看窗口大小
            decay_factor: 指数衰减因子 (越接近 1 越重视近期)
            min_weight: 最小权重
            max_weight: 最大权重
            learning_rate: 学习率
        """
        self.lookback_window = lookback_window
        self.decay_factor = decay_factor
        self.min_weight = min_weight
        self.max_weight = max_weight
        self.learning_rate = learning_rate

        # 指标表现跟踪
        self.indicator_performance: dict[str, IndicatorPerformance] = {}

        # 历史记录
        self.history: list[dict] = []

        # 市场环境权重
        self.regime_weights = MarketRegimeWeights()

        # 初始化默认权重
        self._init_default_weights()

    def _init_default_weights(self):
        """初始化默认权重."""
        default_weights = {
            "L1": 0.15,  # 多策略共振
            "L2": 0.12,  # 多因子评分
            "L3": 0.18,  # 技术指标确认
            "L4": 0.10,  # 量价验证
            "L5": 0.12,  # RSI 超卖/超买
            "L6": 0.08,  # 波动率环境
            "L7": 0.05,  # 历史胜率
            "L8": 0.10,  # 市场环境
            "L9": 0.10,  # 相对强弱
        }

        for name, weight in default_weights.items():
            self.indicator_performance[name] = IndicatorPerformance(
                name=name,
                weight=weight,
            )

    def update_performance(
        self,
        indicator_name: str,
        predicted_direction: int,
        actual_direction: int,
    ):
        """更新指标表现.

        Args:
            indicator_name: 指标名称 (L1-L9)
            predicted_direction: 预测方向 (+1 看多, -1 看空)
            actual_direction: 实际方向
        """
        if indicator_name not in self.indicator_performance:
            self.indicator_performance[indicator_name] = IndicatorPerformance(
                name=indicator_name,
            )

        perf = self.indicator_performance[indicator_name]
        perf.total_signals += 1

        # 判断是否正确
        correct = (predicted_direction == actual_direction)
        if correct:
            perf.correct_signals += 1

        # 计算准确率
        perf.accuracy = perf.correct_signals / perf.total_signals

        # 计算近期准确率 (指数衰减加权)
        self.history.append({
            "indicator": indicator_name,
            "correct": correct,
            "timestamp": time.time(),
        })

        # 保持历史记录在窗口内
        if len(self.history) > self.lookback_window * 10:
            self.history = self.history[-self.lookback_window * 10:]

        # 更新近期准确率
        self._update_recent_accuracy(indicator_name)

    def _update_recent_accuracy(self, indicator_name: str):
        """更新近期准确率 (指数衰减加权)."""
        # 获取该指标的历史记录
        indicator_history = [
            h for h in self.history
            if h["indicator"] == indicator_name
        ]

        if not indicator_history:
            return

        # 取最近的记录
        recent = indicator_history[-self.lookback_window:]

        # 指数衰减加权
        weighted_correct = 0.0
        total_weight = 0.0
        weight = 1.0

        for record in reversed(recent):
            if record["correct"]:
                weighted_correct += weight
            total_weight += weight
            weight *= self.decay_factor

        if total_weight > 0:
            self.indicator_performance[indicator_name].recent_accuracy = (
                weighted_correct / total_weight
            )

    def get_adaptive_weights(
        self,
        market_regime: str = "sideways",
    ) -> dict[str, float]:
        """获取自适应权重.

        Args:
            market_regime: 市场环境 (bull/bear/sideways/volatile)

        Returns:
            dict: {indicator_name: weight}
        """
        weights = {}

        for name, perf in self.indicator_performance.items():
            # 基础权重
            base_weight = perf.weight

            # 根据近期准确率调整
            accuracy_factor = self._calculate_accuracy_factor(perf.recent_accuracy)

            # 根据市场环境调整
            regime_factor = self._get_regime_factor(name, market_regime)

            # 计算最终权重
            final_weight = base_weight * accuracy_factor * regime_factor

            # 限制范围
            final_weight = max(self.min_weight, min(self.max_weight, final_weight))

            weights[name] = final_weight

        # 归一化
        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}

        return weights

    def _calculate_accuracy_factor(self, accuracy: float) -> float:
        """根据准确率计算调整因子.

        准确率 > 0.6: 增加权重
        准确率 < 0.4: 减少权重
        """
        if accuracy >= 0.7:
            return 1.5  # 高准确率，大幅增加权重
        elif accuracy >= 0.6:
            return 1.2  # 较高准确率，增加权重
        elif accuracy >= 0.5:
            return 1.0  # 平均准确率，保持权重
        elif accuracy >= 0.4:
            return 0.8  # 较低准确率，减少权重
        else:
            return 0.5  # 低准确率，大幅减少权重

    def _get_regime_factor(self, indicator_name: str, market_regime: str) -> float:
        """根据市场环境获取调整因子.

        不同指标在不同市场环境下表现不同:
          - 趋势指标 (L3, L5) 在牛市表现更好
          - 反转指标 (L4, L6) 在熊市表现更好
          - 波动率指标 (L6) 在高波动时更重要
        """
        # 指标类型分类
        trend_indicators = ["L3", "L5", "L9"]  # 趋势类
        reversal_indicators = ["L4", "L6"]  # 反转类
        momentum_indicators = ["L1", "L2"]  # 动量类
        volatility_indicators = ["L6", "L7"]  # 波动率类

        if market_regime == "bull":
            # 牛市: 趋势指标更重要
            if indicator_name in trend_indicators:
                return 1.3
            elif indicator_name in reversal_indicators:
                return 0.7
            else:
                return 1.0

        elif market_regime == "bear":
            # 熊市: 反转指标更重要
            if indicator_name in reversal_indicators:
                return 1.3
            elif indicator_name in trend_indicators:
                return 0.7
            else:
                return 1.0

        elif market_regime == "volatile":
            # 高波动: 波动率指标更重要
            if indicator_name in volatility_indicators:
                return 1.5
            else:
                return 0.8

        else:
            # 震荡市: 均衡权重
            return 1.0

    def update_regime_weights(self, market_regime: str, weights: dict[str, float]):
        """更新市场环境权重."""
        if market_regime == "bull":
            self.regime_weights.bull = weights.copy()
        elif market_regime == "bear":
            self.regime_weights.bear = weights.copy()
        elif market_regime == "sideways":
            self.regime_weights.sideways = weights.copy()
        elif market_regime == "volatile":
            self.regime_weights.volatile = weights.copy()

    def save_state(self, path: str):
        """保存状态到文件."""
        state = {
            "indicator_performance": {
                name: {
                    "total_signals": perf.total_signals,
                    "correct_signals": perf.correct_signals,
                    "accuracy": perf.accuracy,
                    "recent_accuracy": perf.recent_accuracy,
                    "weight": perf.weight,
                }
                for name, perf in self.indicator_performance.items()
            },
            "history": self.history[-1000:],  # 只保存最近 1000 条
            "regime_weights": {
                "bull": self.regime_weights.bull,
                "bear": self.regime_weights.bear,
                "sideways": self.regime_weights.sideways,
                "volatile": self.regime_weights.volatile,
            },
        }

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

        logger.info("权重状态已保存到 %s", path)

    def load_state(self, path: str):
        """从文件加载状态."""
        try:
            with open(path, encoding='utf-8') as f:
                state = json.load(f)

            # 恢复指标表现
            for name, data in state.get("indicator_performance", {}).items():
                self.indicator_performance[name] = IndicatorPerformance(
                    name=name,
                    total_signals=data.get("total_signals", 0),
                    correct_signals=data.get("correct_signals", 0),
                    accuracy=data.get("accuracy", 0.5),
                    recent_accuracy=data.get("recent_accuracy", 0.5),
                    weight=data.get("weight", 1.0),
                )

            # 恢复历史记录
            self.history = state.get("history", [])

            # 恢复市场环境权重
            regime_data = state.get("regime_weights", {})
            self.regime_weights.bull = regime_data.get("bull", {})
            self.regime_weights.bear = regime_data.get("bear", {})
            self.regime_weights.sideways = regime_data.get("sideways", {})
            self.regime_weights.volatile = regime_data.get("volatile", {})

            logger.info("权重状态已从 %s 加载", path)
        except Exception as e:
            logger.warning("加载权重状态失败: %s", e)

    def get_performance_summary(self) -> dict:
        """获取性能摘要."""
        summary = {}
        for name, perf in self.indicator_performance.items():
            summary[name] = {
                "total_signals": perf.total_signals,
                "accuracy": round(perf.accuracy, 3),
                "recent_accuracy": round(perf.recent_accuracy, 3),
                "weight": round(perf.weight, 3),
            }
        return summary


# 全局实例
_adaptive_manager: AdaptiveWeightManager | None = None


def get_adaptive_manager() -> AdaptiveWeightManager:
    """获取全局自适应权重管理器."""
    global _adaptive_manager
    if _adaptive_manager is None:
        _adaptive_manager = AdaptiveWeightManager()
    return _adaptive_manager


def get_adaptive_weights(market_regime: str = "sideways") -> dict[str, float]:
    """获取自适应权重."""
    manager = get_adaptive_manager()
    return manager.get_adaptive_weights(market_regime)


def update_indicator_performance(
    indicator_name: str,
    predicted_direction: int,
    actual_direction: int,
):
    """更新指标表现."""
    manager = get_adaptive_manager()
    manager.update_performance(indicator_name, predicted_direction, actual_direction)
