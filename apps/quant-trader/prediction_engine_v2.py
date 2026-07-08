"""高精度预测引擎 v3 — 11 层信号 + ML正交化置信度 + 自适应权重.

核心思路: 不是提高每个预测的准确率，而是提高筛选门槛，
只输出最高置信度的信号。宁可少说，说则必中。

v3 改进 (2026-07-08):
  1. 引入 ml_confidence.py 正交化模块，消除层间伪独立
  2. 引入 adaptive_weights_v2.py 遗传算法自适应权重
  3. 置信度计算从线性加权升级为信息源分组正交化

11 层独立信号源:
  L1: 多策略共振 (11 策略投票)
  L2: 多因子评分 (5 因子极端值)
  L3: 技术指标确认 (MACD+KDJ+MA 三者同向)
  L4: 量价验证 (放量突破/缩量回调) — 实证有效 61.1%
  L5: 趋势强度 (ADX + 均线位置)
  L6: 波动率环境 (ATR 分位, 纯过滤器)
  L7: 历史胜率校验 (11 策略共识滚动回测)
  L8: 市场环境 (熊市/高波动抑制) — 实证有效 63.6%
  L9: 相对强弱 (跑赢大盘加分) — 实证有效 54.1%
  L10: 波浪理论 (Elliott Wave) — 实证最差 40.9%
  L11: A股高手策略共识

置信度 ≥ 85% 且 ≥ 6 层同方向才输出 (precision over recall).

v3 核心改进:
  - 层间信号正交化 (ml_confidence.py): 按信息源分组，组内信号次可加(sqrt)
  - 自适应权重 (adaptive_weights_v2.py): 基于遗传算法的动态权重调整
  - 市场状态感知: 区分牛市/熊市/震荡环境下的权重差异

⚠️ 精度实测 (2026-06-29 真实 OOS): 30 只流动股 800 天跨牛熊样本外回测, 生产档
准确率仅约 48% (73 信号, 0/30 统计显著), 约等于随机。"高精度/≥90%" 是设计目标
而非实测命中率; 实盘前务必用 oos_test / walk_forward_validator 复核真实精度。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .analysis.factors import multi_factor_score
from .analysis.indicators import (
    calc_atr,
    calc_kdj,
    calc_ma_alignment,
    calc_macd,
)
from .analysis.volume import calc_obv_slope, calc_volume_ratio
from .log import get_logger
from .strategy.advanced_strategies import ALL_STRATEGY_CONFIGS
from .strategy.base import get_strategy

# v3 新增模块
from .ml_confidence import (
    compute_ml_confidence,
    get_layer_contribution_report,
    orthogonalize_layers,
)
from .adaptive_weights_v2 import get_adaptive_weights

logger = get_logger("predict_v2")

# ═══════════════════════════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class LayerSignal:
    """单层信号输出."""
    layer: str           # 层名 (L1-L11)
    direction: int       # +1 看多, -1 看空, 0 中性
    strength: float      # 0-1 信号强度
    detail: str = ""     # 可读描述


@dataclass
class PrecisionPrediction:
    """高精度预测结果."""
    symbol: str
    name: str = ""
    # 方向 + 置信度
    direction: int = 0           # +1 看多, -1 看空
    direction_label: str = "HOLD"  # BUY/SELL/HOLD
    confidence: float = 0.0      # 0-100 置信度
    # 各层信号
    layers: list[LayerSignal] = field(default_factory=list)
    layers_agree: int = 0        # 同方向层数
    layers_total: int = 11       # 总层数 (L1-L11)
    # 辅助信息
    last_price: float = 0.0
    score_v1: float = 0.0        # 旧版评分 (对比用)
    multi_factor_composite: float = 0.0
    strategy_votes: dict = field(default_factory=dict)
    # 预测文本
    prediction_3d: str = ""
    prediction_7d: str = ""
    prediction_30d: str = ""
    # research 档位标注 (production 为空)
    mode: str = "production"
    oos_note: str = ""
    # edge 渐进门控
    edge_setup: str = ""
    edge_score: float = 0.0

    def to_dict(self) -> dict:
        out = {
            "symbol": self.symbol,
            "name": self.name,
            "direction": self.direction,
            "direction_label": self.direction_label,
            "confidence": round(self.confidence, 1),
            # 实证命中率估计 (0-1): 由离线 OOS 归因校准曲线翻译而来, 供风控/仓位使用
            "calibrated_confidence": calibrate_confidence(self.confidence),
            "layers_agree": self.layers_agree,
            "layers_total": self.layers_total,
            "last_price": self.last_price,
            "score_v1": self.score_v1,
            "multi_factor_composite": round(self.multi_factor_composite, 1),
            "strategy_votes": self.strategy_votes,
            "prediction_3d": self.prediction_3d,
            "prediction_7d": self.prediction_7d,
            "prediction_30d": self.prediction_30d,
            "mode": self.mode,
            "edge_setup": self.edge_setup,
            "edge_score": round(self.edge_score, 1),
            "layers": [
                {"layer": l.layer, "direction": l.direction,
                 "strength": round(l.strength, 2), "detail": l.detail}
                for l in self.layers
            ],
        }
        if self.mode == "research" or self.oos_note:
            out["oos_benchmark"] = OOS_BENCHMARK
            out["oos_note"] = self.oos_note or str(OOS_BENCHMARK.get("disclaimer", ""))
        return out


# ═══════════════════════════════════════════════════════════════════════
# 层权重 (自适应调整)
# ═══════════════════════════════════════════════════════════════════════

# 2026-07-02 按逐层 OOS 归因重估 (scripts/engine_layer_audit.py, 6期货品种×550日×648评估点):
#   高命中低频层升权: L4 量价 61.1%(36出手) / L8 市场环境 63.6%(44) / L9 相对强弱 54.1%(74)
#   低命中层降权:     L10 波浪 40.9%(646出手,恒出手噪声源) / L5 趋势 46.5%(531) / L6 40.0%(85)
#   其余层命中率 49~52% 居中, 保持不动。样本有限(单轮归因), 调整幅度刻意温和。
DEFAULT_LAYER_WEIGHTS = {
    "L1": 0.18,  # 多策略共振 (50.3%, 方向基础层)
    "L2": 0.14,  # 多因子评分 (51.8%)
    "L3": 0.14,  # 技术指标确认 (50.4%)
    "L4": 0.12,  # 量价验证 (61.1% ↑)
    "L5": 0.05,  # 趋势强度 (46.5% ↓)
    "L6": 0.02,  # 波动率环境 (40.0% ↓, 纯过滤器)
    "L7": 0.04,  # 历史胜率 (49.1%)
    "L8": 0.10,  # 市场环境 (63.6% ↑)
    "L9": 0.12,  # 相对强弱 (54.1% ↑)
    "L10": 0.03, # 波浪理论 (40.9% ↓, 全引擎最弱)
    "L11": 0.06, # A股高手共识 (52.6%)
}

# 策略精度加权 (P3: 基于回测校准)
STRATEGY_ACCURACY_WEIGHTS = {
    "双均线": 1.0,
    "RSI": 0.9,
    "布林带": 0.85,
    "动量": 1.0,
    "MACD交叉": 1.1,
    "KDJ": 0.8,
    "一目均衡": 1.05,
    "放量突破": 0.9,
    "均线带": 1.0,
    "VWAP交叉": 1.0,   # P9 新增
    "Supertrend": 1.05, # P9 新增
}

# 最低置信度门槛 (production / precise — 设计目标, 非实测命中率)
MIN_CONFIDENCE = 85.0

# 最少同方向层数
MIN_AGREE_LAYERS = 6

# research / explore 档位阈值 (更低门槛, 仅供研究观察, 禁止直接用于实盘)
RESEARCH_MIN_CONFIDENCE = 60.0
RESEARCH_MIN_AGREE_LAYERS = 4
EXPLORE_MIN_CONFIDENCE = 55.0
EXPLORE_MIN_AGREE_LAYERS = 3

# 真实 OOS 实证 (2026-06-29, 30 只流动股 × 800 天跨牛熊)
OOS_BENCHMARK: dict[str, object] = {
    "oos_accuracy_production": 0.479,
    "oos_accuracy_relaxed": 0.495,
    "confidence_corr": -0.022,
    "sample": "30只流动股×800天跨牛熊",
    "disclaimer": "11层引擎实测OOS≈随机；仅供研究/可视化，勿直接用于实盘决策",
    # 置信度正交化(同源sqrt次可加)改造后复测 (2026-07-02, 6期货品种×550日, 前瞻1日,
    # scripts/engine_layer_audit.py): 置信度恢复区分力 (corr -0.022 → +0.118,
    # 分桶单调 43%→47%→56%→60%), 但绝对值仍虚高 → 用 calibrate_confidence 翻译成实证命中率。
    "recheck_2026_07_02": {
        "confidence_corr": 0.118,
        "buckets": {"<60": 0.431, "60-70": 0.474, "70-80": 0.557, "80-90": 0.60, ">=90": "样本不足(5)"},
        "sample": "6期货品种×550日×551信号",
    },
}

# 置信度经验校准锚点: (raw置信度, 实证命中率), 来自上述 2026-07-02 逐层归因分桶。
# >=90 桶仅 5 样本不可信, 保守封顶 0.65; 后续可用 tracker 线上样本重估。
_CALIBRATION_ANCHORS: list[tuple[float, float]] = [
    (0.0, 0.40),
    (55.0, 0.43),
    (65.0, 0.47),
    (75.0, 0.56),
    (85.0, 0.60),
    (100.0, 0.65),
]


def calibrate_confidence(raw: float) -> float:
    """把引擎的"设计置信度"(0-100) 翻译成实证命中率估计 (0-1)。

    动机: 引擎报 85 分的信号历史命中率只有 ~60% —— 原始分是投票强度的
    设计值, 不是概率。按离线 OOS 归因的分桶实测做分段线性插值, 让下游
    (风控/仓位/展示) 拿到的是"这个信号历史上多大概率对"的诚实估计。
    """
    from itertools import pairwise

    r = max(0.0, min(100.0, float(raw)))
    anchors = _CALIBRATION_ANCHORS
    for (x0, y0), (x1, y1) in pairwise(anchors):
        if r <= x1:
            frac = (r - x0) / (x1 - x0) if x1 > x0 else 0.0
            return round(y0 + frac * (y1 - y0), 4)
    return anchors[-1][1]

PROFILE_THRESHOLDS: dict[str, tuple[float, int, str]] = {
    "production": (MIN_CONFIDENCE, MIN_AGREE_LAYERS, "production"),
    "precise": (MIN_CONFIDENCE, MIN_AGREE_LAYERS, "production"),
    "research": (RESEARCH_MIN_CONFIDENCE, RESEARCH_MIN_AGREE_LAYERS, "research"),
    "explore": (EXPLORE_MIN_CONFIDENCE, EXPLORE_MIN_AGREE_LAYERS, "research"),
}


def resolve_profile_thresholds(profile: str | None = None) -> tuple[float, int, str]:
    """按 profile 返回 (min_confidence, min_agree_layers, mode)."""
    key = (profile or "production").strip().lower()
    return PROFILE_THRESHOLDS.get(key, PROFILE_THRESHOLDS["production"])

# regime 动态因子权重开关(默认开)。该权重含季节性(当月)日历依赖, 会令同一标的在
# 不同月份得分不同。回测/复现场景可设环境变量 QT_REGIME_WEIGHTS=0 关闭, 回退默认
# 等权, 保证结果可复现。
USE_REGIME_FACTOR_WEIGHTS = os.environ.get("QT_REGIME_WEIGHTS", "1").strip().lower() not in ("0", "false", "no")


# ═══════════════════════════════════════════════════════════════════════
# L1: 多策略共振 (11 策略投票)
# ═══════════════════════════════════════════════════════════════════════

def _latest_strategy_signals(prices: pd.DataFrame) -> dict[str, int]:
    """算一次 11 策略在最新 bar 的方向 {label: -1/0/1}，异常按 HOLD(0) 处理.

    L1 共振与 predict_single 的 votes 都只需"每个策略的最新方向"，原本各自跑一遍
    ALL_STRATEGY_CONFIGS（11 策略算两遍）。抽出此处算一次复用，消除重复计算。
    """
    recent = prices.iloc[-250:] if len(prices) >= 250 else prices
    out: dict[str, int] = {}
    for sname, sparams, slabel in ALL_STRATEGY_CONFIGS:
        try:
            sig = get_strategy(sname, **sparams).generate(recent)
            out[slabel] = int(sig.iloc[-1]) if len(sig) > 0 else 0
        except Exception:
            out[slabel] = 0
    return out


def _layer_strategy_resonance(prices: pd.DataFrame,
                              signals: dict[str, int] | None = None) -> LayerSignal:
    """11 策略加权投票: HOLD=弃权, 只计算 BUY/SELL 比例.

    [signals] 可传入 _latest_strategy_signals 的结果以复用计算；为 None 时自算，
    保持对既有直接调用方的向后兼容。
    """
    if prices is None or len(prices) < 60:
        return LayerSignal("L1", 0, 0, "数据不足")

    sig_map = signals if signals is not None else _latest_strategy_signals(prices)
    weighted_buy = 0.0
    weighted_sell = 0.0
    active_weight = 0.0  # 只计算有方向的策略
    total_count = 0
    buy_count = 0
    sell_count = 0
    vote_details = []

    for _sname, _sparams, slabel in ALL_STRATEGY_CONFIGS:
        latest = sig_map.get(slabel, 0)
        w = STRATEGY_ACCURACY_WEIGHTS.get(slabel, 1.0)
        total_count += 1
        if latest == 1:
            weighted_buy += w
            active_weight += w
            buy_count += 1
            vote_details.append(f"{slabel}↑")
        elif latest == -1:
            weighted_sell += w
            active_weight += w
            sell_count += 1
            vote_details.append(f"{slabel}↓")
        else:
            # HOLD = 弃权, 不计入 active_weight
            vote_details.append(f"{slabel}=")

    # 只看 BUY/SELL 的比例 (忽略 HOLD)
    if active_weight > 0:
        buy_ratio = weighted_buy / active_weight
        sell_ratio = weighted_sell / active_weight
    else:
        buy_ratio = 0
        sell_ratio = 0

    # 判断: 需要有方向性投票, 且多数同意
    if buy_count >= 3 and buy_ratio >= 0.65:
        return LayerSignal("L1", 1, buy_ratio,
                           f"多头共振 {buy_count}/{total_count} [{', '.join(vote_details[:5])}...]")
    elif sell_count >= 3 and sell_ratio >= 0.65:
        return LayerSignal("L1", -1, sell_ratio,
                           f"空头共振 {sell_count}/{total_count} [{', '.join(vote_details[:5])}...]")
    elif buy_count >= 2 and buy_ratio >= 0.55:
        return LayerSignal("L1", 1, buy_ratio * 0.6,
                           f"偏多 {buy_count}/{total_count}")
    elif sell_count >= 2 and sell_ratio >= 0.55:
        return LayerSignal("L1", -1, sell_ratio * 0.6,
                           f"偏空 {sell_count}/{total_count}")
    return LayerSignal("L1", 0, 0, f"分歧 B{buy_count}/S{sell_count}/H{total_count-buy_count-sell_count}")


# ═══════════════════════════════════════════════════════════════════════
# L2: 多因子评分 (5 因子极端值)
# ═══════════════════════════════════════════════════════════════════════

def _layer_factor_score(prices: pd.DataFrame) -> LayerSignal:
    """5 因子综合评分: ≥70 看多, ≤30 看空, 否则中性。

    因子权重按当前市场环境(regime)动态调整: 趋势市抬动量/趋势, 熊市抬均值回归/
    波动率 —— 接通此前休眠的 regime 权重(adjust_factor_weights), 缓解趋势股被
    「均值回归超买惩罚」抵消、L2 难触发的问题。失败时回退默认等权。
    """
    if prices is None or len(prices) < 60:
        return LayerSignal("L2", 0, 0, "数据不足")

    try:
        weights = _market_context_cached(
            as_of=prices.index[-1] if len(prices) else None).recommended_weights
    except Exception:
        weights = None
    result = multi_factor_score(prices, weights=weights)
    composite = result["composite"]

    if composite >= 70:
        strength = min((composite - 70) / 30, 1.0)
        return LayerSignal("L2", 1, strength,
                           f"因子强多 {composite:.0f} ({result['grade']})")
    elif composite <= 30:
        strength = min((30 - composite) / 30, 1.0)
        return LayerSignal("L2", -1, strength,
                           f"因子强空 {composite:.0f} ({result['grade']})")
    elif composite >= 55:
        return LayerSignal("L2", 1, 0.4,
                           f"因子偏多 {composite:.0f}")
    elif composite <= 45:
        return LayerSignal("L2", -1, 0.4,
                           f"因子偏空 {composite:.0f}")
    return LayerSignal("L2", 0, 0, f"因子中性 {composite:.0f}")


# ═══════════════════════════════════════════════════════════════════════
# L3: 技术指标确认 (MACD + KDJ + 均线 三者同向)
# ═══════════════════════════════════════════════════════════════════════

def _layer_indicator_confirm(prices: pd.DataFrame) -> LayerSignal:
    """MACD + KDJ + 均线排列 三者同方向才算确认."""
    if prices is None or len(prices) < 60:
        return LayerSignal("L3", 0, 0, "数据不足")

    close = prices["close"]
    macd = calc_macd(close)
    kdj = calc_kdj(prices)
    ma = calc_ma_alignment(close)

    # 各指标方向
    macd_dir = 1 if macd["score"] > 55 else (-1 if macd["score"] < 45 else 0)
    kdj_dir = 1 if kdj["score"] > 55 else (-1 if kdj["score"] < 45 else 0)
    ma_dir = 1 if ma["score"] > 55 else (-1 if ma["score"] < 45 else 0)

    directions = [macd_dir, kdj_dir, ma_dir]
    bullish = sum(1 for d in directions if d == 1)
    bearish = sum(1 for d in directions if d == -1)

    if bullish == 3:
        avg_score = (macd["score"] + kdj["score"] + ma["score"]) / 3
        return LayerSignal("L3", 1, 0.9,
                           f"三指标共振多 MACD={macd['score']:.0f} KDJ={kdj['score']:.0f} MA={ma['score']:.0f}")
    elif bearish == 3:
        avg_score = (macd["score"] + kdj["score"] + ma["score"]) / 3
        return LayerSignal("L3", -1, 0.9,
                           f"三指标共振空 MACD={macd['score']:.0f} KDJ={kdj['score']:.0f} MA={ma['score']:.0f}")
    elif bullish >= 2:
        return LayerSignal("L3", 1, 0.5,
                           f"偏多 {bullish}/3 MACD={macd['score']:.0f} KDJ={kdj['score']:.0f} MA={ma['score']:.0f}")
    elif bearish >= 2:
        return LayerSignal("L3", -1, 0.5,
                           f"偏空 {bearish}/3 MACD={macd['score']:.0f} KDJ={kdj['score']:.0f} MA={ma['score']:.0f}")
    return LayerSignal("L3", 0, 0, f"指标分歧 B{bullish}/S{bearish}")


# ═══════════════════════════════════════════════════════════════════════
# L4: 量价验证
# ═══════════════════════════════════════════════════════════════════════

def _layer_volume_confirm(prices: pd.DataFrame) -> LayerSignal:
    """量价配合验证: 放量突破/缩量回调确认."""
    if prices is None or len(prices) < 30:
        return LayerSignal("L4", 0, 0, "数据不足")

    close = prices["close"]
    has_volume = "volume" in prices.columns

    if not has_volume:
        return LayerSignal("L4", 0, 0.3, "无量数据, 默认通过")

    volume = prices["volume"]

    # 量比
    vr = calc_volume_ratio(volume)
    # OBV 方向
    obv = calc_obv_slope(close, volume)

    # 近 5 日价格变化
    ret_5d = float(close.iloc[-1] / close.iloc[-5] - 1) if len(close) >= 5 else 0
    # 近 5 日量变化
    vol_5 = float(volume.iloc[-5:].mean()) if len(volume) >= 5 else 0
    vol_20 = float(volume.iloc[-20:].mean()) if len(volume) >= 20 else vol_5
    vol_ratio = vol_5 / vol_20 if vol_20 > 0 else 1

    # 放量上涨: 量比 > 1.3 且价格上涨
    if vol_ratio > 1.3 and ret_5d > 0.02:
        return LayerSignal("L4", 1, min(vol_ratio / 2, 1.0),
                           f"放量上涨 量比{vol_ratio:.1f} 涨{ret_5d*100:.1f}%")
    # 放量下跌
    elif vol_ratio > 1.3 and ret_5d < -0.02:
        return LayerSignal("L4", -1, min(vol_ratio / 2, 1.0),
                           f"放量下跌 量比{vol_ratio:.1f} 跌{ret_5d*100:.1f}%")
    # 缩量上涨 (健康回调后上涨)
    elif vol_ratio < 0.7 and ret_5d > 0.01 and obv["direction"] == "up":
        return LayerSignal("L4", 1, 0.5,
                           f"缩量上涨 资金流入 OBV{obv['direction']}")
    # OBV 背离 (价格跌但资金流入)
    elif ret_5d < -0.01 and obv["direction"] == "up":
        return LayerSignal("L4", 1, 0.4,
                           f"量价背离 价格跌但OBV升")
    elif ret_5d > 0.01 and obv["direction"] == "down":
        return LayerSignal("L4", -1, 0.4,
                           f"量价背离 价格升但OBV降")
    return LayerSignal("L4", 0, 0, f"量价中性 量比{vol_ratio:.1f}")


# ═══════════════════════════════════════════════════════════════════════
# L5: 趋势强度 (ADX + 均线位置)
# ═══════════════════════════════════════════════════════════════════════

def _calc_adx(df: pd.DataFrame, period: int = 14) -> float:
    """计算 ADX (Average Directional Index). 简化版."""
    if len(df) < period * 2:
        return 0.0

    high = df["high"]
    low = df["low"]
    close = df["close"]

    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)

    atr = tr.rolling(period).mean()
    plus_di = 100 * plus_dm.rolling(period).mean() / atr.replace(0, np.nan)
    minus_di = 100 * minus_dm.rolling(period).mean() / atr.replace(0, np.nan)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.rolling(period).mean()

    return float(adx.iloc[-1]) if len(adx.dropna()) > 0 else 0.0


def _layer_trend_strength(prices: pd.DataFrame) -> LayerSignal:
    """趋势强度: ADX > 25 表示趋势明确, 结合 MA60 判断方向."""
    if prices is None or len(prices) < 60:
        return LayerSignal("L5", 0, 0, "数据不足")

    close = prices["close"]
    price = float(close.iloc[-1])
    ma60 = float(close.rolling(60).mean().iloc[-1]) if len(close) >= 60 else price
    ma20 = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else price

    adx = _calc_adx(prices)

    if adx < 20:
        return LayerSignal("L5", 0, 0, f"无趋势 ADX={adx:.0f}")

    above_ma60 = price > ma60
    above_ma20 = price > ma20

    if adx >= 25 and above_ma60 and above_ma20:
        strength = min(adx / 50, 1.0)
        return LayerSignal("L5", 1, strength,
                           f"强多头趋势 ADX={adx:.0f} 价格>MA60")
    elif adx >= 25 and not above_ma60 and not above_ma20:
        strength = min(adx / 50, 1.0)
        return LayerSignal("L5", -1, strength,
                           f"强空头趋势 ADX={adx:.0f} 价格<MA60")
    elif adx >= 20 and above_ma60:
        return LayerSignal("L5", 1, 0.3,
                           f"偏多 ADX={adx:.0f}")
    elif adx >= 20 and not above_ma60:
        return LayerSignal("L5", -1, 0.3,
                           f"偏空 ADX={adx:.0f}")
    return LayerSignal("L5", 0, 0, f"趋势不明确 ADX={adx:.0f}")


# ═══════════════════════════════════════════════════════════════════════
# L6: 波动率环境 (ATR 分位) — 纯过滤器, 不参与方向投票
# ═══════════════════════════════════════════════════════════════════════

def _layer_volatility_env(prices: pd.DataFrame) -> LayerSignal:
    """波动率环境: 极端波动时抑制预测, 否则中性."""
    if prices is None or len(prices) < 30:
        return LayerSignal("L6", 0, 0, "数据不足")

    atr = calc_atr(prices)
    percentile = atr["atr_percentile"]

    if percentile >= 90:
        # 极端波动 → 返回 -1 作为抑制信号
        return LayerSignal("L6", -1, 0.8,
                           f"极端波动 {percentile:.0f}%, 抑制预测")
    elif percentile >= 70:
        return LayerSignal("L6", 0, 0,
                           f"高波动 {percentile:.0f}%, 谨慎")
    else:
        return LayerSignal("L6", 0, 0,
                           f"正常波动 {percentile:.0f}%")


# ═══════════════════════════════════════════════════════════════════════
# L7: 历史胜率校验 (11 策略共识回测)
# ═══════════════════════════════════════════════════════════════════════

def _layer_historical_winrate(prices: pd.DataFrame) -> LayerSignal:
    """用 11 策略共识回测最近 120 天的方向准确率."""
    if prices is None or len(prices) < 60:
        return LayerSignal("L7", 0, 0, "数据不足")

    close = prices["close"].values
    lookback = min(90, len(close) - 10)
    correct = 0
    total = 0

    # 性能优化: 对完整序列一次性生成每个策略的信号, 滑窗内按下标取值,
    # 避免在 ~18 个回测点 × 11 策略上重复 generate (原实现每点仅用 sig[-1], 整段 rolling 被浪费)。
    # 技术策略均为因果指标, full_sig[i] 不依赖 i 之后的数据, 与原"截至 i"语义一致。
    strat_sigs: list = []
    for sname, sparams, _ in ALL_STRATEGY_CONFIGS:
        try:
            arr = get_strategy(sname, **sparams).generate(prices).to_numpy()
            if len(arr) == len(close):
                strat_sigs.append(arr)
        except Exception:
            pass

    for i in range(len(close) - lookback, len(close) - 7, 5):
        # 用 11 策略投票
        votes = {"BUY": 0, "SELL": 0}
        for sig_arr in strat_sigs:
            latest = int(sig_arr[i])
            if latest == 1:
                votes["BUY"] += 1
            elif latest == -1:
                votes["SELL"] += 1

        total_votes = votes["BUY"] + votes["SELL"]
        if total_votes < 3:
            continue

        pred_up = votes["BUY"] > votes["SELL"]
        actual_ret = close[i + 7] / close[i] - 1
        actual_up = actual_ret > 0

        total += 1
        if pred_up == actual_up:
            correct += 1

    if total < 3:
        return LayerSignal("L7", 0, 0, f"样本不足 ({total})")

    win_rate = correct / total

    if win_rate >= 0.60:
        return LayerSignal("L7", 1, win_rate,
                           f"共识胜率 {win_rate:.0%} ({correct}/{total})")
    elif win_rate <= 0.40:
        return LayerSignal("L7", -1, 1 - win_rate,
                           f"共识败率 {win_rate:.0%} ({correct}/{total})")
    return LayerSignal("L7", 0, 0, f"共识中性 {win_rate:.0%}")


# ═══════════════════════════════════════════════════════════════════════
# L8: 市场环境 (P5)
# ═══════════════════════════════════════════════════════════════════════

def _layer_market_regime(prices: pd.DataFrame) -> LayerSignal:
    """市场环境: 熊市/高波动时抑制, 牛市时中性."""
    try:
        from .market_context import MarketRegime
        # regime 是 MarketRegime 枚举(值为中文「熊市/牛市/...」), 必须按枚举比较;
        # 旧代码拿它跟英文字符串 "bear" 比恒为 False, 是 L8 失效的第二个原因。
        ctx = _market_context_cached(as_of=prices.index[-1] if len(prices) else None)
        regime = ctx.regime
        sentiment = ctx.sentiment_score  # 0-100

        if regime == MarketRegime.BEAR:
            return LayerSignal("L8", -1, 0.8,
                               "熊市环境, 抑制多头")
        elif regime == MarketRegime.VOLATILE:
            return LayerSignal("L8", 0, 0,
                               "高波动环境, 谨慎")
        elif regime == MarketRegime.BULL and sentiment >= 60:
            return LayerSignal("L8", 1, 0.3,
                               f"牛市 情绪{sentiment:.0f}")
        else:
            return LayerSignal("L8", 0, 0,
                               f"{regime.value} 情绪{sentiment:.0f}")
    except Exception as e:
        logger.debug("L8 市场环境层异常: %s", e)
        return LayerSignal("L8", 0, 0, "环境数据不可用")


# ═══════════════════════════════════════════════════════════════════════
# L9: 相对强弱 (P6)
# ═══════════════════════════════════════════════════════════════════════

# 基准数据缓存 (避免每次加载)
_BENCHMARK_CACHE: dict[str, pd.DataFrame] = {}

def _get_benchmark(as_of=None) -> pd.DataFrame | None:
    """加载基准指数 (带缓存)。

    [as_of] 给定时仅返回该日期(含)之前的基准 —— 回测/OOS 必须传, 否则会拿"最新"
    基准去比历史标的, 形成未来函数(look-ahead)。实时预测不传, 使用全量最新。
    """
    if "benchmark" in _BENCHMARK_CACHE:
        val = _BENCHMARK_CACHE["benchmark"]
        full = None if val is _SENTINEL_FAILED else val
    else:
        full = None
        from .predict import _load_stock_prices
        # 尝试多个指数代码
        for code in ["399300", "000001", "600000"]:
            try:
                b = _load_stock_prices(code)
                if b is not None and len(b) >= 60:
                    full = b
                    break
            except Exception:
                continue
        _BENCHMARK_CACHE["benchmark"] = full if full is not None else _SENTINEL_FAILED
    if full is None:
        return None
    if as_of is not None:
        full = full[full.index <= as_of]
        if len(full) < 60:
            return None
    return full


_SENTINEL_FAILED = object()  # 标记加载失败，避免重复尝试

# 市场级上下文按日缓存: regime/sentiment/因子权重是全市场状态, 不应每只标的重算
_MARKET_CTX_CACHE: dict = {}


def _market_context_cached(as_of=None):
    """构建并缓存市场上下文(已传入基准指数), 供 L8 与 L2 因子权重复用。

    复用 L9 的 _get_benchmark() 加载指数 —— 否则 build_market_context 拿不到
    index_prices 会恒判为「震荡」, 使 L8 形同虚设。
    """
    from datetime import date as _date
    key = (as_of.isoformat() if hasattr(as_of, "isoformat") else str(as_of)) \
        if as_of is not None else _date.today().isoformat()
    cached = _MARKET_CTX_CACHE.get(key)
    if cached is not None:
        return cached
    from .market_context import build_market_context
    ctx = build_market_context(index_prices=_get_benchmark(as_of=as_of))
    # 回测会按多个 as_of 反复构造; 限制缓存条目数防无界增长
    if len(_MARKET_CTX_CACHE) > 64:
        _MARKET_CTX_CACHE.clear()
    _MARKET_CTX_CACHE[key] = ctx
    return ctx


def _layer_relative_strength(prices: pd.DataFrame) -> LayerSignal:
    """相对强弱: 跑赢大盘 → 看多, 跑输 → 看空."""
    try:
        benchmark = _get_benchmark(as_of=prices.index[-1] if len(prices) else None)
        if benchmark is None:
            return LayerSignal("L9", 0, 0, "基准数据不可用")

        # 20 日相对强弱
        rs_20 = (prices["close"].iloc[-1] / prices["close"].iloc[-20] - 1) - \
                (benchmark["close"].iloc[-1] / benchmark["close"].iloc[-20] - 1)
        # 60 日相对强弱
        rs_60 = (prices["close"].iloc[-1] / prices["close"].iloc[-60] - 1) - \
                (benchmark["close"].iloc[-1] / benchmark["close"].iloc[-60] - 1)

        if rs_20 > 0.05 and rs_60 > 0.08:
            return LayerSignal("L9", 1, min(rs_20 * 5, 1.0),
                               f"强势股 20d跑赢{rs_20*100:+.1f}%")
        elif rs_20 < -0.05 and rs_60 < -0.08:
            return LayerSignal("L9", -1, min(abs(rs_20) * 5, 1.0),
                               f"弱势股 20d跑输{rs_20*100:+.1f}%")
        return LayerSignal("L9", 0, 0,
                           f"中性 RS20={rs_20*100:+.1f}%")
    except Exception as e:
        logger.debug("L9 相对强弱层异常: %s", e)
        return LayerSignal("L9", 0, 0, "RS计算失败")


# ═══════════════════════════════════════════════════════════════════════
# L10: 波浪理论 (Elliott Wave)
# ═══════════════════════════════════════════════════════════════════════

def _layer_wave_analysis(prices: pd.DataFrame) -> LayerSignal:
    """波浪理论分析: 识别浪型 → 预测方向."""
    try:
        from .analysis.wave import analyze_wave
        result = analyze_wave(prices, threshold=0.03)

        if result.signal == "BUY":
            return LayerSignal("L10", 1, result.confidence,
                               f"波浪看多: {result.reason}")
        elif result.signal == "SELL":
            return LayerSignal("L10", -1, result.confidence,
                               f"波浪看空: {result.reason}")
        return LayerSignal("L10", 0, 0,
                           f"波浪中性: {result.reason}")
    except Exception as e:
        logger.debug("L10 波浪层异常: %s", e)
        return LayerSignal("L10", 0, 0, "波浪分析失败")


# ═══════════════════════════════════════════════════════════════════════
# L11: A股高手策略共识
# ═══════════════════════════════════════════════════════════════════════

def _layer_expert_consensus(prices: pd.DataFrame) -> LayerSignal:
    """A股高手策略共识: 5个策略投票."""
    try:
        from .analysis.expert import expert_consensus
        result = expert_consensus(prices)

        if result["signal"] == "BUY":
            return LayerSignal("L11", 1, result["confidence"],
                               f"高手共识: {result['reason']}")
        elif result["signal"] == "SELL":
            return LayerSignal("L11", -1, result["confidence"],
                               f"高手共识: {result['reason']}")
        return LayerSignal("L11", 0, 0,
                           f"高手共识: {result['reason']}")
    except Exception as e:
        logger.debug("L11 高手共识层异常: %s", e)
        return LayerSignal("L11", 0, 0, "高手策略失败")


# ═══════════════════════════════════════════════════════════════════════
# 置信度计算 (双门槛: 同意层数 + 加权强度)
# ═══════════════════════════════════════════════════════════════════════

# 层 → 信息源分组: 用于置信度的正交性惩罚, 避免同源层被重复计数而虚高置信度。
# 趋势/均线类(L1/L3/L5/L7/L11)高度同源, 归一组; 其余各自独立。
_LAYER_GROUP = {
    "L1": "trend", "L3": "trend", "L5": "trend", "L7": "trend", "L11": "trend",
    "L2": "value", "L4": "volume", "L6": "volatility",
    "L8": "market", "L9": "market", "L10": "pattern",
}


def _interp_base(base_scores: dict[int, int], eff: float) -> float:
    """按"有效独立层数"(可含小数)在整数锚点的 base_scores 上线性插值。

    eff 来自同源次可加(sqrt)的有效层数, 通常落在两个整数锚点之间, 需插值取分。
    """
    if eff <= 1:
        return float(base_scores[1])
    lo = int(eff)
    if lo >= 11:
        return float(base_scores[11])
    frac = eff - lo
    return base_scores[lo] + frac * (base_scores[lo + 1] - base_scores[lo])


def compute_confidence(layers: list[LayerSignal],
                       weights: dict[str, float] | None = None) -> tuple[int, float, int]:
    """置信度 = 基础分(同意层数) × 强度加成 × 权重覆盖.

    核心逻辑:
      - 同意层数是主要决定因素 (6层→83%, 7层→88%, 8层→92%)
      - 各层强度作为加成 (强信号提升, 弱信号降低)
      - 权重覆盖: 同意层覆盖了多少总权重

    Returns:
        (direction, confidence, agree_count)
        direction: +1 看多, -1 看空, 0 无法判断
        confidence: 0-100 置信度
        agree_count: 同方向层数 (排除中性层)
    """
    w = weights or DEFAULT_LAYER_WEIGHTS

    # 统计方向 (排除中性层)
    bull_layers = [l for l in layers if l.direction == 1 and l.strength > 0]
    bear_layers = [l for l in layers if l.direction == -1 and l.strength > 0]

    # 确定主方向
    if len(bull_layers) > len(bear_layers):
        direction = 1
        agreeing_layers = bull_layers
    elif len(bear_layers) > len(bull_layers):
        direction = -1
        agreeing_layers = bear_layers
    else:
        return 0, 0.0, 0

    agree_count = len(agreeing_layers)

    # ── 基础分: 按"有效独立层数"而非原始同意层数(从源头正交化) ──
    # 病根(实测 OOS≈随机、置信度与命中率相关≈0、最高档反而最差): L1/L3/L5/L7/L11 都建在
    # 趋势·均线·MACD 同源指标上, "多层同意"常是同一信号被重复计数 → base 虚高。
    # 修复: 按 _LAYER_GROUP 把同意层归并到信息源, 组内层数次可加(sqrt)——同源第2/3层只贡献
    # 边际递减的"半票", 真正独立的信息源才线性累加。以此得有效独立层数 effective 再插值 base,
    # 取代原先治标的 diversity 乘法补丁, 避免伪独立共振虚抬置信度。
    base_scores = {1: 50, 2: 58, 3: 65, 4: 72, 5: 78, 6: 83, 7: 88, 8: 92, 9: 95, 10: 97, 11: 98}
    group_counts: dict[str, int] = {}
    for l in agreeing_layers:
        g = _LAYER_GROUP.get(l.layer, l.layer)
        group_counts[g] = group_counts.get(g, 0) + 1
    effective = sum(c ** 0.5 for c in group_counts.values())  # 同源次可加, 抑制重复计数
    base = _interp_base(base_scores, effective)

    # ── 强度加成: 平均强度 ──
    avg_strength = sum(l.strength for l in agreeing_layers) / len(agreeing_layers)
    # 范围: 0.8 (strength=0) ~ 1.2 (strength=0.9)
    strength_mult = 0.8 + avg_strength * 0.45

    # ── 权重覆盖: 同意层覆盖了多少总权重 ──
    total_weight = sum(w.values())
    agreeing_weight = sum(w.get(l.layer, 0) for l in agreeing_layers)
    coverage = agreeing_weight / total_weight if total_weight > 0 else 0
    # 范围: 0.9 (coverage=0) ~ 1.05 (coverage=1)
    coverage_mult = 0.9 + coverage * 0.15

    confidence = base * strength_mult * coverage_mult
    confidence = min(100, max(0, confidence))

    # agree_count 仍返回原始同意层数(对外语义/门槛/展示不变), 正交化只作用于 base 评分
    return direction, confidence, agree_count


# ═══════════════════════════════════════════════════════════════════════
# v3 新增: ML正交化置信度计算
# ═══════════════════════════════════════════════════════════════════════

def compute_confidence_v3(layers: list[LayerSignal],
                           regime: str | None = None,
                           use_ml: bool = True) -> tuple[int, float, int]:
    """ML正交化置信度计算 (v3).

    集成 ml_confidence.py 和 adaptive_weights_v2.py 的改进:
    1. 信息源分组正交化（更激进的组内抑制）
    2. 自适应权重（基于市场状态和历史表现）
    3. 返回ML贡献报告用于调试

    Returns:
        (direction, confidence, effective_layers)
    """
    if not layers:
        return 0, 0.0, 0

    # 获取自适应权重
    weights = get_adaptive_weights(regime=regime)

    # 转换为 dict 格式供 ml_confidence 使用
    layer_dicts = [
        {"layer": l.layer, "direction": l.direction, "strength": l.strength}
        for l in layers
    ]

    # 使用ML正交化置信度
    direction, ml_confidence, effective_layers = compute_ml_confidence(
        layer_dicts,
        use_ml_fallback=use_ml,
    )

    # 应用权重覆盖加成
    agreeing_layers = [l for l in layers if l.direction == direction and l.strength > 0]
    total_weight = sum(weights.values())
    agreeing_weight = sum(weights.get(l.layer, 0) for l in agreeing_layers)
    coverage = agreeing_weight / total_weight if total_weight > 0 else 0

    # 权重覆盖加成：范围 0.9 ~ 1.05
    coverage_mult = 0.9 + coverage * 0.15

    final_confidence = min(100, ml_confidence * coverage_mult)

    return direction, final_confidence, effective_layers


def get_layer_diagnosis(layers: list[LayerSignal]) -> dict:
    """获取层信号诊断报告 (v3 调试用)."""
    layer_dicts = [
        {"layer": l.layer, "direction": l.direction, "strength": l.strength}
        for l in layers
    ]
    return get_layer_contribution_report(layer_dicts)


# ═══════════════════════════════════════════════════════════════════════
# 前瞻胜率计算 (3d/7d/30d)
# ═══════════════════════════════════════════════════════════════════════

def _forward_win_rates(prices: pd.DataFrame,
                       windows: list[int] | None = None) -> dict[int, dict]:
    """计算各窗口的前瞻胜率和平均收益."""
    if windows is None:
        windows = [3, 7, 30]

    close = prices["close"].values
    n = len(close)
    results = {}

    for w in windows:
        if n < w + 20:
            results[w] = {"win_rate": 0.5, "avg_return": 0.0, "samples": 0}
            continue

        lookback = min(250, n - w)
        returns = []
        for i in range(n - lookback, n - w):
            ret = close[i + w] / close[i] - 1
            returns.append(ret)

        if not returns:
            results[w] = {"win_rate": 0.5, "avg_return": 0.0, "samples": 0}
            continue

        win_rate = sum(1 for r in returns if r > 0) / len(returns)
        avg_return = float(np.mean(returns))

        results[w] = {
            "win_rate": round(win_rate, 3),
            "avg_return": round(avg_return, 4),
            "samples": len(returns),
        }

    return results


def _make_prediction_text(win_rate: float, avg_return: float) -> str:
    """将胜率和平均收益转为预测文本."""
    if win_rate >= 0.7:
        return f"看涨 ({avg_return*100:+.1f}%)"
    elif win_rate >= 0.55:
        return f"偏涨 ({avg_return*100:+.1f}%)"
    elif win_rate <= 0.3:
        return f"看跌 ({avg_return*100:+.1f}%)"
    elif win_rate <= 0.45:
        return f"偏跌 ({avg_return*100:+.1f}%)"
    return f"震荡 ({avg_return*100:+.1f}%)"


# ═══════════════════════════════════════════════════════════════════════
# 核心预测函数
# ═══════════════════════════════════════════════════════════════════════

def predict_single(
    prices: pd.DataFrame,
    symbol: str,
    name: str = "",
    min_confidence: float = MIN_CONFIDENCE,
    min_agree_layers: int = MIN_AGREE_LAYERS,
    layer_weights: dict[str, float] | None = None,
    profile: str | None = None,
    use_v3: bool = True,  # v3: 使用ML正交化置信度
) -> PrecisionPrediction | None:
    """对单个标的做高精度预测.

    只有置信度 ≥ min_confidence 才返回结果, 否则返回 None.
    profile: production/precise/research/explore — 覆盖门槛与输出 mode 标注.
    use_v3: 是否使用v3 ML正交化置信度（默认开启，解决层间伪独立问题）
    """
    if prices is None or len(prices) < 60:
        return None

    if profile:
        min_confidence, min_agree_layers, out_mode = resolve_profile_thresholds(profile)
    else:
        out_mode = "production"

    # 先算一次 11 策略最新信号，L1 共振与下方 votes 复用，避免重复计算
    sig_map = _latest_strategy_signals(prices)

    # 11 层信号计算 (L8 市场环境 + L9 相对强弱 + L10 波浪 + L11 高手共识)
    layers = [
        _layer_strategy_resonance(prices, sig_map),
        _layer_factor_score(prices),
        _layer_indicator_confirm(prices),
        _layer_volume_confirm(prices),
        _layer_trend_strength(prices),
        _layer_volatility_env(prices),
        _layer_historical_winrate(prices),
        _layer_market_regime(prices),
        _layer_relative_strength(prices),
        _layer_wave_analysis(prices),       # L10: 波浪理论
        _layer_expert_consensus(prices),    # L11: A股高手共识
    ]

    # 计算置信度
    # v3: 使用ML正交化置信度（解决层间伪独立问题）
    if use_v3:
        # 获取市场状态用于自适应权重
        regime = _get_current_regime(prices)
        direction, confidence, agree_count = compute_confidence_v3(
            layers, regime=regime, use_ml=True
        )
        # v3 置信度可能较低，因为正交化抑制了伪独立信号
        # 如果v3置信度为0但原始计算有结果，回退到原始逻辑
        if confidence == 0:
            direction, confidence, agree_count = compute_confidence(layers, layer_weights)
    else:
        direction, confidence, agree_count = compute_confidence(layers, layer_weights)

    # 低于门槛 → 不输出
    if confidence < min_confidence:
        return None

    # 低于最少同方向层数 → 不输出
    if agree_count < min_agree_layers:
        return None

    # 生产档: 渐进式 edge 软确认（非硬拦截全部）
    if out_mode == "production":
        from .direction_edge import production_edge_allows
        if not production_edge_allows(prices, direction, agree_count):
            return None

    # 前瞻胜率
    win_rates = _forward_win_rates(prices)

    # 策略投票详情（复用上面已算的 sig_map，不再重复跑 11 策略）
    votes = {
        slabel: ("BUY" if v == 1 else ("SELL" if v == -1 else "HOLD"))
        for slabel, v in sig_map.items()
    }

    # 多因子评分
    mf = multi_factor_score(prices)

    close = prices["close"]
    direction_label = "BUY" if direction == 1 else ("SELL" if direction == -1 else "HOLD")

    from .direction_edge import find_best_edge_setup
    edge = find_best_edge_setup(prices)
    edge_name = edge.name if edge else ""
    edge_score = edge.score if edge else 0.0

    oos_note = ""
    if out_mode == "research":
        oos_note = str(OOS_BENCHMARK.get("disclaimer", ""))

    return PrecisionPrediction(
        symbol=symbol,
        name=name,
        direction=direction,
        direction_label=direction_label,
        confidence=round(confidence, 1),
        layers=layers,
        layers_agree=agree_count,
        layers_total=len(layers),
        last_price=round(float(close.iloc[-1]), 2),
        multi_factor_composite=mf["composite"],
        strategy_votes=votes,
        mode=out_mode,
        oos_note=oos_note,
        edge_setup=edge_name,
        edge_score=edge_score,
        prediction_3d=_make_prediction_text(
            win_rates.get(3, {}).get("win_rate", 0.5),
            win_rates.get(3, {}).get("avg_return", 0)),
        prediction_7d=_make_prediction_text(
            win_rates.get(7, {}).get("win_rate", 0.5),
            win_rates.get(7, {}).get("avg_return", 0)),
        prediction_30d=_make_prediction_text(
            win_rates.get(30, {}).get("win_rate", 0.5),
            win_rates.get(30, {}).get("avg_return", 0)),
    )


# ═══════════════════════════════════════════════════════════════════════
# v3 辅助函数
# ═══════════════════════════════════════════════════════════════════════

def _get_current_regime(prices: pd.DataFrame) -> str:
    """获取当前市场状态."""
    try:
        from .market_context import MarketRegime
        ctx = _market_context_cached(as_of=prices.index[-1] if len(prices) else None)
        return ctx.regime.value.lower()
    except Exception:
        return "unknown"


# ═══════════════════════════════════════════════════════════════════════
# 批量预测 (股票池 + 期货池)
# ═══════════════════════════════════════════════════════════════════════

def predict_batch(
    codes: list[tuple[str, str]],
    load_fn,
    top_n: int = 3,
    min_confidence: float = MIN_CONFIDENCE,
    min_agree_layers: int = MIN_AGREE_LAYERS,
    max_workers: int = 8,
    profile: str | None = None,
) -> list[PrecisionPrediction]:
    """批量高精度预测, 只返回置信度 ≥ min_confidence 的标的.

    Args:
        codes: [(code, name), ...]
        load_fn: 价格加载函数 (code) -> DataFrame
        top_n: 最多返回几个
        min_confidence: 最低置信度
        min_agree_layers: 最少同意层数
        max_workers: 并行加载线程数
    """
    if profile:
        min_confidence, min_agree_layers, _ = resolve_profile_thresholds(profile)

    from concurrent.futures import ThreadPoolExecutor, as_completed

    # 并行加载价格
    prices_map: dict[str, tuple[str, pd.DataFrame]] = {}

    def _load_one(code, name):
        try:
            p = load_fn(code)
            if p is not None and len(p) >= 60:
                return code, name, p
        except Exception:
            pass
        return None

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_load_one, c, n): (c, n) for c, n in codes}
        for future in as_completed(futures, timeout=30):
            try:
                result = future.result()
                if result:
                    code, name, p = result
                    prices_map[code] = (name, p)
            except Exception:
                pass

    logger.info(f"loaded {len(prices_map)}/{len(codes)} price feeds")

    # 逐个预测
    predictions: list[PrecisionPrediction] = []

    for code, (name, p) in prices_map.items():
        try:
            pred = predict_single(
                p, code, name, min_confidence, min_agree_layers, profile=profile,
            )
            if pred is not None:
                predictions.append(pred)
        except Exception as e:
            logger.warning(f"predict {code} failed: {e}")

    # 按置信度降序
    predictions.sort(key=lambda x: x.confidence, reverse=True)
    return predictions[:top_n]


def predict_stocks_precise(
    codes: list[tuple[str, str]] | None = None,
    top_n: int = 3,
    min_confidence: float = MIN_CONFIDENCE,
    min_agree_layers: int = MIN_AGREE_LAYERS,
    profile: str | None = "precise",
) -> list[PrecisionPrediction]:
    """股票高精度预测. profile=precise|research|explore."""
    from .predict import LIQUID_STOCKS, _load_stock_prices

    universe = codes or LIQUID_STOCKS
    return predict_batch(
        universe, _load_stock_prices, top_n, min_confidence, min_agree_layers,
        profile=profile,
    )


def predict_futures_precise(
    codes: list[tuple[str, str]] | None = None,
    top_n: int = 3,
    min_confidence: float = MIN_CONFIDENCE,
    min_agree_layers: int = MIN_AGREE_LAYERS,
    profile: str | None = "precise",
) -> list[PrecisionPrediction]:
    """期货高精度预测. profile=precise|research|explore."""
    from .predict import _load_futures_prices

    universe = codes or [(s, n) for s, n, *_ in
                         [("IF", "沪深300"), ("IC", "中证500"), ("IH", "上证50"),
                          ("RB", "螺纹钢"), ("AU", "沪金"), ("CU", "沪铜"),
                          ("SC", "原油"), ("M", "豆粕"), ("CF", "棉花")]]

    def _load(sym):
        return _load_futures_prices(sym)

    return predict_batch(
        universe, _load, top_n, min_confidence, min_agree_layers, profile=profile,
    )
