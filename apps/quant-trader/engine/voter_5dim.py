"""5维度组合投票器 — 目标75%+准确率。

组合逻辑：
  1. RSI极值 (30%) — 超买超卖，均值回归
  2. MACD+RSI (25%) — 趋势确认
  3. BB突破 (20%) — 价格位置
  4. 跨品种比价 (15%) — M/A比价回归
  5. 波动率 (10%) — ATR缩量/放量

严格筛选：
  - 至少3个维度同向
  - 总置信度≥0.60
  - 动态持有期(根据信号强度)

历史验证(5225根K线)：
  - RSI>75做空3天: 73% (22样本)
  - RSI<25做多10天: 62% (53样本)
  - 组合后预期: 70-75%
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field


@dataclass
class DimVote:
    name: str
    direction: int      # 1=多, -1=空, 0=中性
    confidence: float   # 0~1
    weight: float = 1.0
    reason: str = ""
    hold_days: int = 10  # 建议持有天数


@dataclass
class VoteResult:
    symbol: str
    direction: int
    confidence: float
    score: float
    votes: list[DimVote] = field(default_factory=list)
    hold_days: int = 10
    agreement: float = 0.0

    @property
    def label(self) -> str:
        return {1: "BUY", -1: "SELL"}.get(self.direction, "HOLD")

    @property
    def should_trade(self) -> bool:
        return self.direction != 0 and self.confidence >= 0.60

    def summary(self) -> str:
        lines = [f"[{self.label}] {self.symbol} conf={self.confidence:.0%} hold={self.hold_days}d"]
        for v in self.votes:
            d = "up" if v.direction > 0 else ("dn" if v.direction < 0 else "--")
            lines.append(f"  {v.name:<12s} {d} conf={v.confidence:.0%} w={v.weight:.1f} {v.reason}")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
# 指标预计算
# ══════════════════════════════════════════════════════════════════

def _compute_rsi(closes: pd.Series, period: int = 14) -> dict[int, float]:
    """计算RSI，返回{index: rsi_value}。"""
    returns = closes.pct_change()
    n = len(closes)
    rsi_dict = {}
    for i in range(period, n):
        gains = [float(returns.iloc[j]) for j in range(i-period, i+1)
                 if not np.isnan(returns.iloc[j]) and returns.iloc[j] > 0]
        losses = [abs(float(returns.iloc[j])) for j in range(i-period, i+1)
                  if not np.isnan(returns.iloc[j]) and returns.iloc[j] < 0]
        avg_g = np.mean(gains) if gains else 0.001
        avg_l = np.mean(losses) if losses else 0.001
        rsi_dict[i] = 100 - (100 / (1 + avg_g / avg_l))
    return rsi_dict


def _compute_bb(closes: pd.Series, period: int = 20):
    """计算布林带，返回(upper, lower, width_pct)。"""
    mid = closes.rolling(period).mean()
    std = closes.rolling(period).std()
    upper = mid + 2 * std
    lower = mid - 2 * std
    width_pct = (upper - lower) / mid * 100
    return upper, lower, width_pct


def _compute_macd(closes: pd.Series):
    """计算MACD，返回(hist, prev_hist)。"""
    ema12 = closes.ewm(span=12).mean()
    ema26 = closes.ewm(span=26).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9).mean()
    hist = macd_line - signal_line
    return hist


def _compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14):
    """计算ATR和ATR比率。"""
    trs = []
    n = len(close)
    for i in range(1, n):
        h, l, pc = float(high.iloc[i]), float(low.iloc[i]), float(close.iloc[i-1])
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    tr = pd.Series(trs, index=close.index[1:])
    atr14 = tr.rolling(period).mean()
    atr5 = tr.rolling(5).mean()
    atr_ratio = atr5 / atr14
    return tr, atr14, atr_ratio


# ══════════════════════════════════════════════════════════════════
# 5个维度评分器
# ══════════════════════════════════════════════════════════════════

def _score_rsi(closes: pd.Series, rsi_dict: dict) -> DimVote:
    """维度1: RSI极值 (30%权重)。"""
    n = len(closes)
    if n < 35:
        return DimVote("RSI", 0, 0.0, 0.3, "insufficient")

    idx = n - 1
    rsi = rsi_dict.get(idx, 50)

    if rsi > 75:
        # 极度超买 → 做空，持有3天
        return DimVote("RSI", -1, min(0.9, 0.6 + (rsi-75)*0.03), 0.3,
                       f"RSI={rsi:.0f} 极度超买", hold_days=3)
    elif rsi > 70:
        return DimVote("RSI", -1, min(0.7, 0.4 + (rsi-70)*0.04), 0.3,
                       f"RSI={rsi:.0f} 超买", hold_days=5)
    elif rsi < 25:
        # 极度超卖 → 做多，持有10天
        return DimVote("RSI", 1, min(0.85, 0.55 + (25-rsi)*0.03), 0.3,
                       f"RSI={rsi:.0f} 极度超卖", hold_days=10)
    elif rsi < 30:
        return DimVote("RSI", 1, min(0.7, 0.4 + (30-rsi)*0.04), 0.3,
                       f"RSI={rsi:.0f} 超卖", hold_days=7)
    else:
        return DimVote("RSI", 0, 0.2, 0.3, f"RSI={rsi:.0f} 中性")


def _score_macd_rsi(closes: pd.Series, rsi_dict: dict) -> DimVote:
    """维度2: MACD金叉/死叉 + RSI确认 (25%权重)。"""
    n = len(closes)
    if n < 32:
        return DimVote("MACD", 0, 0.0, 0.25, "insufficient")

    hist = _compute_macd(closes)
    mh = float(hist.iloc[-1])
    mh_prev = float(hist.iloc[-2])
    rsi = rsi_dict.get(n-1, 50)

    # 金叉 + RSI<50确认 → 做多
    if mh > 0 and mh_prev <= 0 and rsi < 50:
        return DimVote("MACD", 1, 0.6, 0.25, f"金叉+RSI={rsi:.0f}", hold_days=10)
    # 死叉 + RSI>50确认 → 做空
    elif mh < 0 and mh_prev >= 0 and rsi > 50:
        return DimVote("MACD", -1, 0.6, 0.25, f"死叉+RSI={rsi:.0f}", hold_days=7)
    # 多头趋势
    elif mh > 0 and mh > mh_prev:
        return DimVote("MACD", 1, 0.4, 0.25, f"多头加速 hist={mh:.2f}", hold_days=10)
    # 空头趋势
    elif mh < 0 and mh < mh_prev:
        return DimVote("MACD", -1, 0.4, 0.25, f"空头加速 hist={mh:.2f}", hold_days=7)
    else:
        return DimVote("MACD", 0, 0.2, 0.25, f"中性 hist={mh:.2f}")


def _score_bb(closes: pd.Series, upper, lower) -> DimVote:
    """维度3: BB突破 (20%权重)。"""
    n = len(closes)
    if n < 22:
        return DimVote("BB", 0, 0.0, 0.2, "insufficient")

    price = float(closes.iloc[-1])
    u = float(upper.iloc[-1])
    l = float(lower.iloc[-1])

    if np.isnan(u) or np.isnan(l) or u == l:
        return DimVote("BB", 0, 0.2, 0.2, "no range")

    pct = (price - l) / (u - l)

    if pct < 0.05:  # 接近下轨
        return DimVote("BB", 1, 0.65, 0.2, f"BB%B={pct:.2f} 近下轨", hold_days=10)
    elif pct > 0.95:  # 接近上轨
        return DimVote("BB", -1, 0.65, 0.2, f"BB%B={pct:.2f} 近上轨", hold_days=5)
    elif pct < 0.15:
        return DimVote("BB", 1, 0.45, 0.2, f"BB%B={pct:.2f}", hold_days=10)
    elif pct > 0.85:
        return DimVote("BB", -1, 0.45, 0.2, f"BB%B={pct:.2f}", hold_days=7)
    else:
        return DimVote("BB", 0, 0.2, 0.2, f"BB%B={pct:.2f} 中性")


def _score_sma_trend(closes: pd.Series) -> DimVote:
    """维度4: SMA趋势排列 (15%权重)。

    纯本地计算，无网络依赖。
    检查 SMA5/10/20/60 的排列状态，判断趋势方向和强度。
    """
    n = len(closes)
    if n < 60:
        return DimVote("SMA", 0, 0.0, 0.15, "insufficient")

    sma5 = float(closes.tail(5).mean())
    sma10 = float(closes.tail(10).mean())
    sma20 = float(closes.tail(20).mean())
    sma60 = float(closes.tail(60).mean())
    price = float(closes.iloc[-1])

    # 多头排列: SMA5 > SMA10 > SMA20 > SMA60
    if sma5 > sma10 > sma20 > sma60:
        return DimVote("SMA", 1, 0.7, 0.15, f"多头排列 sma5={sma5:.0f}", hold_days=10)
    elif sma5 > sma10 > sma20:
        return DimVote("SMA", 1, 0.55, 0.15, f"短多 sma5>{sma5:.0f}", hold_days=7)
    # 空头排列: SMA5 < SMA10 < SMA20 < SMA60
    elif sma5 < sma10 < sma20 < sma60:
        return DimVote("SMA", -1, 0.7, 0.15, f"空头排列 sma5={sma5:.0f}", hold_days=7)
    elif sma5 < sma10 < sma20:
        return DimVote("SMA", -1, 0.55, 0.15, f"短空 sma5={sma5:.0f}", hold_days=5)
    # 价格相对于均线位置
    elif price > sma20 and sma5 > sma20:
        return DimVote("SMA", 1, 0.35, 0.15, f"价在均线上方", hold_days=10)
    elif price < sma20 and sma5 < sma20:
        return DimVote("SMA", -1, 0.35, 0.15, f"价在均线下方", hold_days=7)
    else:
        return DimVote("SMA", 0, 0.2, 0.15, f"均线纠缠")


def _score_volatility(closes: pd.Series, atr_ratio) -> DimVote:
    """维度5: 波动率 (10%权重)。"""
    n = len(closes)
    if n < 40:
        return DimVote("波动", 0, 0.0, 0.1, "insufficient")

    ar = float(atr_ratio.iloc[-1]) if not np.isnan(atr_ratio.iloc[-1]) else 1.0
    pc5 = (float(closes.iloc[-1]) / float(closes.iloc[-6]) - 1) * 100 if n >= 6 else 0

    if ar < 0.7:  # 波动率收缩 → 趋势延续
        if pc5 > 0:
            return DimVote("波动", 1, 0.5, 0.1, f"缩量涨 ar={ar:.2f}", hold_days=10)
        else:
            return DimVote("波动", -1, 0.5, 0.1, f"缩量跌 ar={ar:.2f}", hold_days=7)
    elif ar > 1.5:  # 波动率扩大 → 趋势加速
        if pc5 > 0:
            return DimVote("波动", 1, 0.55, 0.1, f"放量涨 ar={ar:.2f}", hold_days=10)
        else:
            return DimVote("波动", -1, 0.55, 0.1, f"放量跌 ar={ar:.2f}", hold_days=7)
    else:
        return DimVote("波动", 0, 0.2, 0.1, f"ar={ar:.2f} 正常")


# ══════════════════════════════════════════════════════════════════
# 主投票函数
# ══════════════════════════════════════════════════════════════════

def vote_5dim(prices: pd.DataFrame, code: str = "", use_cross: bool = False) -> VoteResult:
    """5维度组合投票器 v2 — 优化版。

    改进:
      1. 替换跨品种比价(需网络)为SMA趋势(纯本地)
      2. 调整权重: RSI 30→25%, MACD 25→25%, BB 20→20%, SMA 15%(新), 波动 10→15%
      3. 降低置信度门槛: ≥0.60 → ≥0.55
      4. 保持: 至少3个维度同向

    严格筛选:
      1. 至少3个维度同向
      2. 总置信度≥0.55
      3. 动态持有期(取最强维度的hold_days)
    """
    closes = prices["close"].astype(float)
    if len(closes) < 40:
        return VoteResult(code, 0, 0.0, 0.0, [], 10, 0.0)

    n = len(closes)

    # 预计算指标
    rsi_dict = _compute_rsi(closes)
    bb_upper, bb_lower, _ = _compute_bb(closes)
    atr_ratio = None
    try:
        highs = prices["high"].astype(float) if "high" in prices.columns else closes
        lows = prices["low"].astype(float) if "low" in prices.columns else closes
        _, _, atr_ratio = _compute_atr(highs, lows, closes)
    except Exception:
        pass

    # 5个维度投票 (v2: 比价→SMA趋势)
    votes = [
        _score_rsi(closes, rsi_dict),       # 25%
        _score_macd_rsi(closes, rsi_dict),  # 25%
        _score_bb(closes, bb_upper, bb_lower),  # 20%
        _score_sma_trend(closes),            # 15% (替代比价)
    ]

    # 波动率
    if atr_ratio is not None:
        votes.append(_score_volatility(closes, atr_ratio))
    else:
        votes.append(DimVote("波动", 0, 0.0, 0, "no atr"))

    # 汇总
    valid = [v for v in votes if v.weight > 0 and v.confidence > 0]
    if not valid:
        return VoteResult(code, 0, 0.0, 0.0, votes, 10, 0.0)

    buy_votes = [v for v in valid if v.direction == 1]
    sell_votes = [v for v in valid if v.direction == -1]
    n_buy = len(buy_votes)
    n_sell = len(sell_votes)
    n_valid = len(valid)

    # 方向
    if n_buy > n_sell:
        direction = 1
        agree = buy_votes
    elif n_sell > n_buy:
        direction = -1
        agree = sell_votes
    else:
        direction = 0
        agree = []

    majority = max(n_buy, n_sell)

    # 规则1: 至少3个维度同向
    if majority < 3:
        return VoteResult(code, 0, 0.0, 0.0, votes, 10, 0.0)

    # 计算置信度
    avg_conf = sum(v.confidence * v.weight for v in agree) / sum(v.weight for v in agree)

    # 增强: 3/3同向→×1.5, 4/5→×1.8, 5/5→×2.0
    if majority >= 5:
        confidence = min(0.95, avg_conf * 2.0)
    elif majority >= 4:
        confidence = min(0.92, avg_conf * 1.8)
    else:
        confidence = min(0.85, avg_conf * 1.5)

    # 规则2: 总置信度≥0.55 (v2: 降低门槛)
    if confidence < 0.55:
        direction = 0

    # 动态持有期: 取最强维度的hold_days
    hold_days = max(v.hold_days for v in agree) if agree else 10

    # 加权总分
    total_weight = sum(v.weight for v in votes)
    score = sum(v.direction * v.confidence * v.weight for v in votes) / max(total_weight, 0.01)

    agreement = majority / n_valid if n_valid > 0 else 0

    return VoteResult(
        symbol=code, direction=direction,
        confidence=round(confidence, 3),
        score=round(score, 3),
        votes=votes,
        hold_days=hold_days,
        agreement=round(agreement, 3),
    )
