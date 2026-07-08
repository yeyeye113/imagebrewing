"""交易评分引擎 — 100分制，4个维度。

v530波动范围: 25分
SymbolFilter方向质量: 35分
ATR止损合理性: 20分
风险收益比: 20分
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TradeScore:
    """交易评分结果。"""
    symbol: str
    direction: str  # "BUY" / "SELL"

    # 4个维度得分
    v530_score: float = 0.0       # 0-25
    direction_score: float = 0.0  # 0-35
    atr_score: float = 0.0        # 0-20
    rr_score: float = 0.0         # 0-20

    # 原始数据
    v530_range_pct: float = 0.0
    direction_tier: str = ""
    direction_win_rate: float = 0.0
    direction_sample: int = 0
    direction_avg_win: float = 0.0
    direction_avg_loss: float = 0.0
    atr_stop_distance: float = 0.0
    v530_stop_distance: float = 0.0
    stop_status: str = ""  # "正常" / "过窄" / "过宽" / "ATR兜底"
    risk_reward: float = 0.0

    @property
    def total(self) -> float:
        return self.v530_score + self.direction_score + self.atr_score + self.rr_score

    @property
    def rating(self) -> str:
        """A/B/C/D评级。"""
        t = self.total
        if t >= 80:
            return "A"
        if t >= 65:
            return "B"
        if t >= 50:
            return "C"
        return "D"

    @property
    def rating_label(self) -> str:
        return {"A": "可重点关注", "B": "可做", "C": "观察", "D": "不做"}[self.rating]

    def summary(self) -> str:
        return (
            f"[{self.rating}] {self.symbol} {self.direction} "
            f"总分={self.total:.0f} "
            f"(v530={self.v530_score:.0f} 方向={self.direction_score:.0f} "
            f"ATR={self.atr_score:.0f} 盈亏比={self.rr_score:.0f})"
        )


def score_v530(range_pct: float) -> float:
    """v530波动范围评分 (0-25)。

    <1.5%: 0分 (不做)
    1.5-2.5%: 15分 (观察)
    2.5-5%: 25分 (正常)
    >5%: 10分 (过大)
    """
    if range_pct < 1.5:
        return 0.0
    if range_pct < 2.5:
        return 15.0
    if range_pct <= 5.0:
        return 25.0
    return 10.0


def score_direction(
    tier: str,
    win_rate: float,
    sample_size: int,
    avg_win: float = 0.0,
    avg_loss: float = 0.0,
) -> float:
    """SymbolFilter方向质量评分 (0-35)。

    基于tier、胜率、样本量、盈亏比综合评分。
    """
    # Tier基础分
    tier_base = {"tier1": 20, "tier2": 15, "tier3": 8, "watch": 3, "block": 0}.get(tier, 0)

    # 胜率加分 (胜率>60%每多1%加0.3分，最高10分)
    wr_bonus = max(0, min(10, (win_rate - 55) * 0.3))

    # 样本量加分 (样本>100加3分，>200加5分)
    sample_bonus = 0
    if sample_size >= 200:
        sample_bonus = 5
    elif sample_size >= 100:
        sample_bonus = 3
    elif sample_size >= 50:
        sample_bonus = 1

    # 盈亏比加分
    rr = avg_win / avg_loss if avg_loss > 0 else 1.0
    rr_bonus = max(0, min(5, (rr - 1.0) * 5))

    return min(35, tier_base + wr_bonus + sample_bonus + rr_bonus)


def score_atr(v530_stop: float, atr_stop: float) -> tuple[float, str]:
    """ATR止损合理性评分 (0-20) 和状态判断。

    v530止损在ATR的0.8-2.0倍之间 = 正常(20分)
    v530止损 < 0.8倍ATR = 过窄(10分)
    v530止损 > 2.0倍ATR = 过宽(8分)
    """
    if atr_stop <= 0:
        return 15.0, "ATR兜底"

    ratio = v530_stop / atr_stop if atr_stop > 0 else 1.0

    if 0.8 <= ratio <= 2.0:
        return 20.0, "正常"
    if ratio < 0.8:
        return 10.0, f"过窄({ratio:.1f}x)"
    return 8.0, f"过宽({ratio:.1f}x)"


def score_risk_reward(upside_pct: float, downside_pct: float) -> float:
    """风险收益比评分 (0-20)。

    RR >= 1.5: 20分
    RR >= 1.0: 15分
    RR >= 0.8: 10分
    RR < 0.8: 5分
    """
    if downside_pct <= 0:
        return 10.0
    rr = upside_pct / downside_pct
    if rr >= 1.5:
        return 20.0
    if rr >= 1.0:
        return 15.0
    if rr >= 0.8:
        return 10.0
    return 5.0


def compute_trade_score(
    symbol: str,
    direction: str,
    range_pct: float,
    tier: str,
    win_rate: float,
    sample_size: int,
    avg_win: float = 0.0,
    avg_loss: float = 0.0,
    v530_stop_distance: float = 0.0,
    atr_stop_distance: float = 0.0,
    upside_pct: float = 0.0,
    downside_pct: float = 0.0,
) -> TradeScore:
    """计算交易评分。"""
    ts = TradeScore(
        symbol=symbol,
        direction=direction,
        v530_range_pct=range_pct,
        direction_tier=tier,
        direction_win_rate=win_rate,
        direction_sample=sample_size,
        direction_avg_win=avg_win,
        direction_avg_loss=avg_loss,
        atr_stop_distance=atr_stop_distance,
        v530_stop_distance=v530_stop_distance,
    )

    ts.v530_score = score_v530(range_pct)
    ts.direction_score = score_direction(tier, win_rate, sample_size, avg_win, avg_loss)
    ts.atr_score, ts.stop_status = score_atr(v530_stop_distance, atr_stop_distance)
    ts.rr_score = score_risk_reward(upside_pct, downside_pct)
    ts.risk_reward = upside_pct / downside_pct if downside_pct > 0 else 0

    return ts
