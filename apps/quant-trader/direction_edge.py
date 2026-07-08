"""高置信方向边缘检测 — 渐进式精度提升（非一刀切白名单）.

策略演进:
  1. 多 setup 并存，实证弱的逐步提高独立门槛（SETUP_MIN_SCORES）
  2. 生产档 edge 为「软确认」：edge 反对则拦截；弱共识(<8层)需 edge 背书
  3. 强共识(≥8层)无 edge 仍可输出 — 保留 11 层引擎能力，慢慢收敛

实证依据 (research.py, 2026-06-29):
  - 深超跌 + 强势 regime → 唯一稳定 edge (~80% 方向命中)
  - 其余 setup 保留但门槛更高，随回测数据可继续微调 SETUP_MIN_SCORES
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .analysis.indicators import calc_macd

MIN_EDGE_SCORE = 70.0

# 分 setup 门槛 — 弱的逐步收紧，强的保持；可据日志继续微调 ±2
SETUP_MIN_SCORES: dict[str, float] = {
    "强势深超跌反弹": 70.0,
    "上升趋势回踩": 83.0,
    "放量突破": 78.0,
    "弱势反弹衰竭": 80.0,
    "超买反转": 83.0,
    "放量跌破": 78.0,
}


@dataclass
class EdgeSetup:
    direction: int
    score: float
    name: str
    reasons: list[str]


def _rsi(close: pd.Series, n: int = 14) -> float:
    d = close.diff()
    up = d.clip(lower=0).rolling(n).mean()
    dn = (-d.clip(upper=0)).rolling(n).mean()
    rs = up / dn.replace(0, np.nan)
    val = 100 - 100 / (1 + rs)
    v = val.iloc[-1]
    return float(v) if pd.notna(v) else 50.0


def _adx(prices: pd.DataFrame, n: int = 14) -> float:
    high = prices["high"].astype(float)
    low = prices["low"].astype(float)
    close = prices["close"].astype(float)
    tr = pd.concat(
        [high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()],
        axis=1,
    ).max(axis=1)
    up = high.diff()
    dn = -low.diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    atr = tr.rolling(n).mean()
    plus_di = 100 * pd.Series(plus_dm, index=prices.index).rolling(n).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=prices.index).rolling(n).mean() / atr
    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
    adx = dx.rolling(n).mean().iloc[-1]
    return float(adx) if pd.notna(adx) else 0.0


def _vol_ratio(prices: pd.DataFrame, n: int = 20) -> float:
    vol = prices["volume"].astype(float)
    if len(vol) < n + 1:
        return 1.0
    avg = float(vol.iloc[-n - 1 : -1].mean())
    if avg <= 0:
        return 1.0
    return float(vol.iloc[-1] / avg)


def _setup_passes(setup: EdgeSetup) -> bool:
    floor = SETUP_MIN_SCORES.get(setup.name, MIN_EDGE_SCORE)
    return setup.score >= max(MIN_EDGE_SCORE, floor)


def _append_if_passes(setups: list[EdgeSetup], setup: EdgeSetup) -> None:
    if _setup_passes(setup):
        setups.append(setup)


def _scan_buy_setups(prices: pd.DataFrame) -> list[EdgeSetup]:
    close = prices["close"].astype(float)
    n = len(close)
    if n < 60:
        return []

    price = float(close.iloc[-1])
    ma20 = float(close.rolling(20).mean().iloc[-1])
    ma60 = float(close.rolling(60).mean().iloc[-1])
    ma120 = float(close.rolling(120).mean().iloc[-1]) if n >= 120 else ma60
    rsi = _rsi(close)
    dev20 = price / ma20 - 1
    dev60 = price / ma60 - 1
    low10 = float(prices["low"].astype(float).tail(10).min())
    high20 = float(prices["high"].astype(float).tail(20).max())
    macd = calc_macd(close)
    macd_hist_up = float(macd.get("histogram", 0)) > float(macd.get("histogram_prev", 0))
    setups: list[EdgeSetup] = []

    # Setup 1: 强势深超跌反弹
    score, reasons = 0.0, []
    if dev60 <= -0.08:
        score += 30
        reasons.append(f"距MA60 {dev60*100:.1f}%")
    if price >= ma120 * 0.97:
        score += 25
        reasons.append("强势regime(≥MA120)")
    if rsi < 38:
        score += 20
        reasons.append(f"RSI={rsi:.0f}超卖")
    if price <= low10 * 1.025:
        score += 15
        reasons.append("近10日低点")
    if macd_hist_up:
        score += 10
        reasons.append("MACD柱转正")
    _append_if_passes(setups, EdgeSetup(1, min(100.0, score), "强势深超跌反弹", reasons))

    # Setup 2: 上升趋势回踩（略收紧 RSI 区间）
    score, reasons = 0.0, []
    if ma20 > ma60 and price > ma60 * 0.99:
        score += 28
        reasons.append("MA20>MA60上升趋势")
    if 32 <= rsi <= 42:
        score += 22
        reasons.append(f"RSI={rsi:.0f}健康回踩")
    if -0.05 <= dev20 <= 0.0:
        score += 18
        reasons.append(f"距MA20 {dev20*100:.1f}%")
    if price <= low10 * 1.015:
        score += 20
        reasons.append("回踩10日低点")
    if _vol_ratio(prices) < 0.95:
        score += 12
        reasons.append("明显缩量")
    _append_if_passes(setups, EdgeSetup(1, min(100.0, score), "上升趋势回踩", reasons))

    # Setup 3: 放量突破
    vr = _vol_ratio(prices)
    adx = _adx(prices)
    score, reasons = 0.0, []
    if price >= high20 * 0.998:
        score += 32
        reasons.append("突破20日高点")
    if vr >= 1.40:
        score += 25
        reasons.append(f"量比{vr:.2f}")
    if ma20 > ma60:
        score += 20
        reasons.append("均线多头")
    if adx >= 22:
        score += 15
        reasons.append(f"ADX={adx:.0f}")
    _append_if_passes(setups, EdgeSetup(1, min(100.0, score), "放量突破", reasons))

    return setups


def _scan_sell_setups(prices: pd.DataFrame) -> list[EdgeSetup]:
    close = prices["close"].astype(float)
    n = len(close)
    if n < 60:
        return []

    price = float(close.iloc[-1])
    ma20 = float(close.rolling(20).mean().iloc[-1])
    ma60 = float(close.rolling(60).mean().iloc[-1])
    rsi = _rsi(close)
    dev20 = price / ma20 - 1
    dev60 = price / ma60 - 1
    high10 = float(prices["high"].astype(float).tail(10).max())
    low20 = float(prices["low"].astype(float).tail(20).min())
    macd = calc_macd(close)
    macd_hist_dn = float(macd.get("histogram", 0)) < float(macd.get("histogram_prev", 0))
    setups: list[EdgeSetup] = []

    # Setup 4: 弱势反弹衰竭
    score, reasons = 0.0, []
    if ma20 < ma60:
        score += 28
        reasons.append("MA20<MA60下降趋势")
    if rsi >= 65:
        score += 22
        reasons.append(f"RSI={rsi:.0f}偏强")
    if dev20 >= 0.07:
        score += 20
        reasons.append(f"距MA20 +{dev20*100:.1f}%")
    if price >= high10 * 0.985:
        score += 18
        reasons.append("近10日高点")
    if macd_hist_dn:
        score += 12
        reasons.append("MACD柱转负")
    _append_if_passes(setups, EdgeSetup(-1, min(100.0, score), "弱势反弹衰竭", reasons))

    # Setup 5: 超买反转
    score, reasons = 0.0, []
    if rsi >= 74:
        score += 30
        reasons.append(f"RSI={rsi:.0f}超买")
    if dev60 >= 0.12:
        score += 25
        reasons.append(f"距MA60 +{dev60*100:.1f}%")
    if dev20 >= 0.09:
        score += 20
        reasons.append("远离MA20")
    if macd_hist_dn:
        score += 15
        reasons.append("MACD走弱")
    _append_if_passes(setups, EdgeSetup(-1, min(100.0, score), "超买反转", reasons))

    # Setup 6: 放量跌破
    vr = _vol_ratio(prices)
    score, reasons = 0.0, []
    if price <= low20 * 1.001:
        score += 32
        reasons.append("跌破20日低点")
    if vr >= 1.35:
        score += 25
        reasons.append(f"量比{vr:.2f}")
    if ma20 < ma60:
        score += 22
        reasons.append("均线空头")
    _append_if_passes(setups, EdgeSetup(-1, min(100.0, score), "放量跌破", reasons))

    return setups


def find_best_edge_setup(prices: pd.DataFrame) -> EdgeSetup | None:
    candidates = _scan_buy_setups(prices) + _scan_sell_setups(prices)
    if not candidates:
        return None
    return max(candidates, key=lambda s: s.score)


def direction_matches_edge(prices: pd.DataFrame, direction: int) -> bool:
    if direction not in (1, -1):
        return False
    setup = find_best_edge_setup(prices)
    return setup is not None and setup.direction == direction


def edge_contradicts(prices: pd.DataFrame, direction: int) -> bool:
    """edge 明确指向反方向 → 应拦截."""
    setup = find_best_edge_setup(prices)
    if setup is None:
        return False
    return setup.direction != direction and setup.score >= MIN_EDGE_SCORE


def production_edge_allows(
    prices: pd.DataFrame,
    direction: int,
    agree_count: int,
    *,
    strong_consensus_layers: int = 8,
) -> bool:
    """渐进式生产档门控：强共识放行；弱共识需 edge 背书；edge 反对则拒."""
    if direction not in (1, -1):
        return False
    if edge_contradicts(prices, direction):
        return False
    if agree_count >= strong_consensus_layers:
        return True
    return direction_matches_edge(prices, direction)


def evaluate_direction_accuracy(
    prices_map: dict[str, pd.DataFrame],
    *,
    forward_days: int = 7,
    step: int = 5,
    min_train: int = 80,
    use_edge_gate: bool = True,
) -> dict:
    correct, total = 0, 0
    for _sym, df in prices_map.items():
        for i in range(min_train, len(df) - forward_days, step):
            window = df.iloc[: i + 1].copy()
            if use_edge_gate:
                setup = find_best_edge_setup(window)
                if setup is None:
                    continue
                direction = setup.direction
            else:
                from .prediction_engine_v2 import predict_single
                pred = predict_single(
                    window, _sym, min_confidence=70, min_agree_layers=5, profile="research",
                )
                if pred is None:
                    continue
                direction = pred.direction

            fut = float(df["close"].iloc[i + forward_days] / df["close"].iloc[i] - 1)
            hit = (fut > 0) if direction == 1 else (fut < 0)
            correct += int(hit)
            total += 1

    acc = correct / total if total else 0.0
    return {
        "signals": total,
        "correct": correct,
        "accuracy": round(acc, 4),
        "forward_days": forward_days,
        "use_edge_gate": use_edge_gate,
    }
