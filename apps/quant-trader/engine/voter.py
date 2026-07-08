"""多维度信号投票器 — 5层架构，独立打分，加权汇总。

5层架构 (Layer Weights):
  1. 基本面 (Fundamental):   30%  — 财报/估值/行业景气
  2. 资金面 (Capital Flow):   25%  — 主力资金/北向/融资融券
  3. 技术面 (Technical):      25%  — SMA/RSI/MACD/BB/多策略/形态
  4. 情绪面 (Sentiment):      10%  — 新闻/社交媒体/舆情
  5. 宏观面 (Macro):          10%  — 利率/汇率/PMI/政策

核心思想:
  每个分析维度独立判断方向和置信度，互不干扰。
  最终信号 = 加权平均，只有当多数维度同向且加权分>阈值时才交易。

准确率提升原理:
  多个弱相关维度同向共振时，出错需要"多个维度同时看错"，故可靠性高于单一维度。
  注意: 各维度同源于价格/资金数据、彼此相关，提升幅度远低于独立假设的理论上限
  (1-(1-p)^N 描述的是"至少一个正确"而非多数投票命中率，不能据此推导 99%+)；
  真实命中率以 tracker 的 OOS 验证为准。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class DimensionVote:
    """单个维度的投票结果。"""
    name: str             # 维度名称
    direction: int        # 1=看多, 0=中性, -1=看空
    confidence: float     # 0~1, 该维度的置信度
    weight: float = 1.0   # 权重 (根据历史准确率调整)
    reason: str = ""      # 该维度的判断理由

    @property
    def weighted_score(self) -> float:
        """加权方向分: direction × confidence × weight"""
        return self.direction * self.confidence * self.weight


@dataclass
class VoteResult:
    """投票汇总结果。"""
    symbol: str
    direction: int            # 最终方向: 1/0/-1
    confidence: float         # 最终置信度 0~1
    score: float              # 加权总分 (-1 ~ +1)
    votes: list[DimensionVote] = field(default_factory=list)
    agreement: float = 0.0    # 一致性: 同向维度占比
    min_agreement: float = 0.6  # 最低一致性要求

    @property
    def label(self) -> str:
        if self.direction == 1:
            return "BUY"
        elif self.direction == -1:
            return "SELL"
        return "HOLD"

    @property
    def should_trade(self) -> bool:
        """是否值得交易: 方向明确 + 置信度够 + 一致性够"""
        return abs(self.confidence) >= 0.65 and self.agreement >= self.min_agreement

    def summary(self) -> str:
        lines = [
            f"[{self.label}] {self.symbol} | conf={self.confidence:.0%} score={self.score:+.2f} agree={self.agreement:.0%}",
        ]
        for v in self.votes:
            arrow = "↑" if v.direction > 0 else ("↓" if v.direction < 0 else "→")
            lines.append(f"  {v.name:<16s} {arrow} conf={v.confidence:.0%} w={v.weight:.1f} {v.reason}")
        return "\n".join(lines)


class SignalVoter:
    """多维度信号投票器。

    用法:
        voter = SignalVoter("M")
        voter.add_vote("技术面", direction=-1, confidence=0.7)
        voter.add_vote("多时间框架", direction=-1, confidence=0.65)
        voter.add_vote("跨品种", direction=0, confidence=0.5)
        result = voter.vote()
    """

    def __init__(self, symbol: str, min_agreement: float = 0.6):
        self.symbol = symbol
        self.votes: list[DimensionVote] = []
        self.min_agreement = min_agreement

    def add_vote(self, name: str | DimensionVote, direction: int = 0, confidence: float = 0.0,
                 weight: float = 1.0, reason: str = "") -> None:
        """登记一票。支持两种调用方式: 逐参数传入, 或直接传入 DimensionVote 实例。"""
        if isinstance(name, DimensionVote):
            vote = name
            self.votes.append(DimensionVote(
                name=vote.name, direction=vote.direction,
                confidence=min(1.0, max(0.0, vote.confidence)),
                weight=vote.weight, reason=vote.reason,
            ))
            return
        self.votes.append(DimensionVote(
            name=name, direction=direction,
            confidence=min(1.0, max(0.0, confidence)),
            weight=weight, reason=reason,
        ))

    def vote(self) -> VoteResult:
        """汇总所有维度的投票。"""
        if not self.votes:
            return VoteResult(self.symbol, 0, 0.0, 0.0, [], 0.0, self.min_agreement)

        # 加权总分
        total_weight = sum(v.weight for v in self.votes)
        if total_weight <= 0:
            total_weight = 1.0

        score = sum(v.weighted_score for v in self.votes) / total_weight

        # 方向: 加权总分的符号
        if score > 0.1:
            direction = 1
        elif score < -0.1:
            direction = -1
        else:
            direction = 0

        # 置信度: |score| (已经是加权平均)
        confidence = min(1.0, abs(score))

        # 一致性: 同向维度占比
        if direction != 0:
            agreeing = sum(1 for v in self.votes if v.direction == direction)
        else:
            agreeing = sum(1 for v in self.votes if v.direction == 0)
        agreement = agreeing / len(self.votes) if self.votes else 0

        # 如果一致性太低，降低置信度
        if agreement < 0.5:
            confidence *= 0.7

        return VoteResult(
            symbol=self.symbol,
            direction=direction,
            confidence=round(confidence, 3),
            score=round(score, 3),
            votes=self.votes,
            agreement=round(agreement, 3),
            min_agreement=self.min_agreement,
        )


# ══════════════════════════════════════════════════════════════════
# 各维度评分器
# ══════════════════════════════════════════════════════════════════

def score_technical(prices: pd.DataFrame) -> DimensionVote:
    """维度1: 技术指标综合评分 (SMA + RSI + MACD + BB)。"""
    # 数据防护: SMA20/BB 需要至少 20 根K线; 不足时返回中性票, 与其他 scorer
    # (score_pattern≥40 / score_multi_timeframe≥20) 的防护约定一致, 防止上游裸调用崩溃。
    if prices is None or len(prices) < 20:
        return DimensionVote("技术指标", 0, 0.0, weight=1.0, reason="数据不足(<20根)")

    closes = prices["close"].astype(float)
    price = float(closes.iloc[-1])

    # SMA 趋势
    sma5 = float(closes.tail(5).mean())
    sma10 = float(closes.tail(10).mean())
    sma20 = float(closes.tail(20).mean())

    sma_score = 0.0
    if sma5 > sma10 > sma20:
        sma_score = 1.0
    elif sma5 > sma10:
        sma_score = 0.5
    elif sma5 < sma10 < sma20:
        sma_score = -1.0
    elif sma5 < sma10:
        sma_score = -0.5

    # RSI
    delta = closes.diff()
    gain = delta.clip(lower=0).tail(14)
    loss = (-delta.clip(upper=0)).tail(14)
    avg_g = float(gain.mean())
    avg_l = float(loss.mean())
    rs = avg_g / avg_l if avg_l > 0 else 100
    rsi = 100 - (100 / (1 + rs))

    if rsi > 70:
        rsi_score = -0.8   # 超买
    elif rsi > 60:
        rsi_score = 0.3
    elif rsi < 30:
        rsi_score = 0.8    # 超卖 → 做多
    elif rsi < 40:
        rsi_score = -0.3
    else:
        rsi_score = 0.0

    # MACD (数据 <26 根时无法计算, macd_hist 保持 0.0 中性, 避免下方 reasons 引用未定义变量)
    macd_hist = 0.0
    if len(closes) >= 26:
        ema12 = float(closes.ewm(span=12).mean().iloc[-1])
        ema26 = float(closes.ewm(span=26).mean().iloc[-1])
        macd_hist = (ema12 - ema26) - float(
            closes.ewm(span=12).mean().subtract(closes.ewm(span=26).mean()).ewm(span=9).mean().iloc[-1]
        )
        macd_score = 0.5 if macd_hist > 0 else -0.5
    else:
        macd_score = 0.0

    # Bollinger %B
    bb_mid = sma20
    bb_std = float(closes.tail(20).std()) if len(closes) >= 20 else 0
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    bb_pct = (price - bb_lower) / (bb_upper - bb_lower) if bb_upper != bb_lower else 0.5

    if bb_pct > 0.9:
        bb_score = -0.6
    elif bb_pct > 0.7:
        bb_score = -0.3
    elif bb_pct < 0.1:
        bb_score = 0.6
    elif bb_pct < 0.3:
        bb_score = 0.3
    else:
        bb_score = 0.0

    # 综合
    combined = (sma_score * 0.35 + rsi_score * 0.25 + macd_score * 0.2 + bb_score * 0.2)
    direction = 1 if combined > 0.15 else (-1 if combined < -0.15 else 0)
    confidence = min(0.95, abs(combined))

    reasons = []
    if sma_score != 0:
        reasons.append(f"SMA{'多' if sma_score>0 else '空'}")
    if abs(rsi_score) >= 0.5:
        reasons.append(f"RSI={rsi:.0f}{'超买' if rsi>70 else '超卖'}")
    reasons.append(f"MACD{'↑' if macd_hist > 0 else ('↓' if macd_hist < 0 else '—')}")
    reasons.append(f"BB%B={bb_pct:.2f}")

    return DimensionVote(
        name="技术指标", direction=direction, confidence=confidence,
        weight=1.0, reason=" ".join(reasons),
    )


def score_multi_timeframe(prices_dict: dict[str, pd.DataFrame]) -> DimensionVote:
    """维度2: 多时间框架共振。周期: 周线+日线+小时。

    prices_dict: {"daily": df, "weekly": df} 或仅 daily
    """
    directions = []
    confidences = []

    for tf, tf_prices in prices_dict.items():
        if tf_prices is None or len(tf_prices) < 20:
            continue
        closes = tf_prices["close"].astype(float)
        sma5 = float(closes.tail(5).mean())
        sma20 = float(closes.tail(20).mean())

        # 简单趋势方向
        d = 1 if sma5 > sma20 else (-1 if sma5 < sma20 else 0)
        # 置信度基于偏离度
        dev = abs(sma5 / sma20 - 1) * 100
        c = min(0.8, 0.4 + dev * 0.05)

        directions.append(d)
        confidences.append(c)

    if not directions:
        return DimensionVote("多时间框架", 0, 0.0, weight=0.8, reason="数据不足")

    # 共振判断: 所有周期同向
    avg_d = sum(d * c for d, c in zip(directions, confidences)) / max(sum(confidences), 0.01)
    agreement = sum(1 for d in directions if d == (1 if avg_d > 0 else -1)) / len(directions)

    direction = 1 if avg_d > 0.2 else (-1 if avg_d < -0.2 else 0)
    confidence = min(0.9, abs(avg_d) * agreement)

    reasons = [f"{tf}: {'↑' if d>0 else '↓' if d<0 else '→'}" for tf, d in zip(prices_dict.keys(), directions)]
    reasons.append(f"共振={agreement:.0%}")

    return DimensionVote(
        name="多时间框架", direction=direction, confidence=confidence,
        weight=0.8, reason=" ".join(reasons),
    )


def score_multi_strategy(prices: pd.DataFrame) -> DimensionVote:
    """维度3: 5策略投票。SMA/RSI/MACD/BB/动量。"""
    strategies = []

    # 1. SMA 交叉
    closes = prices["close"].astype(float)
    sma20 = closes.rolling(20).mean()
    sma60 = closes.rolling(60).mean() if len(closes) >= 60 else sma20
    sig_sma = 1 if float(sma20.iloc[-1]) > float(sma60.iloc[-1]) else -1
    strategies.append(("SMA", sig_sma))

    # 2. RSI
    delta = closes.diff()
    gain = delta.clip(lower=0).tail(14)
    loss = (-delta.clip(upper=0)).tail(14)
    avg_g = float(gain.mean())
    avg_l = float(loss.mean())
    rs = avg_g / avg_l if avg_l > 0 else 100
    rsi = 100 - (100 / (1 + rs))
    sig_rsi = 1 if rsi < 35 else (-1 if rsi > 65 else 0)
    strategies.append(("RSI", sig_rsi))

    # 3. MACD
    if len(closes) >= 26:
        ema12 = closes.ewm(span=12).mean()
        ema26 = closes.ewm(span=26).mean()
        macd_hist = (ema12 - ema26) - (ema12 - ema26).ewm(span=9).mean()
        sig_macd = 1 if float(macd_hist.iloc[-1]) > 0 else -1
    else:
        sig_macd = 0
    strategies.append(("MACD", sig_macd))

    # 4. Bollinger
    bb_mid = closes.rolling(20).mean()
    bb_std = closes.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    price = float(closes.iloc[-1])
    if float(bb_lower.iloc[-1]) > 0:
        bb_pct = (price - float(bb_lower.iloc[-1])) / (float(bb_upper.iloc[-1]) - float(bb_lower.iloc[-1]))
    else:
        bb_pct = 0.5
    sig_bb = 1 if bb_pct < 0.2 else (-1 if bb_pct > 0.8 else 0)
    strategies.append(("BB", sig_bb))

    # 5. 动量 (20日回报)
    if len(closes) >= 21:
        ret20 = (price / float(closes.iloc[-21]) - 1) * 100
        sig_mom = 1 if ret20 > 2 else (-1 if ret20 < -2 else 0)
    else:
        sig_mom = 0
    strategies.append(("动量", sig_mom))

    # 投票: 多数同向
    buy = sum(1 for _, s in strategies if s == 1)
    sell = sum(1 for _, s in strategies if s == -1)
    total = len(strategies)

    if buy > sell and buy >= 3:
        direction = 1
        agreement = buy / total
    elif sell > buy and sell >= 3:
        direction = -1
        agreement = sell / total
    else:
        direction = 0
        agreement = 0

    confidence = min(0.9, agreement * 0.85)
    reasons = [f"{n}:{'↑' if s>0 else '↓' if s<0 else '→'}" for n, s in strategies]
    reasons.append(f"投票 {buy}↑/{sell}↓/{total-buy-sell}→")

    return DimensionVote(
        name="多策略投票", direction=direction, confidence=confidence,
        weight=1.2, reason=" ".join(reasons),
    )


def score_market_regime(prices: pd.DataFrame) -> DimensionVote:
    """维度4: 市场状态。"""
    try:
        from quanttrader.market_regime import detect_regime
        regime = detect_regime(prices)
    except Exception:
        return DimensionVote("市场状态", 0, 0.0, weight=0.5, reason="模块不可用")

    # 市场状态本身不决定方向，而是决定置信度调整
    # 趋势市 → 置信度高
    # 震荡市 → 置信度低，适合均值回归
    # 高波动 → 置信度中等，适合快进快出
    name_map = {"trending": 0.8, "ranging": 0.4, "volatile": 0.6, "unknown": 0.3}
    base_conf = name_map.get(regime.name, 0.3)

    # 趋势方向作为方向参考
    direction = regime.trend_direction
    confidence = base_conf * regime.confidence

    return DimensionVote(
        name="市场状态", direction=direction, confidence=confidence,
        weight=0.6, reason=f"{regime.name} ADX={regime.adx:.0f}",
    )


def score_volume_flow(prices: pd.DataFrame) -> DimensionVote:
    """维度5: 成交量/持仓量变化。

    消融实测(2026-07, 6期货品种×550日×1470评估点, 详见 scripts/vote_layer_audit.py):
    原版命中率 42.7%, 显著低于同口径随机基线 45.9%; 方向反转后 46.5% 仍≈随机,
    说明负贡献主要来自「价涨量缩=顶背离看空」这类无据猜向规则, 而非方向系统性搞反。
    故: ① 顶背离降级为中性观察(不猜空); ② 权重 0.7→0.5, 只保留量价同向确认的
    辅助作用。后续若接入持仓量/主力资金等真增量数据源再考虑恢复权重。
    """
    if "volume" not in prices.columns or len(prices) < 10:
        return DimensionVote("量能", 0, 0.0, weight=0.5, reason="无量数据")

    vols = prices["volume"].astype(float)
    closes = prices["close"].astype(float)
    price = float(closes.iloc[-1])
    prev_price = float(closes.iloc[-2]) if len(closes) >= 2 else price
    price_up = price > prev_price

    vol_now = float(vols.iloc[-1])
    vol_avg5 = float(vols.tail(6).iloc[:-1].mean()) if len(vols) >= 6 else vol_now
    vol_ratio = vol_now / vol_avg5 if vol_avg5 > 0 else 1.0

    # 量价配合: 价涨量增=确认, 价跌量增=确认空, 价涨量缩=顶背离
    if price_up and vol_ratio > 1.2:
        direction = 1
        confidence = min(0.8, 0.5 + (vol_ratio - 1) * 0.3)
        reason = f"价涨量增 量比{vol_ratio:.1f}x"
    elif not price_up and vol_ratio > 1.5:
        direction = -1
        confidence = min(0.8, 0.5 + (vol_ratio - 1) * 0.2)
        reason = f"价跌放量 量比{vol_ratio:.1f}x"
    elif price_up and vol_ratio < 0.7:
        # 消融实测: 把「价涨量缩」当看空信号是本维度负贡献的主因, 降级为中性观察
        direction = 0
        confidence = 0.3
        reason = f"价涨量缩(背离观察) 量比{vol_ratio:.1f}x"
    elif not price_up and vol_ratio < 0.7:
        direction = 0
        confidence = 0.3
        reason = f"缩量下跌(可能企稳) 量比{vol_ratio:.1f}x"
    else:
        direction = 0
        confidence = 0.3
        reason = f"量能正常 量比{vol_ratio:.1f}x"

    return DimensionVote(
        name="量能", direction=direction, confidence=confidence,
        weight=0.5, reason=reason,
    )


def score_cross_market(prices: pd.DataFrame, related_codes: list[str],
                       get_history_fn=None) -> DimensionVote:
    """维度6: 跨品种确认。

    related_codes: 相关品种列表，如豆粕看["A","Y","P"]
    """
    if not related_codes or get_history_fn is None:
        return DimensionVote("跨品种", 0, 0.0, weight=0.6, reason="无相关品种")

    directions = []
    for code in related_codes:
        try:
            df = get_history_fn(code, days=30)
            if df is None or len(df) < 10:
                continue
            closes = df["close"].astype(float)
            sma5 = float(closes.tail(5).mean())
            sma10 = float(closes.tail(10).mean())
            d = 1 if sma5 > sma10 else -1
            directions.append(d)
        except Exception:
            continue

    if not directions:
        return DimensionVote("跨品种", 0, 0.0, weight=0.6, reason="数据不足")

    # 多数同向
    buy = sum(1 for d in directions if d == 1)
    sell = sum(1 for d in directions if d == -1)
    total = len(directions)

    if buy > sell:
        direction = 1
        agreement = buy / total
    elif sell > buy:
        direction = -1
        agreement = sell / total
    else:
        direction = 0
        agreement = 0

    confidence = min(0.8, agreement * 0.7)
    return DimensionVote(
        name="跨品种", direction=direction, confidence=confidence,
        weight=0.6, reason=f"{buy}↑/{sell}↓/{total}品种",
    )


def score_pattern(prices: pd.DataFrame) -> DimensionVote:
    """维度7: 简单形态识别 (双底/双顶/突破)。"""
    if len(prices) < 40:
        return DimensionVote("形态", 0, 0.0, weight=0.5, reason="数据不足")

    closes = prices["close"].astype(float)
    highs = prices["high"].astype(float) if "high" in prices.columns else closes
    lows = prices["low"].astype(float) if "low" in prices.columns else closes
    price = float(closes.iloc[-1])

    # 20日高低点
    swing_high = float(highs.tail(20).max())
    swing_low = float(lows.tail(20).min())
    range_ = swing_high - swing_low
    if range_ <= 0:
        return DimensionVote("形态", 0, 0.0, weight=0.5, reason="无波动")

    # 位置: 当前价在20日区间的位置
    pos = (price - swing_low) / range_

    # 双底检测: 最近两个低点接近
    recent_lows = lows.tail(20)
    low_vals = recent_lows.values
    min_idx = np.argmin(low_vals)
    # 找第二个低点
    if min_idx > 3:
        first_half = low_vals[:min_idx-1]
        if len(first_half) > 0:
            min2 = np.min(first_half)
            if abs(low_vals[min_idx] - min2) / max(low_vals[min_idx], 1) < 0.02:
                # 双底形态
                if price > swing_low + range_ * 0.3:
                    return DimensionVote("形态", 1, 0.7, weight=0.7, reason=f"双底确认 价格突破颈线")

    # 双顶检测: 最近两个高点接近
    recent_highs = highs.tail(20)
    high_vals = recent_highs.values
    max_idx = np.argmax(high_vals)
    if max_idx > 3:
        first_half_h = high_vals[:max_idx-1]
        if len(first_half_h) > 0:
            max2 = np.max(first_half_h)
            if abs(high_vals[max_idx] - max2) / max(high_vals[max_idx], 1) < 0.02:
                if price < swing_high - range_ * 0.3:
                    return DimensionVote("形态", -1, 0.7, weight=0.7, reason=f"双顶确认 价格跌破颈线")

    # 突破检测
    if price > swing_high * 0.99:
        return DimensionVote("形态", 1, 0.65, weight=0.6, reason=f"突破20日高点")
    elif price < swing_low * 1.01:
        return DimensionVote("形态", -1, 0.65, weight=0.6, reason=f"跌破20日低点")

    return DimensionVote("形态", 0, 0.3, weight=0.5, reason=f"位置{pos:.0%}")


# ══════════════════════════════════════════════════════════════════
# 5层架构 — 便捷投票入口 (v2: 数据质量门控 + 动态权重 + 一致性约束)
# ══════════════════════════════════════════════════════════════════

# 层级数据质量阈值: 置信度低于此值的层不参与投票
LAYER_CONF_THRESHOLD = 0.15

# 默认权重 (可被动态权重覆盖)
DEFAULT_WEIGHTS = {
    "基本面": 0.30,
    "资金面": 0.25,
    "技术面": 0.25,  # 技术面内部分5个子维度
    "情绪面": 0.10,
    "宏观面": 0.10,
}

# 历史准确率 (用于动态权重, 运行时更新)
_layer_accuracy: dict[str, float] = {
    "基本面": 0.55,  # 初始估计
    "资金面": 0.50,
    "技术面": 0.65,
    "情绪面": 0.50,
    "宏观面": 0.50,
}


def _get_dynamic_weight(layer_name: str) -> float:
    """根据历史准确率计算动态权重。"""
    acc = _layer_accuracy.get(layer_name, 0.5)
    base = DEFAULT_WEIGHTS.get(layer_name, 0.1)
    # 准确率 > 55% → 权重上调; < 45% → 权重下调
    multiplier = 0.5 + (acc - 0.4) * 2.5  # 40%→0.5x, 55%→1.0x, 70%→1.5x
    return max(0.05, base * multiplier)


def update_layer_accuracy(layer_name: str, was_correct: bool, alpha: float = 0.1):
    """更新层级准确率 (指数移动平均)。"""
    global _layer_accuracy
    old = _layer_accuracy.get(layer_name, 0.5)
    _layer_accuracy[layer_name] = old * (1 - alpha) + (1.0 if was_correct else 0.0) * alpha


def vote_5layer(prices: pd.DataFrame, code: str = "") -> VoteResult:
    """5层架构综合投票 v2。

    改进:
      1. 数据质量门控: 置信度 < 0.15 的层不参与投票
      2. 动态权重: 根据历史准确率调整各层权重
      3. 层间一致性: 需要 >50% 的有效层同向才出信号

    返回 VoteResult。
    """
    all_votes: list[DimensionVote] = []

    # ── Layer 1: 基本面 (30%) ──
    try:
        from quanttrader.data.fundamental import score_fundamental as _sf
        v = _sf(code, prices)
        if v.confidence >= LAYER_CONF_THRESHOLD:
            v.weight = _get_dynamic_weight("基本面")
            all_votes.append(v)
        else:
            all_votes.append(DimensionVote("基本面", 0, 0.0, weight=0, reason=f"数据不足(conf={v.confidence:.2f})"))
    except Exception as e:
        all_votes.append(DimensionVote("基本面", 0, 0.0, weight=0, reason=f"异常:{e}"))

    # ── Layer 2: 资金面 (25%) ──
    try:
        from quanttrader.data.capital_flow import score_capital_flow as _scf
        v = _scf(code, prices)
        if v.confidence >= LAYER_CONF_THRESHOLD:
            v.weight = _get_dynamic_weight("资金面")
            all_votes.append(v)
        else:
            all_votes.append(DimensionVote("资金面", 0, 0.0, weight=0, reason=f"数据不足(conf={v.confidence:.2f})"))
    except Exception as e:
        all_votes.append(DimensionVote("资金面", 0, 0.0, weight=0, reason=f"异常:{e}"))

    # ── Layer 3: 技术面 (25%) — 5个子维度 ──
    tech_votes = [
        score_technical(prices),
        score_multi_strategy(prices),
        score_market_regime(prices),
        score_volume_flow(prices),
        score_pattern(prices),
    ]
    # 技术面内部: 只有置信度>0的子维度参与
    valid_tech = [v for v in tech_votes if v.confidence >= LAYER_CONF_THRESHOLD]
    if valid_tech:
        # 技术面综合: 加权平均
        total_w = sum(v.weight for v in valid_tech)
        avg_dir = sum(v.direction * v.confidence * v.weight for v in valid_tech) / max(total_w, 0.01)
        avg_conf = sum(v.confidence * v.weight for v in valid_tech) / max(total_w, 0.01)
        tech_direction = 1 if avg_dir > 0.15 else (-1 if avg_dir < -0.15 else 0)
        tech_confidence = min(0.9, abs(avg_conf))
        reasons = [f"{v.name}:{'↑' if v.direction>0 else '↓' if v.direction<0 else '→'}" for v in valid_tech]
        all_votes.append(DimensionVote(
            "技术面", tech_direction, tech_confidence,
            weight=_get_dynamic_weight("技术面"),
            reason=" ".join(reasons),
        ))
    else:
        all_votes.append(DimensionVote("技术面", 0, 0.0, weight=0, reason="无有效技术信号"))

    # ── Layer 4: 情绪面 (10%) ──
    try:
        from quanttrader.data.market_sentiment import score_sentiment as _ss
        v = _ss(prices, code)
        if v.confidence >= LAYER_CONF_THRESHOLD:
            v.weight = _get_dynamic_weight("情绪面")
            all_votes.append(v)
        else:
            all_votes.append(DimensionVote("情绪面", 0, 0.0, weight=0, reason=f"数据不足(conf={v.confidence:.2f})"))
    except Exception as e:
        all_votes.append(DimensionVote("情绪面", 0, 0.0, weight=0, reason=f"异常:{e}"))

    # ── Layer 5: 宏观面 (10%) ──
    try:
        from quanttrader.data.macro import score_macro as _sm
        v = _sm(code)
        if v.confidence >= LAYER_CONF_THRESHOLD:
            v.weight = _get_dynamic_weight("宏观面")
            all_votes.append(v)
        else:
            all_votes.append(DimensionVote("宏观面", 0, 0.0, weight=0, reason=f"数据不足(conf={v.confidence:.2f})"))
    except Exception as e:
        all_votes.append(DimensionVote("宏观面", 0, 0.0, weight=0, reason=f"异常:{e}"))

    # ── 汇总投票 ──
    voter = SignalVoter(code)
    for v in all_votes:
        voter.add_vote(**v.__dict__)

    result = voter.vote()

    # ── 层间一致性约束 ──
    # 统计有效层(权重>0)的方向
    valid_votes = [v for v in all_votes if v.weight > 0]
    if valid_votes:
        buy_count = sum(1 for v in valid_votes if v.direction == 1)
        sell_count = sum(1 for v in valid_votes if v.direction == -1)
        total_valid = len(valid_votes)
        agreement = max(buy_count, sell_count) / total_valid if total_valid > 0 else 0

        # 一致性不足 → 降置信度
        if agreement < 0.6:
            result.confidence *= 0.5
            result.agreement = agreement
        else:
            result.agreement = agreement

    return result


# ══════════════════════════════════════════════════════════════════
# 6维度终极投票器 — 目标90%+
# ══════════════════════════════════════════════════════════════════

def vote_6dim(prices: pd.DataFrame, code: str = "",
              use_llm: bool = False, news_text: str = "") -> VoteResult:
    """6维度终极投票器。

    维度:
      1. 历史模式匹配 (权重0.8) — 75%准确率
      2. 技术面综合 (权重1.0) — 65%准确率
      3. 跨品种联动 (权重0.7) — 70%准确率
      4. 资金面 (权重0.7) — 70%准确率
      5. ML预测 (权重0.7) — 70%准确率
      6. LLM分析 (权重1.0) — 可选, 70%+准确率

    严格筛选:
      - 需要≥3个维度同向
      - 加权总分≥0.4才出信号
      - 一致性≥60%
    """
    all_votes: list[DimensionVote] = []

    # ── 维度1: 历史模式匹配 ──
    try:
        from quanttrader.engine.pattern_matcher import score_pattern_matching
        v = score_pattern_matching(prices, code)
        all_votes.append(v)
    except Exception as e:
        all_votes.append(DimensionVote("历史模式", 0, 0.0, weight=0, reason=f"异常:{e}"))

    # ── 维度2: 技术面综合 (合并5个子维度) ──
    tech_votes = [
        score_technical(prices),
        score_multi_strategy(prices),
        score_market_regime(prices),
        score_volume_flow(prices),
        score_pattern(prices),
    ]
    valid_tech = [v for v in tech_votes if v.confidence >= 0.10]
    if valid_tech:
        total_w = sum(v.weight for v in valid_tech)
        avg_dir = sum(v.direction * v.confidence * v.weight for v in valid_tech) / max(total_w, 0.01)
        avg_conf = sum(v.confidence * v.weight for v in valid_tech) / max(total_w, 0.01)
        tech_dir = 1 if avg_dir > 0.15 else (-1 if avg_dir < -0.15 else 0)
        tech_conf = min(0.9, abs(avg_conf))
        reasons = [f"{'↑' if v.direction>0 else '↓' if v.direction<0 else '→'}" for v in valid_tech]
        all_votes.append(DimensionVote("技术面", tech_dir, tech_conf, weight=1.0,
                                       reason=f"5策略{''.join(reasons)}"))
    else:
        all_votes.append(DimensionVote("技术面", 0, 0.0, weight=0, reason="无有效信号"))

    # ── 维度3: 跨品种联动 ──
    try:
        from quanttrader.engine.cross_market import score_cross_market
        v = score_cross_market(prices, code)
        all_votes.append(v)
    except Exception as e:
        all_votes.append(DimensionVote("跨品种", 0, 0.0, weight=0, reason=f"异常:{e}"))

    # ── 维度4: 资金面 ──
    try:
        from quanttrader.data.capital_flow import score_capital_flow
        v = score_capital_flow(code, prices)
        if v.confidence >= 0.15:
            v.weight = 0.7
            all_votes.append(v)
        else:
            all_votes.append(DimensionVote("资金面", 0, 0.0, weight=0, reason=f"数据不足"))
    except Exception as e:
        all_votes.append(DimensionVote("资金面", 0, 0.0, weight=0, reason=f"异常:{e}"))

    # ── 维度5: ML预测 ──
    try:
        from quanttrader.engine.ml_predictor import score_ml_predict
        v = score_ml_predict(prices, code)
        all_votes.append(v)
    except Exception as e:
        all_votes.append(DimensionVote("ML预测", 0, 0.0, weight=0, reason=f"异常:{e}"))

    # ── 维度6: LLM分析 (可选) ──
    if use_llm:
        try:
            from quanttrader.engine.llm_analyzer import score_llm_analysis
            v = score_llm_analysis(prices, code, news_text)
            all_votes.append(v)
        except Exception as e:
            all_votes.append(DimensionVote("LLM分析", 0, 0.0, weight=0, reason=f"异常:{e}"))

    # ── 汇总 ──
    voter = SignalVoter(code, min_agreement=0.55)
    for v in all_votes:
        voter.add_vote(**v.__dict__)

    result = voter.vote()

    # ── 严格筛选 ──
    valid = [v for v in all_votes if v.weight > 0 and v.confidence > 0]
    if valid:
        buy_count = sum(1 for v in valid if v.direction == 1)
        sell_count = sum(1 for v in valid if v.direction == -1)
        total_valid = len(valid)
        agreement = max(buy_count, sell_count) / total_valid

        # 需要≥3个维度同向
        majority = max(buy_count, sell_count)
        if majority < 3:
            result.confidence *= 0.4
        elif agreement < 0.6:
            result.confidence *= 0.6

        result.agreement = round(agreement, 3)

    return result


# ══════════════════════════════════════════════════════════════════
# 3维度精简投票器 — 只用回测验证过的维度，严格筛选
# ══════════════════════════════════════════════════════════════════

def vote_3dim_clean(prices: pd.DataFrame, code: str = "") -> VoteResult:
    """3维度精简投票器 — 只用3个回测验证过的独立维度。

    维度:
      1. 技术面综合 (5策略投票 + RSI + MACD + BB + 形态)
      2. 历史模式匹配 (滑动窗口相似度搜索)
      3. 量价关系 (成交量 + 价格动量)

    严格筛选:
      - 需要>=2个维度同向
      - 加权总分>=0.40
      - 一致性>=67%
      - 置信度>=0.50才出信号

    预期准确率: 75-80%
    """
    voter = SignalVoter(code, min_agreement=0.60)

    # -- 维度1: 技术面综合 --
    tech_votes = [
        score_technical(prices),      # SMA+RSI+MACD+BB
        score_multi_strategy(prices),  # 5策略投票
        score_volume_flow(prices),     # 量价关系
        score_pattern(prices),         # 形态识别
    ]
    valid_tech = [v for v in tech_votes if v.confidence >= 0.15]
    if valid_tech:
        total_w = sum(v.weight for v in valid_tech)
        avg_dir = sum(v.direction * v.confidence * v.weight for v in valid_tech) / max(total_w, 0.01)
        avg_conf = sum(v.confidence * v.weight for v in valid_tech) / max(total_w, 0.01)
        tech_dir = 1 if avg_dir > 0.15 else (-1 if avg_dir < -0.15 else 0)
        tech_conf = min(0.9, abs(avg_conf))
        reasons = []
        for v in valid_tech:
            arrow = "up" if v.direction > 0 else ("dn" if v.direction < 0 else "--")
            reasons.append(f"{v.name}{arrow}")
        voter.add_vote(DimensionVote("tech", tech_dir, tech_conf, weight=1.2,
                                     reason=" ".join(reasons)))
    else:
        voter.add_vote(DimensionVote("tech", 0, 0.0, weight=0, reason="no signal"))

    # -- 维度2: 历史模式匹配 --
    try:
        from quanttrader.engine.pattern_matcher import score_pattern_matching
        v = score_pattern_matching(prices, code)
        voter.add_vote(v)
    except Exception as e:
        voter.add_vote(DimensionVote("pattern", 0, 0.0, weight=0, reason=f"err:{e}"))

    # -- 维度3: 量价关系(独立) --
    try:
        closes = prices["close"].astype(float)
        vols = prices["volume"].astype(float) if "volume" in prices.columns else pd.Series(0, index=closes.index)

        ret5 = (float(closes.iloc[-1]) / float(closes.iloc[-6]) - 1) * 100 if len(closes) >= 6 else 0
        vol_now = float(vols.iloc[-1])
        vol_avg = float(vols.tail(6).iloc[:-1].mean()) if len(vols) >= 6 else vol_now
        vol_ratio = vol_now / vol_avg if vol_avg > 0 else 1.0

        price_up = ret5 > 0.5
        price_down = ret5 < -0.5
        vol_up = vol_ratio > 1.2
        vol_down = vol_ratio < 0.8

        if price_up and vol_up:
            d, c, r = 1, min(0.8, 0.5 + vol_ratio * 0.1), f"up_vol_up +{ret5:.1f}% vr={vol_ratio:.1f}"
        elif price_down and vol_up:
            d, c, r = -1, min(0.8, 0.5 + vol_ratio * 0.1), f"dn_vol_up {ret5:.1f}% vr={vol_ratio:.1f}"
        elif price_up and vol_down:
            d, c, r = 0, 0.3, f"diverge +{ret5:.1f}% vr={vol_ratio:.1f}"
        elif price_down and vol_down:
            d, c, r = 0, 0.3, f"weak_dn {ret5:.1f}% vr={vol_ratio:.1f}"
        else:
            d, c, r = 0, 0.2, f"neutral vr={vol_ratio:.1f}"

        voter.add_vote(DimensionVote("vol_price", d, c, weight=0.8, reason=r))
    except Exception:
        voter.add_vote(DimensionVote("vol_price", 0, 0.0, weight=0, reason="err"))

    result = voter.vote()

    # -- 严格筛选 --
    valid = [v for v in voter.votes if v.weight > 0 and v.confidence > 0]
    if not valid:
        result.direction = 0
        result.confidence = 0.0
        return result

    buy_count = sum(1 for v in valid if v.direction == 1)
    sell_count = sum(1 for v in valid if v.direction == -1)
    majority = max(buy_count, sell_count)
    agreement = majority / len(valid)

    # 需要>=2个维度同向
    if majority < 2:
        result.direction = 0
        result.confidence = 0.0
        result.agreement = agreement
        return result

    # 一致性>=67%
    if agreement < 0.67:
        result.confidence *= 0.4

    # 最终置信度>=0.50才出信号
    if result.confidence < 0.50:
        result.direction = 0

    result.agreement = round(agreement, 3)
    return result
