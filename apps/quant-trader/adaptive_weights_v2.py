"""自适应权重引擎 — 基于进化算法的动态层权重调整。

核心思路:
  1. 记录每次预测的实际表现
  2. 用遗传算法思想动态调整层权重
  3. 表现好的层权重增加，表现差的减少
  4. 支持多市场状态下的差异化权重

灵感来源: quantevolve遗传算法自动演化策略

⚠️ 重要: 此模块需要持续运行收集预测结果，才能逐步优化权重。
      初期权重来自OOS实测数据（prediction_engine_v2.py注释）。
"""
from __future__ import annotations

import logging
import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

logger = logging.getLogger("quanttrader.adaptive_weights_v2")

# ═══════════════════════════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class LayerPerformance:
    """单层历史表现."""
    layer_name: str
    correct: int = 0
    total: int = 0
    avg_return_when_correct: float = 0.0
    avg_return_when_wrong: float = 0.0
    last_updated: float = field(default_factory=time.time)


@dataclass
class AdaptiveWeights:
    """自适应权重状态."""
    weights: dict[str, float]  # 层名 -> 权重
    market_regime: str = "unknown"  # bull/bear/volatile/sideways
    confidence: float = 0.5  # 权重可靠性
    sample_count: int = 0  # 累计样本数
    generation: int = 0  # 遗传代数


# ═══════════════════════════════════════════════════════════════════════
# 默认权重（来自prediction_engine_v2.py的OOS归因）
# ═══════════════════════════════════════════════════════════════════════

DEFAULT_WEIGHTS = {
    "L1": 0.18,  # 多策略共振 (50.3%)
    "L2": 0.14,  # 多因子评分 (51.8%)
    "L3": 0.14,  # 技术指标确认 (50.4%)
    "L4": 0.12,  # 量价验证 (61.1% ↑ 有效)
    "L5": 0.05,  # 趋势强度 (46.5% ↓)
    "L6": 0.02,  # 波动率环境 (40.0% ↓ 纯过滤器)
    "L7": 0.04,  # 历史胜率 (49.1%)
    "L8": 0.10,  # 市场环境 (63.6% ↑ 有效)
    "L9": 0.12,  # 相对强弱 (54.1% ↑ 有效)
    "L10": 0.03, # 波浪理论 (40.9% ↓ 最差)
    "L11": 0.06, # A股高手共识 (52.6%)
}

# 历史准确率（用于初始化）
HISTORICAL_ACCURACY = {
    "L1": 0.503,
    "L2": 0.518,
    "L3": 0.504,
    "L4": 0.611,  # 最高
    "L5": 0.465,
    "L6": 0.400,  # 纯过滤器
    "L7": 0.491,
    "L8": 0.636,  # 次高
    "L9": 0.541,
    "L10": 0.409,  # 最低
    "L11": 0.526,
}


# ═══════════════════════════════════════════════════════════════════════
# 市场状态权重（桥水全天候思想）
# ═══════════════════════════════════════════════════════════════════════

REGIME_WEIGHTS = {
    "bull": {
        "L1": 0.20, "L2": 0.12, "L3": 0.16, "L4": 0.12,
        "L5": 0.06, "L6": 0.02, "L7": 0.04, "L8": 0.08,
        "L9": 0.10, "L10": 0.02, "L11": 0.08,
    },
    "bear": {
        "L1": 0.14, "L2": 0.16, "L3": 0.12, "L4": 0.12,
        "L5": 0.04, "L6": 0.04, "L7": 0.06, "L8": 0.14,
        "L9": 0.10, "L10": 0.02, "L11": 0.06,
    },
    "volatile": {
        "L1": 0.12, "L2": 0.14, "L3": 0.10, "L4": 0.14,
        "L5": 0.04, "L6": 0.06, "L7": 0.08, "L8": 0.14,
        "L9": 0.10, "L10": 0.02, "L11": 0.06,
    },
    "sideways": {
        "L1": 0.16, "L2": 0.14, "L3": 0.16, "L4": 0.12,
        "L5": 0.06, "L6": 0.04, "L7": 0.04, "L8": 0.10,
        "L9": 0.10, "L10": 0.04, "L11": 0.04,
    },
}


