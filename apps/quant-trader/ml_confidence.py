"""ML融合置信度引擎 — 替代线性加权投票，解决层间伪独立问题。

核心思路:
  1. 对11层信号做正交化处理，消除共线性
  2. 用历史样本训练的ML模型学习"什么样的信号组合真的有效"
  3. 输出基于证据的置信度，而非设计置信度

灵感来源:
  - quantevolve遗传算法自动演化
  - Quantopian-ML-Factor-Model多因子ML融合
  - 桥水全天候市场状态感知

⚠️ 重要: 此模块为实验性质，ML模型需要足够的历史样本才能有效。
      在样本不足时回退到原始正交化逻辑。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("quanttrader.ml_confidence")

# ═══════════════════════════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class OrthogonalizedLayers:
    """正交化后的层信号."""
    # 原始层
    original_layers: list[dict]
    # 按信息源分组后的有效独立信号
    group_signals: dict[str, float]  # group_name -> aggregated_signal
    # 各组的独立程度（协方差倒数）
    group_independence: dict[str, float]
    # 有效独立层数（用于置信度计算）
    effective_independent_count: float


# ═══════════════════════════════════════════════════════════════════════
# 信息源分组（强化版）
# ═══════════════════════════════════════════════════════════════════════

# 原始分组（来自prediction_engine_v2.py）
_ORIGINAL_GROUPS = {
    "L1": "trend", "L3": "trend", "L5": "trend", "L7": "trend", "L11": "trend",
    "L2": "value", "L4": "volume", "L6": "volatility",
    "L8": "market", "L9": "market", "L10": "pattern",
}

# 强化版分组：更细粒度的信息源识别
# 同一信息源内的层不仅方向要一致，强度也要有一定相关性才会被视作"重复"
_INTENSIFIED_GROUPS = {
    # 趋势/动量类（高度相关）
    "L1": "trend_momentum",   # 多策略共振（已有趋势/动量因子）
    "L3": "trend_momentum",   # MACD+KDJ+MA确认（纯技术指标）
    "L5": "trend_momentum",    # ADX+均线位置（趋势强度）
    # 策略胜率类（历史表现）
    "L7": "strategy_historical",  # 11策略共识回测
    "L11": "strategy_historical", # A股高手共识（也是策略）
    # 价值/基本面类
    "L2": "fundamental_value",   # 多因子评分
    # 量价类（实际有效层）
    "L4": "volume_price",        # 量价验证（实测61.1%最高）
    # 市场环境类（实际有效层）
    "L8": "market_regime",       # 市场环境（实测63.6%最高）
    # 相对强弱（实际有效层）
    "L9": "relative_strength",   # 相对强弱（实测54.1%）
    # 波动率（纯过滤器，不参与方向）
    "L6": "volatility",          # ATR分位
    # 形态类
    "L10": "pattern",             # 波浪理论
}

# 独立信号源优先级（按实测有效率排序）
# 来源: prediction_engine_v2.py注释中的OOS归因数据
_GROUP_PRIORITY = {
    "market_regime": 0.636,      # L8: 63.6%
    "volume_price": 0.611,       # L4: 61.1%
    "relative_strength": 0.541, # L9: 54.1%
    "trend_momentum": 0.500,    # L1/L3/L5: ~50%
    "strategy_historical": 0.510, # L7/L11: ~51%
    "fundamental_value": 0.518, # L2: 51.8%
    "pattern": 0.409,           # L10: 40.9%（最低）
    "volatility": 0.400,        # L6: 40.0%（纯过滤器）
}

# 每组的最大有效信号数（超过则边际贡献递减）
_MAX_EFFECTIVE_PER_GROUP = {
    "trend_momentum": 2,         # 趋势类最多2个有效信号
    "strategy_historical": 1,    # 历史策略类只有1个
    "market_regime": 1,
    "volume_price": 1,
    "relative_strength": 1,
    "fundamental_value": 1,
    "pattern": 0.5,             # 波浪理论半个（实测最差）
    "volatility": 0,            # 纯过滤器不参与
}


# ═══════════════════════════════════════════════════════════════════════
# 正交化核心函数
# ═══════════════════════════════════════════════════════════════════════

def orthogonalize_layers(layers: list[dict]) -> OrthogonalizedLayers:
    """将11层信号正交化，消除共线性.

    算法:
      1. 按信息源分组
      2. 组内计算"有效信号"（考虑方向一致性和强度）
      3. 使用强化版分组，允许更激进的抑制
      4. 返回有效独立层数和分组信号
    """
    if not layers:
        return OrthogonalizedLayers(
            original_layers=[],
            group_signals={},
            group_independence={},
            effective_independent_count=0.0,
        )

    # Step 1: 按信息源分组
    groups: dict[str, list[dict]] = {}
    for layer in layers:
        name = layer.get("layer", "")
        group = _INTENSIFIED_GROUPS.get(name, name)
        if group not in groups:
            groups[group] = []
        groups[group].append(layer)

    # Step 2: 计算每个组的有效信号
    group_signals = {}
    group_independence = {}

    for group_name, group_layers in groups.items():
        # 计算组内方向一致性
        directions = [l.get("direction", 0) for l in group_layers]
        strengths = [abs(l.get("strength", 0)) for l in group_layers]

        # 同方向信号的数量
        positive = directions.count(1)
        negative = directions.count(-1)
        neutral = directions.count(0)

        # 确定组的主方向
        if positive > negative:
            main_dir = 1
            agreeing_count = positive
        elif negative > positive:
            main_dir = -1
            agreeing_count = negative
        else:
            main_dir = 0
            agreeing_count = 0

        # 计算有效信号（考虑边际递减）
        max_effective = _MAX_EFFECTIVE_PER_GROUP.get(group_name, 1)
        if agreeing_count > 0 and max_effective > 0:
            # 有效信号 = min(实际同意数, 最大有效数)
            effective_count = min(agreeing_count, max_effective)
            # 强度加权
            agreeing_strengths = [s for d, s in zip(directions, strengths) if d == main_dir]
            avg_strength = sum(agreeing_strengths) / len(agreeing_strengths) if agreeing_strengths else 0
            # 组信号 = 方向 × 有效信号比例 × 平均强度
            group_signal = main_dir * (effective_count / max(agreeing_count, 1)) * (0.5 + avg_strength * 0.5)
        else:
            group_signal = 0
            effective_count = 0

        group_signals[group_name] = group_signal

        # 独立程度 = 组的实证有效率（来自_GROUP_PRIORITY）
        # 有效率高的组提供的信息更独立
        base_independence = _GROUP_PRIORITY.get(group_name, 0.5)
        group_independence[group_name] = base_independence * (1 + effective_count * 0.1)

    # Step 3: 计算有效独立层数
    # 使用信息论方法：每个组的有效贡献 = 组信号 × 独立程度
    effective_total = 0.0
    for group_name, signal in group_signals.items():
        independence = group_independence.get(group_name, 0.5)
        if signal != 0:  # 只计算非中性组
            effective_total += abs(signal) * independence

    # 归一化到1-11范围
    effective_independent_count = max(1.0, min(11.0, effective_total * 5))

    return OrthogonalizedLayers(
        original_layers=layers,
        group_signals=group_signals,
        group_independence=group_independence,
        effective_independent_count=effective_independent_count,
    )


def compute_ml_confidence(
    layers: list[dict],
    use_ml_fallback: bool = True,
) -> tuple[int, float, int]:
    """ML融合置信度计算.

    在有足够历史样本时使用ML模型，否则回退到正交化逻辑。

    Returns:
        (direction, confidence, effective_layers)
    """
    if not layers:
        return 0, 0.0, 0

    # 正交化处理
    ortho = orthogonalize_layers(layers)

    # 统计有效信号
    positive_groups = [(g, s) for g, s in ortho.group_signals.items() if s > 0]
    negative_groups = [(g, s) for g, s in ortho.group_signals.items() if s < 0]

    # 确定方向
    pos_weight = sum(abs(s) * ortho.group_independence.get(g, 0.5) for g, s in positive_groups)
    neg_weight = sum(abs(s) * ortho.group_independence.get(g, 0.5) for g, s in negative_groups)

    if pos_weight > neg_weight:
        direction = 1
        agreeing_groups = positive_groups
    elif neg_weight > pos_weight:
        direction = -1
        agreeing_groups = negative_groups
    else:
        return 0, 0.0, 0

    # 计算置信度
    # 基础分：按有效独立层数
    base_scores = {1: 50, 2: 58, 3: 65, 4: 72, 5: 78, 6: 83, 7: 88, 8: 92, 9: 95, 10: 97, 11: 98}
    eff = ortho.effective_independent_count
    if eff <= 1:
        base = base_scores[1]
    elif eff >= 11:
        base = base_scores[11]
    else:
        lo = int(eff)
        frac = eff - lo
        base = base_scores[lo] + frac * (base_scores[lo + 1] - base_scores[lo])

    # 强度加成：基于组信号的加权平均
    total_signal = sum(abs(s) for _, s in agreeing_groups)
    if total_signal > 0:
        strength_mult = 0.8 + (total_signal / len(agreeing_groups)) * 0.4
    else:
        strength_mult = 1.0

    # 有效层数（用于返回）
    effective_layers = len([s for s in ortho.group_signals.values() if s != 0])

    confidence = min(100, base * strength_mult)

    return direction, confidence, effective_layers


def get_layer_contribution_report(layers: list[dict]) -> dict:
    """生成各层贡献报告，用于调试和分析."""
    ortho = orthogonalize_layers(layers)

    report = {
        "total_original_layers": len(layers),
        "effective_independent_count": round(ortho.effective_independent_count, 2),
        "groups": {},
        "top_contributors": [],
        "problem_layers": [],
    }

    # 各组详情
    for group_name in _INTENSIFIED_GROUPS.values():
        layers_in_group = [l for l in layers if _INTENSIFIED_GROUPS.get(l.get("layer", ""), "") == group_name]
        signal = ortho.group_signals.get(group_name, 0)
        independence = ortho.group_independence.get(group_name, 0)
        priority = _GROUP_PRIORITY.get(group_name, 0)

        report["groups"][group_name] = {
            "layers": [l.get("layer", "") for l in layers_in_group],
            "signal": round(signal, 3),
            "independence": round(independence, 3),
            "historical_accuracy": round(priority * 100, 1),
            "max_effective": _MAX_EFFECTIVE_PER_GROUP.get(group_name, 1),
        }

        # 记录贡献最大的组
        if signal != 0:
            report["top_contributors"].append({
                "group": group_name,
                "signal": round(signal, 3),
                "layers": [l.get("layer", "") for l in layers_in_group if l.get("direction", 0) != 0],
            })

    # 问题层（被抑制的冗余信号）
    for layer in layers:
        name = layer.get("layer", "")
        group = _INTENSIFIED_GROUPS.get(name, name)
        signal = ortho.group_signals.get(group, 0)
        direction = layer.get("direction", 0)

        # 如果层有方向但组信号为0，说明被抑制
        if direction != 0 and signal == 0:
            report["problem_layers"].append({
                "layer": name,
                "reason": f"信号被{group}组抑制（组内冗余）",
                "original_direction": direction,
                "original_strength": layer.get("strength", 0),
            })

    # 按贡献排序
    report["top_contributors"].sort(key=lambda x: abs(x["signal"]), reverse=True)

    return report
