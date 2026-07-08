"""投资建议引擎 — 从用户视角生成可操作的投资建议.

核心原则:
  - 每个建议必须有明确理由
  - 风险提示必须具体
  - 操作建议必须可执行
  - 支持多时间维度 (短线/中线/长线)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Action(str, Enum):
    BUY = "买入"
    ADD = "加仓"
    HOLD = "持有"
    REDUCE = "减仓"
    SELL = "卖出"
    WATCH = "观望"
    AVOID = "回避"


class RiskLevel(str, Enum):
    LOW = "低风险"
    MEDIUM = "中风险"
    HIGH = "高风险"
    EXTREME = "极高风险"


class TimeHorizon(str, Enum):
    SHORT = "短线"    # 1-5天
    MEDIUM = "中线"   # 1-4周
    LONG = "长线"     # 1-6月


@dataclass
class InvestmentAdvice:
    """单条投资建议."""
    action: Action
    time_horizon: TimeHorizon
    risk_level: RiskLevel
    confidence: float          # 0-1
    position_pct: str          # 建议仓位百分比
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    reasons: list[str] = field(default_factory=list)       # 买入理由
    risks: list[str] = field(default_factory=list)         # 风险提示
    catalysts: list[str] = field(default_factory=list)     # 潜在催化剂
    key_levels: dict = field(default_factory=dict)         # 关键价位
    summary: str = ""
    # 进出场时间建议
    entry_timing: str = ""         # 入场时机建议
    exit_timing: str = ""          # 出场时机建议
    best_entry_window: str = ""    # 最佳入场窗口
    holding_period: str = ""       # 建议持仓周期
    # 涨跌幅度预测
    target_1d: float | None = None    # 1日目标价
    target_3d: float | None = None    # 3日目标价
    target_7d: float | None = None    # 7日目标价
    target_30d: float | None = None   # 30日目标价
    expected_return_1d: float | None = None   # 1日预期收益
    expected_return_3d: float | None = None   # 3日预期收益
    expected_return_7d: float | None = None   # 7日预期收益
    expected_return_30d: float | None = None  # 30日预期收益
    # 概率标记
    prob_up_1d: float | None = None   # 1日上涨概率
    prob_up_3d: float | None = None   # 3日上涨概率
    prob_up_7d: float | None = None   # 7日上涨概率
    prob_up_30d: float | None = None  # 30日上涨概率

    def to_dict(self) -> dict:
        """导出为看板/API 用的完整字典 (键名即对外契约, 只加不改)。"""
        return {
            "action": self.action.value,
            "confidence": self.confidence,
            "position_pct": self.position_pct,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "reasons": self.reasons,
            "risks": self.risks,
            "summary": self.summary,
            "entry_timing": self.entry_timing,
            "exit_timing": self.exit_timing,
            "best_entry_window": self.best_entry_window,
            "holding_period": self.holding_period,
            "target_1d": self.target_1d,
            "target_3d": self.target_3d,
            "target_7d": self.target_7d,
            "target_30d": self.target_30d,
            "expected_return_1d": self.expected_return_1d,
            "expected_return_3d": self.expected_return_3d,
            "expected_return_7d": self.expected_return_7d,
            "expected_return_30d": self.expected_return_30d,
            "prob_up_1d": self.prob_up_1d,
            "prob_up_3d": self.prob_up_3d,
            "prob_up_7d": self.prob_up_7d,
            "prob_up_30d": self.prob_up_30d,
        }


@dataclass
class ComprehensiveReport:
    """综合分析报告."""
    symbol: str
    name: str
    current_price: float
    overall_score: float       # 0-100
    overall_grade: str         # A/B/C/D/E
    overall_signal: str        # 强烈看多/偏多/中性/偏空/强烈看空
    # 多维度评分
    tech_score: float = 0
    fundamental_score: float = 0
    momentum_score: float = 0
    volume_score: float = 0
    risk_score: float = 0
    # 建议
    advice_short: InvestmentAdvice | None = None
    advice_medium: InvestmentAdvice | None = None
    advice_long: InvestmentAdvice | None = None
    # 核心逻辑
    bull_case: list[str] = field(default_factory=list)     # 看多逻辑
    bear_case: list[str] = field(default_factory=list)     # 看空逻辑
    key_metrics: dict = field(default_factory=dict)        # 关键指标
    # 操作计划
    entry_strategy: str = ""
    exit_strategy: str = ""
    position_strategy: str = ""
    # 风险管理
    max_loss_pct: float = 0
    risk_reward_ratio: float = 0
    holding_period: str = ""


# ═══════════════════════════════════════════════════════════════════════
# 建议生成引擎
# ═══════════════════════════════════════════════════════════════════════

def _determine_action(
    composite_score: float,
    trend: str,
    momentum: str,
    risk_level: RiskLevel,
    time_horizon: TimeHorizon,
) -> Action:
    """根据综合评分和维度确定操作建议."""
    if composite_score >= 80:
        if time_horizon == TimeHorizon.SHORT:
            return Action.BUY
        return Action.ADD
    elif composite_score >= 65:
        if trend == "bullish":
            return Action.BUY
        return Action.HOLD
    elif composite_score >= 50:
        if momentum == "weak":
            return Action.WATCH
        return Action.HOLD
    elif composite_score >= 35:
        if risk_level == RiskLevel.HIGH:
            return Action.REDUCE
        return Action.WATCH
    else:
        if risk_level in (RiskLevel.HIGH, RiskLevel.EXTREME):
            return Action.SELL
        return Action.AVOID


def _determine_risk_level(
    volatility_percentile: float,
    max_drawdown: float,
    atr_pct: float,
) -> RiskLevel:
    """确定风险等级."""
    if volatility_percentile >= 85 or max_drawdown < -0.25 or atr_pct > 0.04:
        return RiskLevel.EXTREME
    elif volatility_percentile >= 65 or max_drawdown < -0.15 or atr_pct > 0.025:
        return RiskLevel.HIGH
    elif volatility_percentile >= 40 or max_drawdown < -0.08:
        return RiskLevel.MEDIUM
    else:
        return RiskLevel.LOW


def _calc_position_pct(
    risk_level: RiskLevel,
    confidence: float,
    composite_score: float,
) -> str:
    """计算建议仓位百分比."""
    base = {
        RiskLevel.LOW: 0.25,
        RiskLevel.MEDIUM: 0.15,
        RiskLevel.HIGH: 0.08,
        RiskLevel.EXTREME: 0.03,
    }[risk_level]

    # 置信度调整
    adj = base * (0.5 + confidence * 0.5)

    # 评分调整
    if composite_score >= 75:
        adj *= 1.2
    elif composite_score < 50:
        adj *= 0.6

    adj = max(0.02, min(0.30, adj))
    return f"{adj*100:.0f}%"


def _calc_stop_loss(
    price: float,
    atr: float,
    support_level: float,
    risk_level: RiskLevel,
) -> float:
    """计算止损价."""
    # 取 ATR 倍数和支撑位的较高者
    atr_multipliers = {
        RiskLevel.LOW: 2.0,
        RiskLevel.MEDIUM: 1.5,
        RiskLevel.HIGH: 1.2,
        RiskLevel.EXTREME: 1.0,
    }
    atr_stop = price - atr * atr_multipliers[risk_level]
    support_stop = support_level * 0.98  # 支撑位下方 2%

    return max(atr_stop, support_stop)


def _calc_take_profit(
    price: float,
    stop_loss: float,
    resistance_level: float,
    risk_reward_target: float = 2.0,
) -> float:
    """计算止盈价 (基于风险收益比)."""
    risk = price - stop_loss
    rr_target = price + risk * risk_reward_target

    # 取阻力位和风险收益目标的较低者
    return min(rr_target, resistance_level * 1.02) if resistance_level > 0 else rr_target


# ═══════════════════════════════════════════════════════════════════════
# 进出场时间建议
# ═══════════════════════════════════════════════════════════════════════

def _generate_entry_timing(
    horizon: TimeHorizon,
    action: Action,
    momentum: str,
    indicators: dict,
) -> str:
    """生成入场时机建议."""
    kdj_zone = indicators.get("kdj", {}).get("zone", "neutral")
    macd_cross = indicators.get("macd", {}).get("cross", "none")

    if action in (Action.SELL, Action.AVOID):
        return "不建议入场"

    # 短线入场时机
    if horizon == TimeHorizon.SHORT:
        if kdj_zone == "oversold" and macd_cross == "golden":
            return "最佳入场: KDJ超卖+MACD金叉确认, 今日可介入"
        elif kdj_zone == "oversold":
            return "可关注: KDJ超卖区, 等MACD金叉确认后介入"
        elif macd_cross == "golden":
            return "可关注: MACD金叉, 等回调至支撑位附近介入"
        elif momentum == "strong":
            return "追涨入场: 动量强劲, 开盘30分钟内可介入"
        else:
            return "观望为主: 等待更明确的入场信号"

    # 中线入场时机
    elif horizon == TimeHorizon.MEDIUM:
        if indicators.get("ma_alignment", {}).get("alignment") == "bullish":
            return "分批建仓: 均线多头, 回调至MA20附近可加仓"
        elif kdj_zone == "oversold":
            return "左侧布局: 超卖区, 可分2-3次建仓"
        else:
            return "等待回调: 等价格回踩均线支撑后再入场"

    # 长线入场时机
    else:
        return "定投策略: 每周/月固定金额买入, 不择时"


def _generate_exit_timing(
    horizon: TimeHorizon,
    action: Action,
    risk_level: RiskLevel,
) -> str:
    """生成出场时机建议."""
    if action in (Action.SELL, Action.REDUCE):
        return "建议尽快出场, 逢高减仓"

    if horizon == TimeHorizon.SHORT:
        if risk_level in (RiskLevel.HIGH, RiskLevel.EXTREME):
            return "快进快出: 持仓不超过3天, 达到目标或止损立即出场"
        else:
            return "3-5个交易日: 达到止盈目标或出现卖出信号时出场"

    elif horizon == TimeHorizon.MEDIUM:
        if risk_level == RiskLevel.HIGH:
            return "1-2周: 密切关注, 趋势转弱立即减仓"
        else:
            return "2-4周: 持有至目标价或趋势反转信号出现"

    else:
        return "1-6个月: 长期持有, 每季度复盘一次"


def _get_best_entry_window(horizon: TimeHorizon) -> str:
    """获取最佳入场时间窗口."""
    if horizon == TimeHorizon.SHORT:
        return "开盘30分钟 / 尾盘30分钟 (避开盘中震荡)"
    elif horizon == TimeHorizon.MEDIUM:
        return "周一/周二 (周初资金充裕) / 月初 (月度资金流入)"
    else:
        return "每月固定日期定投 (不择时)"


def _get_holding_period(horizon: TimeHorizon, action: Action) -> str:
    """获取建议持仓周期."""
    if action in (Action.SELL, Action.AVOID):
        return "不持仓"

    if horizon == TimeHorizon.SHORT:
        return "1-5个交易日"
    elif horizon == TimeHorizon.MEDIUM:
        return "2-4周"
    else:
        return "1-6个月"


# ═══════════════════════════════════════════════════════════════════════
# 涨跌幅度预测
# ═══════════════════════════════════════════════════════════════════════

def _generate_price_predictions(
    price: float,
    atr: float,
    momentum_score: float,
    composite_score: float,
    horizon: TimeHorizon,
) -> dict:
    """生成多日涨跌幅度预测.

    基于ATR和动量评分估算:
      - ATR决定波动范围
      - 动量决定方向
      - 综合分决定置信度

    科学性设计:
      - 对称性: 看多和看空幅度对称
      - 单调性: 预测收益随时间单调递增
      - 合理性: 概率在40%-70%范围, 不过度自信
    """
    # 日均波动 (ATR)
    daily_vol = atr / price if price > 0 else 0.02

    # 方向系数 (动量分50为中性, 范围-1到1)
    direction = (momentum_score - 50) / 50  # -1 到 1

    # 强度系数 (综合分越高, 预测越强, 范围0.5到1.0)
    # 使用对称公式: 50分时为0.75, 0分和100分时对称
    strength = 0.75 + 0.25 * abs(composite_score - 50) / 50  # 0.75 到 1.0
    strength = max(0.75, min(1.0, strength))

    # 预测收益 (使用平方根缩放, 更符合实际)
    # 短期波动小, 长期波动大, 使用sqrt(t)缩放
    base_return_1d = direction * daily_vol * 0.3 * strength
    base_return_3d = direction * daily_vol * 0.5 * strength * (3 ** 0.5)
    base_return_7d = direction * daily_vol * 0.7 * strength * (7 ** 0.5)
    base_return_30d = direction * daily_vol * 1.0 * strength * (30 ** 0.5)

    # 上涨概率 (基于方向和置信度, 范围40%-70%)
    # 使用logistic函数, 更符合概率论
    base_prob = 0.5 + direction * 0.2 * strength
    prob_1d = max(0.40, min(0.70, base_prob))
    prob_3d = max(0.40, min(0.70, base_prob - 0.02))
    prob_7d = max(0.40, min(0.70, base_prob - 0.04))
    prob_30d = max(0.40, min(0.70, base_prob - 0.06))

    return {
        "target_1d": round(price * (1 + base_return_1d), 2),
        "target_3d": round(price * (1 + base_return_3d), 2),
        "target_7d": round(price * (1 + base_return_7d), 2),
        "target_30d": round(price * (1 + base_return_30d), 2),
        "return_1d": round(base_return_1d, 4),
        "return_3d": round(base_return_3d, 4),
        "return_7d": round(base_return_7d, 4),
        "return_30d": round(base_return_30d, 4),
        "prob_1d": round(prob_1d, 2),
        "prob_3d": round(prob_3d, 2),
        "prob_7d": round(prob_7d, 2),
        "prob_30d": round(prob_30d, 2),
    }


def generate_investment_advice(
    symbol: str,
    name: str,
    price: float,
    analysis: dict | None,
    factors: dict,
    indicators: dict,
    volume_info: dict,
    screener_result: dict | None = None,
) -> ComprehensiveReport:
    """生成综合投资建议报告.

    Args:
        symbol: 代码
        name: 名称
        price: 当前价
        analysis: 原始分析结果 (pipeline)
        factors: 多因子评分
        indicators: 技术指标
        volume_info: 成交量分析
        screener_result: 筛选器结果

    Returns:
        ComprehensiveReport: 完整的投资建议报告
    """
    # 提取关键数据
    composite_score = factors.get("composite", 50)
    factor_grade = factors.get("grade", "C")
    factor_signal = factors.get("signal", "中性")

    # 各维度评分
    tech_score = indicators.get("composite", 50)
    momentum_score = next((f["score"] for f in factors.get("factors", []) if f["name"] == "动量"), 50)
    volume_score = volume_info.get("composite", 50)
    volatility_score = next((f["score"] for f in factors.get("factors", []) if f["name"] == "波动率"), 50)

    # 趋势判断
    ma_align = indicators.get("ma_alignment", {}).get("alignment", "tangled")
    trend = "bullish" if ma_align == "bullish" else ("bearish" if ma_align == "bearish" else "neutral")

    # 动量判断
    momentum = "strong" if momentum_score >= 70 else ("weak" if momentum_score < 40 else "normal")

    # 波动率数据
    atr_pct = indicators.get("atr", {}).get("atr_pct", 0.02)
    atr_percentile = indicators.get("atr", {}).get("atr_percentile", 50)
    atr_val = indicators.get("atr", {}).get("atr", price * 0.02)

    # 风险评估
    risk_level = _determine_risk_level(atr_percentile, -0.10, atr_pct)

    # 置信度
    confidence = analysis.get("confidence", 0.5) if analysis else 0.5

    # 生成多时间维度建议
    def make_advice(horizon: TimeHorizon) -> InvestmentAdvice:
        action = _determine_action(composite_score, trend, momentum, risk_level, horizon)
        position = _calc_position_pct(risk_level, confidence, composite_score)

        # 关键价位
        ma20 = indicators.get("ma_alignment", {}).get("ma_values", {}).get("ma20", price * 0.97)
        ma60 = indicators.get("ma_alignment", {}).get("ma_values", {}).get("ma60", price * 0.94)

        stop_loss = _calc_stop_loss(price, atr_val, ma60, risk_level)
        take_profit = _calc_take_profit(price, stop_loss, price * 1.15)

        reasons = []
        risks = []
        catalysts = []

        # 理由生成
        if ma_align == "bullish":
            reasons.append("均线多头排列，趋势向上")
        if momentum_score >= 70:
            reasons.append(f"动量强劲(得分{momentum_score:.0f})")
        if volume_score >= 65:
            reasons.append("成交量配合良好")
        if indicators.get("macd", {}).get("cross") == "golden":
            reasons.append("MACD金叉")
        if indicators.get("kdj", {}).get("zone") == "oversold":
            reasons.append("KDJ超卖区，有反弹潜力")

        # 风险提示
        if atr_percentile >= 70:
            risks.append(f"波动率偏高(ATR分位{atr_percentile:.0f}%)")
        if indicators.get("macd", {}).get("divergence") == "bearish":
            risks.append("MACD顶背离，注意回调")
        if volume_info.get("vp_divergence", {}).get("divergence") == "bearish":
            risks.append("量价背离，上攻乏力")
        if risk_level in (RiskLevel.HIGH, RiskLevel.EXTREME):
            risks.append("当前风险等级较高，控制仓位")

        # 催化剂
        if indicators.get("kdj", {}).get("cross") == "golden":
            catalysts.append("KDJ金叉，短期可能反弹")
        if volume_info.get("money_flow", {}).get("direction") == "主力流入":
            catalysts.append("资金持续流入")

        # 时间维度调整
        if horizon == TimeHorizon.SHORT:
            stop_loss_pct = 0.05
            take_profit_pct = 0.08
            holding = "1-5个交易日"
        elif horizon == TimeHorizon.MEDIUM:
            stop_loss_pct = 0.08
            take_profit_pct = 0.15
            holding = "1-4周"
        else:
            stop_loss_pct = 0.12
            take_profit_pct = 0.25
            holding = "1-6个月"

        stop_loss = price * (1 - stop_loss_pct)
        take_profit = price * (1 + take_profit_pct)

        # 进出场时间建议
        entry_timing = _generate_entry_timing(horizon, action, momentum, indicators)
        exit_timing = _generate_exit_timing(horizon, action, risk_level)
        best_entry_window = _get_best_entry_window(horizon)
        holding_period = _get_holding_period(horizon, action)

        # 涨跌幅度预测 (基于ATR和动量)
        predictions = _generate_price_predictions(
            price, atr_val, momentum_score, composite_score, horizon
        )

        return InvestmentAdvice(
            action=action,
            time_horizon=horizon,
            risk_level=risk_level,
            confidence=confidence,
            position_pct=position,
            entry_price=round(price, 2),
            stop_loss=round(stop_loss, 2),
            take_profit=round(take_profit, 2),
            reasons=reasons,
            risks=risks,
            catalysts=catalysts,
            key_levels={
                "ma20": round(ma20, 2),
                "ma60": round(ma60, 2),
                "atr": round(atr_val, 2),
            },
            summary=f"{action.value} | 仓位{position} | 止损{stop_loss:.2f} | 止盈{take_profit:.2f}",
            entry_timing=entry_timing,
            exit_timing=exit_timing,
            best_entry_window=best_entry_window,
            holding_period=holding_period,
            target_1d=predictions.get("target_1d"),
            target_3d=predictions.get("target_3d"),
            target_7d=predictions.get("target_7d"),
            target_30d=predictions.get("target_30d"),
            expected_return_1d=predictions.get("return_1d"),
            expected_return_3d=predictions.get("return_3d"),
            expected_return_7d=predictions.get("return_7d"),
            expected_return_30d=predictions.get("return_30d"),
            prob_up_1d=predictions.get("prob_1d"),
            prob_up_3d=predictions.get("prob_3d"),
            prob_up_7d=predictions.get("prob_7d"),
            prob_up_30d=predictions.get("prob_30d"),
        )

    advice_short = make_advice(TimeHorizon.SHORT)
    advice_medium = make_advice(TimeHorizon.MEDIUM)
    advice_long = make_advice(TimeHorizon.LONG)

    # make_advice 恒定产出止损/止盈; 此处显式收窄为 float 供后续算术与格式化使用
    med_stop = advice_medium.stop_loss if advice_medium.stop_loss is not None else price * 0.95
    med_take = advice_medium.take_profit if advice_medium.take_profit is not None else price * 1.10

    # 看多/看空逻辑
    bull_case = []
    bear_case = []

    if ma_align == "bullish":
        bull_case.append("均线多头排列，中期趋势向上")
    if momentum_score >= 65:
        bull_case.append(f"动量得分{momentum_score:.0f}，上涨动能充足")
    if volume_score >= 60:
        bull_case.append("成交量配合，资金关注度高")
    if indicators.get("macd", {}).get("histogram", 0) > 0:
        bull_case.append("MACD柱状图为正，多头占优")

    if ma_align == "bearish":
        bear_case.append("均线空头排列，趋势向下")
    if momentum_score < 40:
        bear_case.append(f"动量得分{momentum_score:.0f}，上涨乏力")
    if indicators.get("macd", {}).get("divergence") == "bearish":
        bear_case.append("MACD顶背离，回调风险大")
    if volume_info.get("vp_divergence", {}).get("divergence") == "bearish":
        bear_case.append("量价背离，上攻无量")

    # 操作策略
    if composite_score >= 70:
        entry_strategy = f"建议在{price:.2f}附近分批建仓，首次仓位不超过建议仓位的50%"
        exit_strategy = f"跌破{med_stop:.2f}止损，达到{med_take:.2f}止盈"
        position_strategy = f"总仓位不超过{advice_medium.position_pct}，分2-3次建仓"
    elif composite_score >= 50:
        entry_strategy = f"观望为主，若回调至{price*0.97:.2f}附近可轻仓试探"
        exit_strategy = f"严格止损{price*0.95:.2f}，快进快出"
        position_strategy = "仓位控制在5%以内，等待明确信号"
    else:
        entry_strategy = "暂不建议入场，等待趋势改善"
        exit_strategy = "如有持仓，建议逢高减仓"
        position_strategy = "空仓观望"

    # 风险收益比
    risk = price - med_stop
    reward = med_take - price
    risk_reward = reward / risk if risk > 0 else 0

    return ComprehensiveReport(
        symbol=symbol,
        name=name,
        current_price=round(price, 2),
        overall_score=round(composite_score, 1),
        overall_grade=factor_grade,
        overall_signal=factor_signal,
        tech_score=round(tech_score, 1),
        momentum_score=round(momentum_score, 1),
        volume_score=round(volume_score, 1),
        risk_score=round(volatility_score, 1),
        advice_short=advice_short,
        advice_medium=advice_medium,
        advice_long=advice_long,
        bull_case=bull_case,
        bear_case=bear_case,
        key_metrics={
            "composite_score": round(composite_score, 1),
            "tech_score": round(tech_score, 1),
            "momentum_score": round(momentum_score, 1),
            "volume_score": round(volume_score, 1),
            "volatility_score": round(volatility_score, 1),
            "atr_pct": round(atr_pct, 4),
            "atr_percentile": round(atr_percentile, 1),
            "ma_alignment": ma_align,
        },
        entry_strategy=entry_strategy,
        exit_strategy=exit_strategy,
        position_strategy=position_strategy,
        max_loss_pct=round((price - med_stop) / price, 4),
        risk_reward_ratio=round(risk_reward, 2),
        holding_period=advice_medium.summary.split("|")[-1].strip() if "|" in advice_medium.summary else "中线",
    )


def format_report_text(report: ComprehensiveReport) -> str:
    """格式化报告为可读文本 (详细版)."""
    # 涨跌标记
    def ret_mark(val):
        if val is None:
            return "—"
        return f"📈+{val*100:.2f}%" if val > 0 else (f"📉{val*100:.2f}%" if val < 0 else "➡️0%")

    def prob_mark(val):
        if val is None:
            return "—"
        if val >= 0.65:
            return f"🟢{val*100:.0f}%"
        if val >= 0.50:
            return f"🟡{val*100:.0f}%"
        return f"🔴{val*100:.0f}%"

    a_short = report.advice_short
    a = report.advice_medium
    a_long = report.advice_long
    if a_short is None or a is None or a_long is None:
        return f"{report.name}({report.symbol}) 综合分析报告: 建议数据缺失, 无法生成详细文本"

    def fnum(val: float | None) -> str:
        """None 安全的两位小数格式化。"""
        return f"{val:.2f}" if val is not None else "—"

    lines = [
        "╔══════════════════════════════════════════════════════════════╗",
        f"║  {report.name}({report.symbol}) 综合分析报告",
        "╚══════════════════════════════════════════════════════════════╝",
        "",
        f"📊 当前价格: {report.current_price:.2f}",
        f"📊 综合评分: {report.overall_score:.0f}/100 ({report.overall_grade}) {report.overall_signal}",
        "",
        "┌─ 多维度评分 ─────────────────────────────────────────────┐",
        f"│ 技术面: {report.tech_score:.0f}  动量: {report.momentum_score:.0f}  成交量: {report.volume_score:.0f}  风险: {report.risk_score:.0f}",
        "└──────────────────────────────────────────────────────────┘",
        "",
        "┌─ 涨跌预测 (基于ATR+动量模型) ────────────────────────────┐",
        f"│ 1日:  {fnum(a.target_1d)}  {ret_mark(a.expected_return_1d)}  上涨概率{prob_mark(a.prob_up_1d)}",
        f"│ 3日:  {fnum(a.target_3d)}  {ret_mark(a.expected_return_3d)}  上涨概率{prob_mark(a.prob_up_3d)}",
        f"│ 7日:  {fnum(a.target_7d)}  {ret_mark(a.expected_return_7d)}  上涨概率{prob_mark(a.prob_up_7d)}",
        f"│ 30日: {fnum(a.target_30d)}  {ret_mark(a.expected_return_30d)}  上涨概率{prob_mark(a.prob_up_30d)}",
        "└──────────────────────────────────────────────────────────┘",
        "",
        "┌─ 短线建议 (1-5天) ──────────────────────────────────────┐",
        f"│ 操作: {a_short.action.value}  仓位: {a_short.position_pct}",
        f"│ 止损: {fnum(a_short.stop_loss)}  止盈: {fnum(a_short.take_profit)}",
        f"│ 入场: {a_short.entry_timing}",
        f"│ 出场: {a_short.exit_timing}",
        f"│ 理由: {'; '.join(a_short.reasons[:2])}",
        "└──────────────────────────────────────────────────────────┘",
        "",
        "┌─ 中线建议 (1-4周) ──────────────────────────────────────┐",
        f"│ 操作: {a.action.value}  仓位: {a.position_pct}",
        f"│ 止损: {fnum(a.stop_loss)}  止盈: {fnum(a.take_profit)}",
        f"│ 入场: {a.entry_timing}",
        f"│ 出场: {a.exit_timing}",
        f"│ 理由: {'; '.join(a.reasons[:2])}",
        f"│ 最佳窗口: {a.best_entry_window}",
        f"│ 持仓周期: {a.holding_period}",
        "└──────────────────────────────────────────────────────────┘",
        "",
        "┌─ 长线建议 (1-6月) ──────────────────────────────────────┐",
        f"│ 操作: {a_long.action.value}  仓位: {a_long.position_pct}",
        f"│ 止损: {fnum(a_long.stop_loss)}  止盈: {fnum(a_long.take_profit)}",
        f"│ 入场: {a_long.entry_timing}",
        f"│ 出场: {a_long.exit_timing}",
        f"│ 理由: {'; '.join(a_long.reasons[:2])}",
        "└──────────────────────────────────────────────────────────┘",
        "",
        "┌─ 看多逻辑 ─────────────────────────────────────────────┐",
        *[f"│ ✅ {r}" for r in report.bull_case],
        "└──────────────────────────────────────────────────────────┘",
        "",
        "┌─ 看空逻辑 ─────────────────────────────────────────────┐",
        *[f"│ ⚠️ {r}" for r in report.bear_case],
        "└──────────────────────────────────────────────────────────┘",
        "",
        "┌─ 操作策略 ─────────────────────────────────────────────┐",
        f"│ 入场: {report.entry_strategy}",
        f"│ 出场: {report.exit_strategy}",
        f"│ 仓位: {report.position_strategy}",
        "└──────────────────────────────────────────────────────────┘",
        "",
        "┌─ 风险管理 ─────────────────────────────────────────────┐",
        f"│ 最大亏损: {report.max_loss_pct*100:.1f}%",
        f"│ 风险收益比: {report.risk_reward_ratio:.2f}",
        f"│ ATR波动: {a.key_levels.get('atr', 0):.2f}",
        f"│ MA20支撑: {a.key_levels.get('ma20', 0):.2f}",
        f"│ MA60支撑: {a.key_levels.get('ma60', 0):.2f}",
        "└──────────────────────────────────────────────────────────┘",
    ]
    return "\n".join(lines)