# ═══════════════════════════════════════════════════════════════════════
# 权重调整引擎
# ═══════════════════════════════════════════════════════════════════════

class AdaptiveWeightEngine:
    """自适应权重引擎.

    使用遗传算法思想动态调整层权重:
    1. 变异: 随机调整部分权重
    2. 选择: 表现好的层权重增加
    3. 交叉: 借鉴历史有效权重
    """

    def __init__(
        self,
        initial_weights: Optional[dict[str, float]] = None,
        max_history: int = 1000,
        mutation_rate: float = 0.1,
        learning_rate: float = 0.05,
    ):
        self.weights = initial_weights or DEFAULT_WEIGHTS.copy()
        self.max_history = max_history
        self.mutation_rate = mutation_rate
        self.learning_rate = learning_rate

        # 层表现历史
        self.layer_history: dict[str, deque] = {
            layer: deque(maxlen=max_history)
            for layer in DEFAULT_WEIGHTS.keys()
        }

        # 市场状态
        self.current_regime = "unknown"

        # 代数
        self.generation = 0

        # 权重可信度
        self.confidence = 0.5

    def record_prediction(
        self,
        layer_predictions: dict[str, int],  # layer -> direction prediction
        actual_outcome: int,  # 1 = price went up, -1 = went down
        returns: float,  # actual return percentage
    ) -> None:
        """记录一次预测结果，用于后续权重调整."""
        for layer, predicted_dir in layer_predictions.items():
            if layer not in self.layer_history:
                continue

            # 记录预测是否正确
            correct = 1 if (predicted_dir * actual_outcome > 0) else 0
            self.layer_history[layer].append({
                "correct": correct,
                "returns": returns,
                "timestamp": time.time(),
            })

    def get_adaptive_weights(self, regime: Optional[str] = None) -> dict[str, float]:
        """获取当前自适应权重.

        权重 = 历史权重 × 市场状态调整 × 近期表现调整
        """
        # 更新市场状态
        if regime:
            self.current_regime = regime

        # 从历史表现计算调整因子
        performance_factors = self._compute_performance_factors()

        # 合并权重
        regime_weights = REGIME_WEIGHTS.get(self.current_regime, DEFAULT_WEIGHTS)

        adaptive_weights = {}
        total = 0.0

        for layer in DEFAULT_WEIGHTS.keys():
            base = regime_weights.get(layer, DEFAULT_WEIGHTS[layer])
            perf_adj = performance_factors.get(layer, 1.0)

            # 调整因子范围: 0.7 ~ 1.3
            clamped_adj = max(0.7, min(1.3, perf_adj))

            adaptive_weights[layer] = base * clamped_adj
            total += adaptive_weights[layer]

        # 归一化
        if total > 0:
            adaptive_weights = {
                k: v / total for k, v in adaptive_weights.items()
            }

        self.weights = adaptive_weights
        return adaptive_weights

    def _compute_performance_factors(self) -> dict[str, float]:
        """从历史表现计算调整因子."""
        factors = {}

        for layer, history in self.layer_history.items():
            if len(history) < 10:
                # 样本不足，使用历史准确率
                factors[layer] = 1.0 + (HISTORICAL_ACCURACY.get(layer, 0.5) - 0.5)
                continue

            # 计算近期准确率（最近50条）
            recent = list(history)[-50:]
            correct_rate = sum(h["correct"] for h in recent) / len(recent)

            # 计算盈亏比
            correct_returns = [h["returns"] for h in recent if h["correct"] == 1]
            wrong_returns = [h["returns"] for h in recent if h["correct"] == 0]

            avg_correct = np.mean(correct_returns) if correct_returns else 0
            avg_wrong = np.mean(wrong_returns) if wrong_returns else 0

            # 盈亏比 > 1 表示层有效
            profit_ratio = abs(avg_correct / avg_wrong) if avg_wrong != 0 else 1.0

            # 综合表现因子
            # 准确率权重 0.6，盈亏比权重 0.4
            performance = 0.6 * correct_rate + 0.4 * min(profit_ratio, 2) / 2

            # 调整因子：表现好的层权重增加
            # 以0.5为基准，范围0.7~1.3
            factors[layer] = 0.7 + (performance - 0.5) * 1.2

        return factors

    def evolve(self) -> dict[str, float]:
        """执行遗传算法的一代进化."""
        self.generation += 1

        # 1. 评估当前权重表现
        performance = self._evaluate_population()

        # 2. 选择：保留表现好的层权重
        best_layers = [p["layer"] for p in performance[:5]]

        # 3. 变异：随机调整部分权重
        new_weights = self.weights.copy()
        for layer in DEFAULT_WEIGHTS.keys():
            if layer in best_layers:
                # 表现好的层，小幅变异
                mutation = np.random.normal(0, self.mutation_rate * 0.3)
            else:
                # 表现差的层，较大变异
                mutation = np.random.normal(0, self.mutation_rate * 0.6)

            new_weights[layer] *= (1 + mutation)

        # 4. 交叉：借鉴最优层的历史权重
        for i, layer in enumerate(DEFAULT_WEIGHTS.keys()):
            if np.random.random() < 0.2 and best_layers:
                # 20%概率从最优层借鉴
                best_layer = best_layers[np.random.randint(len(best_layers))]
                # 借鉴比例为代数的倒数（越晚越少借鉴）
                blend = min(0.2, 1.0 / max(1, self.generation))
                new_weights[layer] = (
                    (1 - blend) * new_weights[layer] +
                    blend * DEFAULT_WEIGHTS.get(best_layer, 0.1)
                )

        # 5. 归一化
        total = sum(new_weights.values())
        if total > 0:
            new_weights = {k: v / total for k, v in new_weights.items()}

        self.weights = new_weights
        return new_weights

    def _evaluate_population(self) -> list[dict]:
        """评估各层的表现."""
        results = []

        for layer, history in self.layer_history.items():
            if len(history) < 5:
                score = 0.5
            else:
                recent = list(history)[-20:]
                score = sum(h["correct"] for h in recent) / len(recent)

            results.append({
                "layer": layer,
                "score": score,
                "samples": len(history),
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    def get_state(self) -> AdaptiveWeights:
        """获取当前状态."""
        return AdaptiveWeights(
            weights=self.weights,
            market_regime=self.current_regime,
            confidence=self.confidence,
            sample_count=sum(len(h) for h in self.layer_history.values()),
            generation=self.generation,
        )

    def load_state(self, state: AdaptiveWeights) -> None:
        """加载状态."""
        self.weights = state.weights
        self.current_regime = state.market_regime
        self.confidence = state.confidence
        self.generation = state.generation


# ═══════════════════════════════════════════════════════════════════════
# 全局单例
# ═══════════════════════════════════════════════════════════════════════

_engine: Optional[AdaptiveWeightEngine] = None


def get_engine() -> AdaptiveWeightEngine:
    """获取全局引擎实例."""
    global _engine
    if _engine is None:
        _engine = AdaptiveWeightEngine()
    return _engine


def get_adaptive_weights(regime: Optional[str] = None) -> dict[str, float]:
    """便捷函数：获取自适应权重."""
    engine = get_engine()
    return engine.get_adaptive_weights(regime=regime)


def record_prediction_result(
    layer_predictions: dict[str, int],
    actual_outcome: int,
    returns: float,
) -> None:
    """便捷函数：记录预测结果."""
    engine = get_engine()
    engine.record_prediction(layer_predictions, actual_outcome, returns)


def evolve_weights() -> dict[str, float]:
    """便捷函数：执行一代进化."""
    engine = get_engine()
    return engine.evolve()
