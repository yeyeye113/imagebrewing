"""评分函数: 共振评分, Round2 深度分析, 置信度, 综合排名."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..log import get_logger
from ..screening_journal import ScreeningWeights
from ..strategy.base import get_strategy
from .constants import RESONANCE_CORE_STRATEGIES, ROUND2_CORE_STRATEGIES, TIME_WINDOWS

logger = get_logger("pipeline")


def resonance_and_score(prices: pd.DataFrame, kind: str = "stock") -> tuple[bool, dict | None]:
    """单次策略遍历: 共振关 + 初筛分 (避免重复 generate)."""
    if prices is None or len(prices) < 120:
        return False, None
    recent = prices.iloc[-120:]
    close = recent["close"]
    rets = close.pct_change().dropna()
    vol = max(float(rets.std()) if len(rets) else 0.01, 1e-6)
    ret_60 = float(close.iloc[-1] / close.iloc[max(0, len(close) - 60)] - 1)
    dd = float((close / close.cummax() - 1).min()) if len(close) > 1 else 0.0
    sh = float(rets.mean() / vol * np.sqrt(252)) if len(rets) else 0.0

    scores: dict[str, float] = {}
    signals: list[int] = []
    key_map = {"sma_cross": "sma_score", "rsi": "rsi_score", "bollinger": "boll_score", "momentum": "mom_score"}

    for sname, sparams, _ in RESONANCE_CORE_STRATEGIES:
        try:
            sig_s = get_strategy(sname, **sparams).generate(recent)
            latest = int(sig_s.iloc[-1]) if len(sig_s) > 0 else 0
            s_score = 58.0
            if sh >= 1.5:
                s_score += min(sh * 14, 35)
            elif sh >= 1.0:
                s_score += min(sh * 12, 28)
            elif sh >= 0.5:
                s_score += min(sh * 10, 16)
            elif sh < 0:
                s_score -= 18
            if ret_60 > 0.05:
                s_score += min(ret_60 * 50, 14)
            elif ret_60 > 0:
                s_score += min(ret_60 * 40, 8)
            if dd > -0.08:
                s_score += 4
            elif dd < -0.15:
                s_score -= 10
            if latest == 1:
                s_score += 14
            elif latest == -1:
                s_score -= 18
            scores[sname] = float(np.clip(s_score, 0, 100))
            signals.append(latest)
        except Exception:
            scores[sname] = 50.0
            signals.append(0)

    if not scores:
        return False, None

    bullish = sum(1 for s in signals if s == 1)
    bearish = sum(1 for s in signals if s == -1)
    min_bull = 2 if kind == "future" else 3
    passed = bullish > bearish and bullish >= min_bull
    if not passed or bullish <= bearish:
        return passed, None

    composite = float(np.clip(
        np.mean(list(scores.values())) + (bullish - bearish) * 5 + ret_60 * 22,
        0, 100,
    ))
    out = {
        "score": round(composite, 1),
        "signal": "BUY",
        "sma_score": 50.0, "rsi_score": 50.0, "boll_score": 50.0, "mom_score": 50.0,
        "last_price": round(float(close.iloc[-1]), 2),
        "sharpe": round(sh, 2), "total_return_pct": round(ret_60 * 100, 2),
        "max_drawdown_pct": round(dd * 100, 2),
        "change_1w_pct": 0, "change_1m_pct": 0,
    }
    for sname, _, _ in RESONANCE_CORE_STRATEGIES:
        k = key_map.get(sname)
        if k and sname in scores:
            out[k] = round(scores[sname], 1)
    return True, out


def score_one_round1(prices: pd.DataFrame) -> dict | None:
    """轻量初筛分 (兼容旧调用)."""
    passed, out = resonance_and_score(prices, kind="stock")
    return out if passed else None


def forward_win_rates(close: pd.Series) -> dict:
    """向量化计算多周期 forward 命中."""
    ws: dict = {}
    arr = close.values.astype(float)
    n = len(arr)
    for wl, lb, fw in TIME_WINDOWS:
        if n < lb + fw:
            ws[f"win_rate_{wl}"] = None
            ws[f"avg_return_{wl}"] = None
            continue
        seg = arr[-lb:]
        m = len(seg) - fw
        if m <= 0:
            ws[f"win_rate_{wl}"] = None
            ws[f"avg_return_{wl}"] = None
            continue
        starts = seg[:m]
        ends = seg[fw:fw + m]
        fwds = ends / np.maximum(starts, 1e-9) - 1.0
        ws[f"win_rate_{wl}"] = round(float(np.mean(fwds > 0)), 3)
        ws[f"avg_return_{wl}"] = round(float(np.mean(fwds)), 4)
    return ws


def score_one_round2(prices: pd.DataFrame) -> dict | None:
    """轻量深度分: 2 策略信号 + 向量化命中 (无全量回测)."""
    if prices is None or len(prices) < 120:
        return None
    recent = prices.iloc[-120:]
    close = recent["close"]
    rets = close.pct_change().dropna()
    vol = max(float(rets.std()) if len(rets) else 0.01, 1e-6)
    ret_20 = float(close.iloc[-1] / close.iloc[-21] - 1) if len(close) >= 21 else 0.0
    ret_60 = float(close.iloc[-1] / close.iloc[max(0, len(close) - 60)] - 1)
    sh = float(rets.mean() / vol * np.sqrt(252)) if len(rets) else 0.0

    pseudo_rets: list[float] = []
    pseudo_shs: list[float] = []
    s_bull = s_bear = 0
    for sn, sp, _ in ROUND2_CORE_STRATEGIES:
        try:
            s = get_strategy(sn, **sp)
            latest = int(s.generate(recent).iloc[-1])
            pseudo_rets.append(ret_20 * (1.2 if latest == 1 else (-0.8 if latest == -1 else 0.3)))
            pseudo_shs.append(sh * (1.15 if latest == 1 else 0.85))
            if latest == 1:
                s_bull += 1
            elif latest == -1:
                s_bear += 1
        except Exception:
            pass
    if not pseudo_rets:
        pseudo_rets, pseudo_shs = [ret_20], [sh]

    base = (
        58.0 + np.mean(pseudo_rets) * 55 + np.mean(pseudo_shs) * 8
        + (s_bull - s_bear) * 4 + ret_60 * 15
    )
    r2 = float(np.clip(base, 0, 100))
    ws = forward_win_rates(prices["close"])
    return {
        "round2_score": r2,
        "avg_sharpe": round(float(np.mean(pseudo_shs)), 2),
        "avg_return": round(float(np.mean(pseudo_rets)) * 100, 2),
        "signals_bull": s_bull,
        "signals_bear": s_bear,
        **ws,
    }


def make_prediction(wr, ar) -> str:
    if wr is None:
        return "—"
    if wr >= 0.55 and (ar or 0) > 0:
        return f"看涨 (+{float(ar)*100:.1f}%)"
    if wr >= 0.45:
        return "震荡"
    if wr < 0.45 and (ar or 0) <= 0:
        return f"看跌 ({float(ar)*100:.1f}%)"
    return "震荡偏强"


def confidence_v2(r) -> float:
    """v3 置信度: 以技术面为主，新闻/玄学仅作辅助加分."""
    checks = 0
    if r.round1_score >= 72:
        checks += 2
    elif r.round1_score >= 65:
        checks += 1
    if r.signal == "BUY":
        checks += 2
    if r.sharpe_round2 is not None and r.sharpe_round2 >= 0.8:
        checks += 1
    if r.win_rate_7d is not None and r.win_rate_7d >= 0.52:
        checks += 1
    if r.news_label == "bullish":
        checks += 1
    if r.wuxing_relation not in ("克我(杀)", "") and r.wuxing_score >= 50:
        checks += 1
    return {
        7: 0.95, 6: 0.90, 5: 0.85, 4: 0.72, 3: 0.58, 2: 0.42, 1: 0.28, 0: 0.12,
    }.get(min(checks, 7), 0.12)


def tech_score(r) -> float:
    """纯技术面得分（策略回测 + 深度分析）."""
    r2 = r.round2_score if r.round2_score is not None else r.round1_score
    base = r.round1_score * 0.55 + r2 * 0.45
    if r.signal == "BUY":
        base += 4
    if r.sharpe_round2 is not None and r.sharpe_round2 >= 1.0:
        base += 3
    return float(round(min(100.0, max(0.0, base)), 1))


def horizon_guidance(r) -> tuple[str, str, str]:
    """返回 (短线建议, 长线建议, 最佳周期 short|medium|long)."""
    short_bull = (r.win_rate_3d or 0) >= 0.52 and (r.avg_return_3d or 0) > 0
    med_bull = (r.win_rate_7d or 0) >= 0.52 and (r.avg_return_7d or 0) > 0
    long_bull = (r.win_rate_30d or 0) >= 0.52 and (r.avg_return_30d or 0) > 0

    short = r.prediction_3d or r.prediction_7d or "—"
    long_p = r.prediction_30d or "—"

    if short_bull and r.tech_score >= 75:
        short_advice = f"短线可关注：{short}，设 5–8% 止损，对了移动止盈。"
    elif short_bull:
        short_advice = f"短线偏强({short})，小仓试探，勿追高。"
    else:
        short_advice = f"短线不宜激进({short})，等待更好入场或观望。"

    if long_bull and r.tech_score >= 78:
        long_advice = f"长线配置价值：{long_p}，可分批建仓，保留 20% 现金应对波动。"
    elif long_bull:
        long_advice = f"长线偏乐观({long_p})，确认趋势延续后再加仓。"
    else:
        long_advice = f"长线谨慎({long_p})，优先控回撤，不逆势重仓。"

    scores = {"short": (1 if short_bull else 0) + (1 if med_bull else 0),
              "long": 2 if long_bull else 0}
    if r.tech_score >= 80 and long_bull:
        best = "long"
    elif short_bull and not long_bull:
        best = "short"
    elif scores["long"] >= scores["short"]:
        best = "long"
    else:
        best = "short" if med_bull else "medium"
    return short_advice, long_advice, best


def quality_final_score(r, w: ScreeningWeights | None = None) -> float:
    """综合评分：默认技术面 82%，新闻/玄学合计 ≤ 18%."""
    weights = (w or ScreeningWeights()).normalized()
    r2 = r.round2_score if r.round2_score is not None else r.combined_score
    ts = tech_score(r)
    raw = (
        ts * weights.tech
        + r2 * (weights.tech * 0.35)
        + r.round1_score * (weights.tech * 0.25)
        + r.news_score * weights.news
        + r.wuxing_score * weights.wuxing
        + r.meta_score * weights.meta
    )
    if r.signal == "BUY":
        raw += 4
    if r.passed_resonance and r.passed_trend:
        raw += 4
    if r.news_label == "bullish":
        raw += weights.news * 15
    elif r.news_label == "bearish":
        raw -= 4
    if r.win_rate_7d is not None and r.win_rate_7d >= 0.52:
        raw += 3
    return float(round(min(98.0, max(75.0, raw)), 1))


def finalize(results: list, weights: ScreeningWeights | None = None) -> list:
    w = (weights or ScreeningWeights()).normalized()
    for r in results:
        r.tech_score = tech_score(r)
        r.prediction_3d = make_prediction(r.win_rate_3d, r.avg_return_3d)
        r.prediction_5d = make_prediction(r.win_rate_5d, r.avg_return_5d)
        r.prediction_7d = make_prediction(r.win_rate_7d, r.avg_return_7d)
        r.prediction_30d = make_prediction(r.win_rate_30d, r.avg_return_30d)
        r.confidence = confidence_v2(r)
        r.meta_score = r.combined_score * 0.70 + r.bazi_score * 0.15 + r.divination_score * 0.15
        sa, la, hb = horizon_guidance(r)
        r.short_term_advice = sa
        r.long_term_advice = la
        r.horizon_best = hb

    score_cache = {id(r): quality_final_score(r, w) for r in results}
    results.sort(key=lambda x: score_cache[id(x)], reverse=True)
    for i, r in enumerate(results, 1):
        r.rank = i
        r.final_score = score_cache[id(r)]
    return results


def pick_elite(results: list, top_n: int, min_final: float = 78.0) -> list:
    """只保留最优质标的；不足时放宽到 BUY + 置信度门槛."""
    elite = [
        r for r in results
        if r.final_score >= min_final and r.signal == "BUY" and r.confidence >= 0.65
    ]
    if len(elite) >= min(3, top_n):
        return elite[:top_n]
    fallback = [r for r in results if r.signal == "BUY" and r.confidence >= 0.45]
    if fallback:
        return fallback[:top_n]
    return results[:top_n]
