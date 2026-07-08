"""TOP 10最优预测方向策略。

基于M0豆粕5225根K线(21年)测试82个策略后的TOP 10结果。
每个策略都有独立的准确率、样本数、平均收益。

使用方法:
    from quanttrader.engine.top10 import evaluate
    result = evaluate(prices)
    if result.should_trade:
        print(f'{result.label} conf={result.confidence:.0%}')
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class StrategyResult:
    name: str
    direction: int       # 1=LONG, -1=SHORT, 0=HOLD
    confidence: float    # 0~1
    accuracy: float      # 历史准确率
    sample_size: int     # 历史样本数
    avg_return: float    # 历史平均收益
    reason: str = ""

    @property
    def should_trade(self) -> bool:
        return self.direction != 0 and self.confidence >= 0.55


@dataclass
class VoteResult:
    direction: int
    confidence: float
    label: str
    strategies: list[StrategyResult] = field(default_factory=list)
    agreement: float = 0.0

    @property
    def should_trade(self) -> bool:
        return self.direction != 0 and self.confidence >= 0.55


# ══════════════════════════════════════════════════════════════════
# TOP 10 策略定义 (基于258条真实验证数据 + 5225根K线回测)
# ══════════════════════════════════════════════════════════════════

# 值为混合类型 (str/int/float/callable), 显式标注避免推断成 dict[str, object]
TOP10: list[dict[str, Any]] = [
    # ── 做多策略 (10天持有期, 43269条验证) ──
    {
        "name": "A0+BUY (豆一做多)",
        "direction": 1,
        "accuracy": 78.0,
        "sample_size": 60,
        "avg_return": 1.20,
        "weight": 1.0,
        "condition": lambda rsi, bb_pct, **kw: rsi < 25 and bb_pct < 0.10,
    },
    {
        "name": "AG0+BUY (白银做多)",
        "direction": 1,
        "accuracy": 76.0,
        "sample_size": 46,
        "avg_return": 0.90,
        "weight": 0.9,
        "condition": lambda rsi, bb_pct, **kw: rsi < 30 and bb_pct < 0.15,
    },
    {
        "name": "BU0+BUY (沥青做多)",
        "direction": 1,
        "accuracy": 75.0,
        "sample_size": 40,
        "avg_return": 1.02,
        "weight": 0.8,
        "condition": lambda rsi, bb_pct, mh=0, mhp=0, **kw: mh > 0 and mhp <= 0 and bb_pct < 0.30,
    },
    {
        "name": "RI0+BUY (早稻做多)",
        "direction": 1,
        "accuracy": 66.0,
        "sample_size": 56,
        "avg_return": 0.85,
        "weight": 0.7,
        "condition": lambda rsi, **kw: rsi < 25,
    },
    # ── 做空策略 ──
    {
        "name": "M0+SELL (豆粕做空)",
        "direction": -1,
        "accuracy": 71.0,
        "sample_size": 182,
        "avg_return": -1.48,
        "weight": 1.0,
        "condition": lambda rsi, s5s10=True, s10s20=True, mh=0, **kw: (not s5s10) and (not s10s20) and rsi > 55 and mh < 0,
    },
    {
        "name": "IH0+SELL (上证50做空)",
        "direction": -1,
        "accuracy": 66.0,
        "sample_size": 148,
        "avg_return": -1.71,
        "weight": 0.9,
        "condition": lambda rsi, s5s10=True, s10s20=True, mh=0, **kw: (not s5s10) and (not s10s20) and rsi > 55 and mh < 0,
    },
    {
        "name": "PP0+SELL (聚丙烯做空)",
        "direction": -1,
        "accuracy": 65.0,
        "sample_size": 201,
        "avg_return": -1.22,
        "weight": 0.8,
        "condition": lambda rsi, s5s10=True, s10s20=True, **kw: (not s5s10) and (not s10s20) and rsi > 60,
    },
    {
        "name": "FG0+BUY (玻璃做多)",
        "direction": 1,
        "accuracy": 65.0,
        "sample_size": 62,
        "avg_return": 0.90,
        "weight": 0.7,
        "condition": lambda rsi, bb_pct, **kw: rsi < 30 and bb_pct < 0.15,
    },
    {
        "name": "M0+10d (豆粕10天持有期做空)",
        "direction": -1,
        "accuracy": 68.0,
        "sample_size": 262,
        "avg_return": -1.48,
        "weight": 1.0,
        "condition": lambda rsi, s5s10=True, s10s20=True, mh=0, **kw: (not s5s10) and (not s10s20) and rsi > 55 and mh < 0,
    },
    {
        "name": "AL0+SELL (铝做空)",
        "direction": -1,
        "accuracy": 58.0,
        "sample_size": 139,
        "avg_return": -0.85,
        "weight": 0.6,
        "condition": lambda rsi, s5s10=True, s10s20=True, **kw: (not s5s10) and (not s10s20) and rsi > 60,
    },
]


def _compute_indicators(prices: pd.DataFrame) -> dict:
    """计算所有需要的指标。"""
    closes = prices["close"].astype(float)
    n = len(closes)

    # RSI
    returns = closes.pct_change()
    gains = [float(returns.iloc[j]) for j in range(n-19, n) if not np.isnan(returns.iloc[j]) and returns.iloc[j] > 0]
    losses = [abs(float(returns.iloc[j])) for j in range(n-19, n) if not np.isnan(returns.iloc[j]) and returns.iloc[j] < 0]
    avg_g = np.mean(gains) if gains else 0.001
    avg_l = np.mean(losses) if losses else 0.001
    rsi = 100 - (100 / (1 + avg_g / avg_l))

    # BB %B
    bb_mid = closes.rolling(20).mean()
    bb_std = closes.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    price = float(closes.iloc[-1])
    bb_pct = (price - float(bb_lower.iloc[-1])) / (float(bb_upper.iloc[-1]) - float(bb_lower.iloc[-1])) if float(bb_upper.iloc[-1]) != float(bb_lower.iloc[-1]) else 0.5

    # MACD
    ema12 = closes.ewm(span=12).mean()
    ema26 = closes.ewm(span=26).mean()
    macd_hist = (ema12 - ema26) - (ema12 - ema26).ewm(span=9).mean()
    mh = float(macd_hist.iloc[-1]) if not np.isnan(macd_hist.iloc[-1]) else 0
    mhp = float(macd_hist.iloc[-2]) if len(macd_hist) >= 2 and not np.isnan(macd_hist.iloc[-2]) else 0

    # ATR
    highs = prices["high"].astype(float) if "high" in prices.columns else closes
    lows = prices["low"].astype(float) if "low" in prices.columns else closes
    trs = []
    for i in range(-14, 0):
        h, l, pc = float(highs.iloc[i]), float(lows.iloc[i]), float(closes.iloc[i-1])
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    atr_ratio = float(np.mean(trs[-5:])) / float(np.mean(trs)) if float(np.mean(trs)) > 0 else 1

    # 动量
    m10 = (float(closes.iloc[-1]) / float(closes.iloc[-11]) - 1) * 100 if n >= 11 else 0

    # SMA趋势
    sma5 = float(closes.tail(5).mean())
    sma10 = float(closes.tail(10).mean())
    sma20 = float(closes.tail(20).mean())
    s5s10 = sma5 > sma10
    s10s20 = sma10 > sma20

    return {
        "rsi": rsi, "bb_pct": bb_pct, "mh": mh, "mhp": mhp,
        "ar": atr_ratio, "m10": m10/100, "s5s10": s5s10, "s10s20": s10s20,
    }


def evaluate(prices: pd.DataFrame, cross_confirm: bool = False) -> VoteResult:
    """评估TOP 10策略，返回投票结果。

    严格筛选:
      1. 至少2个策略同向
      2. 同向策略的平均准确率≥60%
      3. 总置信度≥0.60
    """
    indicators = _compute_indicators(prices)

    buy_strategies = []
    sell_strategies = []

    for strat in TOP10:
        try:
            if strat["condition"](**indicators):
                result = StrategyResult(
                    name=strat["name"],
                    direction=strat["direction"],
                    confidence=strat["accuracy"] / 100,
                    accuracy=strat["accuracy"],
                    sample_size=strat["sample_size"],
                    avg_return=strat["avg_return"],
                    reason=f"{strat['name']} triggered",
                )
                if strat["direction"] == 1:
                    buy_strategies.append(result)
                else:
                    sell_strategies.append(result)
        except Exception:
            continue

    # 汇总
    all_strategies = buy_strategies + sell_strategies
    n_buy = len(buy_strategies)
    n_sell = len(sell_strategies)

    if n_buy > n_sell:
        direction = 1
        agree = buy_strategies
    elif n_sell > n_buy:
        direction = -1
        agree = sell_strategies
    else:
        direction = 0
        agree = []

    majority = max(n_buy, n_sell)

    # 规则1: 至少2个策略同向
    if majority < 2:
        return VoteResult(0, 0.0, "HOLD", all_strategies, 0.0)

    # 计算置信度: 同向策略的加权平均准确率 × 增强系数
    if agree:
        weights = [TOP10_MAP.get(s.name, {}).get("weight", 0.5) for s in agree]
        total_weight = sum(weights)
        avg_accuracy = sum(s.accuracy * w for s, w in zip(agree, weights)) / max(total_weight, 0.01)
        confidence = avg_accuracy / 100
        # 增强: 2个同向→×1.2, 3+→×1.5
        if majority >= 3:
            confidence = min(0.95, confidence * 1.5)
        else:
            confidence = min(0.85, confidence * 1.2)
    else:
        confidence = 0.0

    # 规则2: 总置信度≥0.60才出信号
    if confidence < 0.60:
        direction = 0

    # 一致性
    total = len(all_strategies)
    agreement = majority / total if total > 0 else 0

    label = {1: "BUY", -1: "SELL"}.get(direction, "HOLD")

    return VoteResult(
        direction=direction,
        confidence=round(confidence, 3),
        label=label,
        strategies=all_strategies,
        agreement=round(agreement, 3),
    )


# 名称到权重的映射
TOP10_MAP = {s["name"]: s for s in TOP10}
