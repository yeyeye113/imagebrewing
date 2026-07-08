"""市场环境检测 + 动态权重 + 资金流向。

Iteration 7: MarketRegime — 基于均线排列自动判断牛/熊/震荡
Iteration 8: DynamicWeights — 根据MarketRegime调整评分维度权重
Iteration 9: MoneyFlowIndicator — 资金流向估算 (大单净流入/流出)
Iteration 10: 单元测试
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .common import ScanConfig

logger = logging.getLogger("quanttrader.scanner.regime")


# ══════════════════════════════════════════════════════════════════
# Iteration 7: MarketRegime
# ══════════════════════════════════════════════════════════════════


class Regime(Enum):
    BULL = "bull"
    BEAR = "bear"
    SIDEWAYS = "sideways"


@dataclass
class RegimeSignal:
    regime: Regime
    confidence: float  # 0-1
    ma排列: str  # "多头排列"/"空头排列"/"纠缠"
    breadth: float  # 涨跌比 (涨家数/总数)
    avg_chg: float  # 平均涨跌幅
    reasoning: str


class MarketRegimeDetector:
    """基于均线排列和市场广度判断当前市场环境。

    判断逻辑:
    - 牛市: 价格>SMA5>SMA10>SMA20 且 涨跌比>0.55
    - 熊市: 价格<SMA5<SMA10<SMA20 且 涨跌比<0.45
    - 震荡: 其他情况
    """

    def detect_from_batch(self, stocks: list[dict[str, Any]]) -> RegimeSignal:
        """从批量股票数据判断市场环境。"""
        if not stocks:
            return RegimeSignal(Regime.SIDEWAYS, 0.5, "数据不足", 0.5, 0.0, "无数据")

        # 统计涨跌
        total = len(stocks)
        up_count = sum(1 for s in stocks if s.get("chg_pct", 0) > 0)
        down_count = sum(1 for s in stocks if s.get("chg_pct", 0) < 0)
        flat_count = total - up_count - down_count

        breadth = up_count / max(total, 1)
        avg_chg = sum(s.get("chg_pct", 0) for s in stocks) / max(total, 1)

        # 均线排列分析 (用 trend_pct 代替)
        # trend_pct > 0 表示在SMA10之上
        above_sma10 = sum(1 for s in stocks if s.get("trend_pct", 0) > 0)
        above_ratio = above_sma10 / max(total, 1)

        # mom_5d > 0 表示短期趋势向上
        mom_up = sum(1 for s in stocks if s.get("mom_5d", 0) > 0)
        mom_ratio = mom_up / max(total, 1)

        # 综合判断
        bull_score = 0.0
        bear_score = 0.0

        # 涨跌比
        bull_score += breadth * 30
        bear_score += (1 - breadth) * 30

        # 均线位置
        bull_score += above_ratio * 35
        bear_score += (1 - above_ratio) * 35

        # 短期动量
        bull_score += mom_ratio * 25
        bear_score += (1 - mom_ratio) * 25

        # 平均涨跌幅
        if avg_chg > 1:
            bull_score += 10
        elif avg_chg < -1:
            bear_score += 10
        elif avg_chg > 0:
            bull_score += 5
        else:
            bear_score += 5

        # 判定
        if bull_score > 65 and breadth > 0.55 and above_ratio > 0.55:
            regime = Regime.BULL
            conf = min((bull_score - 50) / 30, 1.0)
            ma排列 = "多头排列"
            reasoning = f"涨跌比{breadth:.0%} 均线站上{above_ratio:.0%} 动量{mom_ratio:.0%}"
        elif bear_score > 65 and breadth < 0.45 and above_ratio < 0.45:
            regime = Regime.BEAR
            conf = min((bear_score - 50) / 30, 1.0)
            ma排列 = "空头排列"
            reasoning = f"涨跌比{breadth:.0%} 均线跌破{above_ratio:.0%} 动量反向{1-mom_ratio:.0%}"
        else:
            regime = Regime.SIDEWAYS
            conf = max(0.3, 1 - abs(bull_score - bear_score) / 30)
            ma排列 = "纠缠"
            reasoning = f"多空均衡 多{bull_score:.0f}/空{bear_score:.0f} 涨跌比{breadth:.0%}"

        return RegimeSignal(
            regime=regime,
            confidence=round(conf, 2),
            ma排列=ma排列,
            breadth=round(breadth, 3),
            avg_chg=round(avg_chg, 2),
            reasoning=reasoning,
        )


# ══════════════════════════════════════════════════════════════════
# Iteration 8: Dynamic Weights
# ══════════════════════════════════════════════════════════════════


def get_regime_weights(regime: Regime) -> dict[str, float]:
    """根据市场环境返回调整后的评分权重。

    - 牛市: 重动量 (追涨), 轻换手
    - 熊市: 重换手 (活跃度=防御), 轻动量
    - 震荡: 重成交额 (资金关注), 均衡配置
    """
    if regime == Regime.BULL:
        return {
            "w_amount": 25.0,
            "w_turnover": 15.0,
            "w_momentum": 30.0,  # 动量优先
            "w_direction": 20.0,  # 方向加分
            "w_vol_ratio": 10.0,
        }
    elif regime == Regime.BEAR:
        return {
            "w_amount": 20.0,
            "w_turnover": 30.0,  # 换手率=活跃=防御
            "w_momentum": 15.0,
            "w_direction": 10.0,
            "w_vol_ratio": 25.0,  # 量比=资金异动
        }
    else:  # SIDEWAYS
        return {
            "w_amount": 30.0,  # 成交额=资金关注
            "w_turnover": 25.0,
            "w_momentum": 15.0,
            "w_direction": 15.0,
            "w_vol_ratio": 15.0,
        }


def apply_dynamic_weights(config: ScanConfig, regime: Regime) -> ScanConfig:
    """应用动态权重到配置。返回新配置 (不修改原配置)。"""
    weights = get_regime_weights(regime)
    new_cfg = ScanConfig(
        min_price=config.min_price,
        max_price=config.max_price,
        min_turnover_pct=config.min_turnover_pct,
        min_amount_yi=config.min_amount_yi,
        limit_threshold=config.limit_threshold,
        top_n=config.top_n,
        kline_days=config.kline_days,
        kline_fetch_ratio=config.kline_fetch_ratio,
        w_amount=weights["w_amount"],
        w_turnover=weights["w_turnover"],
        w_momentum=weights["w_momentum"],
        w_direction=weights["w_direction"],
        w_vol_ratio=weights["w_vol_ratio"],
        boost_top10=config.boost_top10,
        boost_top25=config.boost_top25,
        boost_top50=config.boost_top50,
        divination_weight=config.divination_weight,
        mode=config.mode,
        use_divination=config.use_divination,
    )
    return new_cfg


# ══════════════════════════════════════════════════════════════════
# Iteration 9: MoneyFlowIndicator
# ══════════════════════════════════════════════════════════════════


@dataclass
class MoneyFlow:
    """单只股票资金流向。"""
    code: str
    net_inflow_yi: float  # 净流入 (亿), 正=流入, 负=流出
    big_order_ratio: float  # 大单占比
    signal: str  # "inflow" / "outflow" / "neutral"
    strength: float  # 0-1 信号强度


class MoneyFlowDetector:
    """基于量价关系估算资金流向。

    真正的大单数据需要Level2, 这里用:
    1. 量比 > 1.5 + 涨 = 主力流入
    2. 量比 > 1.5 + 跌 = 主力流出
    3. 换手率异常 = 资金异动
    """

    def detect(self, stocks: list[dict[str, Any]]) -> dict[str, MoneyFlow]:
        """检测批量资金流向。"""
        results: dict[str, MoneyFlow] = {}

        # 计算换手率中位数 (基准)
        turnovers = [s.get("turnover", 0) for s in stocks if s.get("turnover", 0) > 0]
        median_turn = sorted(turnovers)[len(turnovers) // 2] if turnovers else 5.0

        for s in stocks:
            code = s.get("code", "")
            chg = s.get("chg_pct", 0)
            vr = s.get("vol_ratio", 1.0)
            turnover = s.get("turnover", 0)
            amount = s.get("amount_yi", 0)

            # 换手率异常度
            turn_ratio = turnover / max(median_turn, 1)

            # 资金流向估算
            if vr > 1.5 and chg > 0.5:
                # 放量上涨 → 流入
                net = amount * (vr - 1) * 0.3  # 粗估
                signal = "inflow"
                strength = min((vr - 1) * 0.4 + min(chg / 5, 0.5), 1.0)
            elif vr > 1.5 and chg < -0.5:
                # 放量下跌 → 流出
                net = -amount * (vr - 1) * 0.3
                signal = "outflow"
                strength = min((vr - 1) * 0.4 + min(abs(chg) / 5, 0.5), 1.0)
            elif vr < 0.7 and chg > 1:
                # 缩量上涨 → 可能是散户行为, 弱流入
                net = amount * 0.05
                signal = "inflow"
                strength = 0.2
            elif vr < 0.7 and chg < -1:
                # 缩量下跌 → 恐慌, 弱流出
                net = -amount * 0.05
                signal = "outflow"
                strength = 0.2
            else:
                net = 0
                signal = "neutral"
                strength = 0.0

            results[code] = MoneyFlow(
                code=code,
                net_inflow_yi=round(net / 1e8, 2),
                big_order_ratio=round(min(turn_ratio * vr * 0.3, 1.0), 2),
                signal=signal,
                strength=round(strength, 2),
            )

        return results

    def get_bonus(self, code: str, flows: dict[str, MoneyFlow]) -> float:
        """获取资金流向加分 (-3 ~ +3)。"""
        flow = flows.get(code)
        if not flow or flow.signal == "neutral":
            return 0.0
        if flow.signal == "inflow":
            return round(flow.strength * 3, 1)
        else:
            return round(-flow.strength * 3, 1)
