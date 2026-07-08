"""策略打法库 — 多套可切换的交易策略.

每套打法针对不同市场环境优化:
  - 进攻型: 牛市追涨
  - 防守型: 熊市控回撤
  - 均衡型: 震荡市稳健
  - 抄底型: 极端恐慌时使用
  - 趋势型: 强趋势市场
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .market_context import MarketRegime, SentimentLevel


class PlaybookStyle(str, Enum):
    AGGRESSIVE = "进攻型"
    DEFENSIVE = "防守型"
    BALANCED = "均衡型"
    CONTRARIAN = "抄底型"
    TREND = "趋势型"


@dataclass
class Playbook:
    """策略打法定义."""
    name: str
    style: PlaybookStyle
    description: str
    # 适用条件
    suitable_regimes: list[MarketRegime]
    suitable_sentiments: list[SentimentLevel]
    # 仓位参数
    max_position_pct: float       # 单票最大仓位
    max_total_exposure: float     # 最大总敞口
    min_cash_reserve: float       # 最低现金保留
    # 因子权重覆盖
    factor_weights: dict[str, float] = field(default_factory=dict)
    # 筛选门槛
    min_score: float = 60.0       # 最低综合分
    min_confidence: float = 0.5   # 最低置信度
    # 风控参数
    stop_loss_pct: float = 0.08   # 止损百分比
    trailing_stop_pct: float = 0.05  # 移动止损
    take_profit_pct: float = 0.15    # 止盈百分比
    max_holding_days: int = 30       # 最大持仓天数
    # 其他
    notes: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════
# 预定义打法
# ═══════════════════════════════════════════════════════════════════════

PLAYBOOKS: dict[str, Playbook] = {
    "aggressive": Playbook(
        name="进攻型",
        style=PlaybookStyle.AGGRESSIVE,
        description="牛市追涨, 追求高收益, 接受较高波动",
        suitable_regimes=[MarketRegime.BULL],
        suitable_sentiments=[SentimentLevel.NEUTRAL, SentimentLevel.GREED],
        max_position_pct=0.25,
        max_total_exposure=0.85,
        min_cash_reserve=0.15,
        factor_weights={
            "动量": 0.35,
            "趋势": 0.30,
            "成交量": 0.15,
            "波动率": 0.10,
            "均值回归": 0.10,
        },
        min_score=65.0,
        min_confidence=0.6,
        stop_loss_pct=0.07,
        trailing_stop_pct=0.05,
        take_profit_pct=0.20,
        max_holding_days=20,
        notes=[
            "强势市场追涨, 快速止盈",
            "动量+趋势双重确认",
            "严格止损, 防止假突破",
        ],
    ),

    "defensive": Playbook(
        name="防守型",
        style=PlaybookStyle.DEFENSIVE,
        description="熊市控回撤, 优先保本, 等待确定性机会",
        suitable_regimes=[MarketRegime.BEAR, MarketRegime.VOLATILE],
        suitable_sentiments=[SentimentLevel.FEAR, SentimentLevel.EXTREME_FEAR],
        max_position_pct=0.08,
        max_total_exposure=0.40,
        min_cash_reserve=0.60,
        factor_weights={
            "波动率": 0.30,
            "均值回归": 0.25,
            "成交量": 0.20,
            "趋势": 0.15,
            "动量": 0.10,
        },
        min_score=75.0,
        min_confidence=0.7,
        stop_loss_pct=0.05,
        trailing_stop_pct=0.03,
        take_profit_pct=0.10,
        max_holding_days=10,
        notes=[
            "高门槛, 只做最确定的机会",
            "波动率因子优先, 选低波动标的",
            "小仓位, 快进快出",
        ],
    ),

    "balanced": Playbook(
        name="均衡型",
        style=PlaybookStyle.BALANCED,
        description="震荡市稳健, 攻守兼备, 追求风险调整后收益",
        suitable_regimes=[MarketRegime.SIDEWAYS],
        suitable_sentiments=[SentimentLevel.NEUTRAL],
        max_position_pct=0.15,
        max_total_exposure=0.65,
        min_cash_reserve=0.35,
        factor_weights={
            "动量": 0.20,
            "趋势": 0.20,
            "成交量": 0.15,
            "波动率": 0.20,
            "均值回归": 0.25,
        },
        min_score=62.0,
        min_confidence=0.55,
        stop_loss_pct=0.06,
        trailing_stop_pct=0.04,
        take_profit_pct=0.12,
        max_holding_days=15,
        notes=[
            "均值回归权重较高, 高抛低吸",
            "中等仓位, 分散风险",
            "稳健为主, 不追涨杀跌",
        ],
    ),

    "contrarian": Playbook(
        name="抄底型",
        style=PlaybookStyle.CONTRARIAN,
        description="极端恐慌时逆向布局, 高风险高回报",
        suitable_regimes=[MarketRegime.BEAR],
        suitable_sentiments=[SentimentLevel.EXTREME_FEAR],
        max_position_pct=0.12,
        max_total_exposure=0.50,
        min_cash_reserve=0.50,
        factor_weights={
            "均值回归": 0.40,
            "波动率": 0.25,
            "成交量": 0.15,
            "趋势": 0.10,
            "动量": 0.10,
        },
        min_score=55.0,  # 门槛放低, 因为是逆向
        min_confidence=0.4,
        stop_loss_pct=0.08,
        trailing_stop_pct=0.04,
        take_profit_pct=0.25,  # 高止盈目标
        max_holding_days=30,
        notes=[
            "极度恐慌时逆向布局",
            "均值回归为核心, 选超跌标的",
            "分批建仓, 不要一次all in",
            "严格止损, 防止接飞刀",
        ],
    ),

    "trend": Playbook(
        name="趋势型",
        style=PlaybookStyle.TREND,
        description="强趋势市场顺势而为, 让利润奔跑",
        suitable_regimes=[MarketRegime.BULL],
        suitable_sentiments=[SentimentLevel.NEUTRAL, SentimentLevel.GREED],
        max_position_pct=0.20,
        max_total_exposure=0.75,
        min_cash_reserve=0.25,
        factor_weights={
            "趋势": 0.35,
            "动量": 0.30,
            "成交量": 0.15,
            "波动率": 0.10,
            "均值回归": 0.10,
        },
        min_score=68.0,
        min_confidence=0.65,
        stop_loss_pct=0.10,
        trailing_stop_pct=0.06,
        take_profit_pct=0.30,  # 高止盈, 让利润奔跑
        max_holding_days=40,
        notes=[
            "趋势+动量双重确认",
            "移动止损保护利润",
            "高止盈目标, 截断亏损让利润奔跑",
        ],
    ),
}


# ═══════════════════════════════════════════════════════════════════════
# 打法选择逻辑
# ═══════════════════════════════════════════════════════════════════════

def select_playbook(
    regime: MarketRegime,
    sentiment: SentimentLevel,
    custom_style: PlaybookStyle | None = None,
) -> Playbook:
    """根据市场环境选择最合适的打法.

    Args:
        regime: 市场状态
        sentiment: 市场情绪
        custom_style: 用户指定风格 (覆盖自动选择)

    Returns:
        Playbook: 最合适的打法
    """
    # 用户指定优先
    if custom_style:
        style_map = {
            PlaybookStyle.AGGRESSIVE: "aggressive",
            PlaybookStyle.DEFENSIVE: "defensive",
            PlaybookStyle.BALANCED: "balanced",
            PlaybookStyle.CONTRARIAN: "contrarian",
            PlaybookStyle.TREND: "trend",
        }
        return PLAYBOOKS.get(style_map.get(custom_style, "balanced"), PLAYBOOKS["balanced"])

    # 自动选择
    # 极端恐慌 → 抄底型
    if sentiment == SentimentLevel.EXTREME_FEAR:
        return PLAYBOOKS["contrarian"]

    # 熊市或高波动 → 防守型
    if regime in (MarketRegime.BEAR, MarketRegime.VOLATILE):
        return PLAYBOOKS["defensive"]

    # 牛市 + 贪婪 → 趋势型
    if regime == MarketRegime.BULL and sentiment in (SentimentLevel.GREED, SentimentLevel.EXTREME_GREED):
        return PLAYBOOKS["trend"]

    # 牛市 + 中性 → 进攻型
    if regime == MarketRegime.BULL:
        return PLAYBOOKS["aggressive"]

    # 震荡 → 均衡型
    return PLAYBOOKS["balanced"]


def get_playbook_by_name(name: str) -> Playbook | None:
    """按名称获取打法."""
    for pb in PLAYBOOKS.values():
        if pb.name == name:
            return pb
    return None


def list_playbooks() -> list[dict]:
    """列出所有打法."""
    return [
        {
            "id": k,
            "name": v.name,
            "style": v.style.value,
            "description": v.description,
            "max_position": f"{v.max_position_pct:.0%}",
            "max_exposure": f"{v.max_total_exposure:.0%}",
            "stop_loss": f"{v.stop_loss_pct:.0%}",
            "take_profit": f"{v.take_profit_pct:.0%}",
            "notes": v.notes,
        }
        for k, v in PLAYBOOKS.items()
    ]


def format_playbook(pb: Playbook) -> str:
    """格式化打法详情."""
    lines = [
        f"=== {pb.name} ({pb.style.value}) ===",
        f"描述: {pb.description}",
        "",
        "仓位参数:",
        f"  单票最大仓位: {pb.max_position_pct:.0%}",
        f"  最大总敞口: {pb.max_total_exposure:.0%}",
        f"  最低现金保留: {pb.min_cash_reserve:.0%}",
        "",
        "风控参数:",
        f"  止损: {pb.stop_loss_pct:.0%}",
        f"  移动止损: {pb.trailing_stop_pct:.0%}",
        f"  止盈: {pb.take_profit_pct:.0%}",
        f"  最大持仓天数: {pb.max_holding_days}",
        "",
        "因子权重:",
    ]
    for k, v in pb.factor_weights.items():
        lines.append(f"  {k}: {v:.0%}")

    if pb.notes:
        lines.append("")
        lines.append("策略要点:")
        for note in pb.notes:
            lines.append(f"  - {note}")

    return "\n".join(lines)
