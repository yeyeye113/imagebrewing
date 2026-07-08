"""Prediction Engine — 用软件自有策略回测评分，选出未来一周涨势最强标的。

对每只标的跑 4 套内置策略 (双均线/RSI/布林带/动量) 的回测，
综合近期信号强度 + 回测绩效 + 最新信号方向，给出 0-100 综合评分。

v0.6: 增强排名委托到 pipeline.py 的统一 6 步管线引擎。

⚠️  这只是技术面量化筛选，不是投资建议。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .data.base import _normalize
from .engine.backtest import Backtester
from .engine.position_sizing import SizingConfig
from .engine.risk import RiskConfig
from .strategy.base import get_strategy


@dataclass
class RankedSymbol:
    symbol: str
    name: str = ""
    score: float = 0.0
    signal: str = "HOLD"
    sma_score: float = 0.0
    rsi_score: float = 0.0
    boll_score: float = 0.0
    mom_score: float = 0.0
    last_price: float = 0.0
    change_1w_pct: float = 0.0
    change_1m_pct: float = 0.0
    sharpe: float = 0.0
    total_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    # v0.5: 新闻 + 五行 + 矫正
    news_sentiment: float = 0.0       # −1..+1 新闻情绪分
    news_label: str = ""              # bullish/bearish/neutral
    wuxing_score_val: float = 50.0    # 五行得分 (0–100)
    wuxing_element: str = ""          # 五行属性
    wuxing_relation: str = ""         # 五行关系 (生/克/比和)
    corrected_score: float = 0.0      # 偏差矫正后的最终得分


# ── 内置策略列表 ───────────────────────────────────────────────────
# 参数 dict 为 int/float 混合, 显式标注避免推断成 object
STRATEGIES: list[tuple[str, dict[str, Any], str]] = [
    ("sma_cross", {"fast": 20, "slow": 50}, "双均线"),
    ("rsi", {"period": 14, "oversold": 30, "overbought": 70}, "RSI"),
    ("bollinger", {"period": 20, "num_std": 2.0}, "布林带"),
    ("momentum", {"lookback": 90}, "动量"),
]

# ── A 股核心标的 (30 only) ─────────────────────────────────────────
LIQUID_STOCKS = [
    ("600519", "贵州茅台"), ("000858", "五粮液"), ("000568", "泸州老窖"),
    ("600887", "伊利股份"),
    ("601318", "中国平安"), ("600036", "招商银行"), ("000001", "平安银行"),
    ("600030", "中信证券"), ("601688", "华泰证券"),
    ("601857", "中国石油"), ("601088", "中国神华"), ("600900", "长江电力"),
    ("600276", "恒瑞医药"), ("300760", "迈瑞医疗"), ("300015", "爱尔眼科"),
    ("000333", "美的集团"), ("000651", "格力电器"), ("002415", "海康威视"),
    ("002594", "比亚迪"), ("300750", "宁德时代"), ("601012", "隆基绿能"),
    ("002230", "科大讯飞"), ("688981", "中芯国际"), ("603019", "中科曙光"),
    ("601899", "紫金矿业"), ("600547", "山东黄金"),
    ("600941", "中国移动"),
    ("601888", "中国中免"), ("300059", "东方财富"), ("002714", "牧原股份"),
]

# ── 期货标的 ───────────────────────────────────────────────────────
FUTURES_UNIVERSE = [
    ("IF", "沪深300股指"), ("IC", "中证500股指"), ("IH", "上证50股指"), ("IM", "中证1000股指"),
    ("RB", "螺纹钢"), ("HC", "热卷"), ("I", "铁矿石"), ("J", "焦炭"), ("JM", "焦煤"),
    ("FG", "玻璃"), ("SA", "纯碱"), ("MA", "甲醇"), ("TA", "PTA"), ("EG", "乙二醇"),
    ("BU", "沥青"), ("RU", "橡胶"), ("SP", "纸浆"),
    ("CU", "沪铜"), ("AL", "沪铝"), ("ZN", "沪锌"), ("NI", "沪镍"),
    ("AU", "沪金"), ("AG", "沪银"),
    ("SC", "原油"), ("FU", "燃料油"), ("LU", "低硫燃油"), ("PG", "液化气"),
    ("M", "豆粕"), ("RM", "菜粕"), ("Y", "豆油"), ("P", "棕榈油"), ("OI", "菜油"),
    ("CF", "棉花"), ("SR", "白糖"), ("JD", "鸡蛋"), ("LH", "生猪"),
    ("C", "玉米"), ("CS", "淀粉"), ("AP", "苹果"), ("CJ", "红枣"),
]


def _load_stock_prices(code: str) -> pd.DataFrame | None:
    """Load A-share daily bars (前复权) via akshare Tencent source."""
    from datetime import datetime, timedelta

    import akshare as ak

    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=400)).strftime("%Y%m%d")
    prefix = "sh" if code.startswith(("6", "68")) else "sz"
    tx_code = f"{prefix}{code}"

    for attempt in range(3):
        try:
            raw = ak.stock_zh_a_hist_tx(
                symbol=tx_code, start_date=start, end_date=end, adjust="qfq",
            )
            if raw is not None and not raw.empty:
                break
        except Exception:
            time.sleep(0.5 * (attempt + 1))
    else:
        return None

    df = raw.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    df = df.rename(columns={c: c.lower() for c in df.columns})
    if "volume" not in df.columns and "amount" in df.columns:
        df["volume"] = (df["amount"] * 10000) / df["close"].clip(lower=0.01)
    df = df.dropna(subset=["close"])
    return _normalize(df) if len(df) >= 60 else None


def _load_futures_prices(symbol: str) -> pd.DataFrame | None:
    """Load futures daily bars via akshare sina."""
    import akshare as ak

    code = f"{symbol}0"
    for attempt in range(3):
        try:
            raw = ak.futures_zh_daily_sina(symbol=code)
            if raw is not None and not raw.empty:
                break
        except Exception:
            time.sleep(0.5 * (attempt + 1))
    else:
        return None

    df = raw.rename(columns={c: c.lower() for c in raw.columns})
    keep = [c for c in ("date", "open", "high", "low", "close", "volume") if c in df.columns]
    df = df[keep]
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    df = df.dropna(subset=["close"])
    return _normalize(df) if len(df) >= 60 else None


def _score_one(prices: pd.DataFrame) -> dict | None:
    """用软件自有 4 套策略回测一只标的，返回综合评分。"""
    if prices is None or len(prices) < 60:
        return None

    recent = prices.iloc[-120:]
    if len(recent) < 60:
        recent = prices

    scores: dict[str, float] = {}
    all_returns: list[float] = []
    all_drawdowns: list[float] = []
    signals: list[int] = []

    risk = RiskConfig(stop_loss=0.08, trailing_stop=0.15, max_drawdown=0.25, risk_per_trade=0.01)
    sizing = SizingConfig(max_position_pct=0.30, max_total_exposure=0.80, cash_reserve_pct=0.20)

    for sname, sparams, _slabel in STRATEGIES:
        try:
            strat = get_strategy(sname, **sparams)
            bt = Backtester(cash=100_000, order_size=0.25, commission=0.00025, slippage=0.0005,
                           risk=risk, sizing=sizing)
            result = bt.run(recent, strat)
            stats = result.stats or {}

            sharpe = stats.get("sharpe", 0.0)
            total_ret = stats.get("total_return", 0.0)
            dd = stats.get("max_drawdown", 0.0)

            sig_series = strat.generate(recent)
            latest_sig = int(sig_series.iloc[-1]) if len(sig_series) > 0 else 0

            strat_score = 50.0
            if sharpe > 0:
                strat_score += min(sharpe * 15, 25)
            if total_ret > 0:
                strat_score += min(total_ret * 50, 15)
            if dd < -0.15:
                strat_score -= 10
            if latest_sig == 1:
                strat_score += 10
            elif latest_sig == -1:
                strat_score -= 15

            scores[sname] = float(np.clip(strat_score, 0, 100))
            all_returns.append(total_ret)
            all_drawdowns.append(dd)
            signals.append(latest_sig)
        except Exception:
            scores[sname] = 50.0
            signals.append(0)

    if not scores:
        return None

    avg_ret = np.mean(all_returns) if all_returns else 0.0
    avg_dd = np.mean(all_drawdowns) if all_drawdowns else 0.0
    avg_sharpe = np.mean([s for s in scores.values() if s > 0]) / 15

    bullish_count = sum(1 for s in signals if s == 1)
    bearish_count = sum(1 for s in signals if s == -1)

    consensus_bonus = (bullish_count - bearish_count) * 5
    base = np.mean(list(scores.values()))
    composite = float(np.clip(base + consensus_bonus + avg_ret * 20, 0, 100))

    close = prices["close"]
    ret_1w = float(close.iloc[-1] / close.iloc[-5] - 1) if len(close) >= 5 else 0.0
    ret_1m = float(close.iloc[-1] / close.iloc[-20] - 1) if len(close) >= 20 else 0.0

    sig_label = "BUY" if bullish_count > bearish_count else ("SELL" if bearish_count > bullish_count else "HOLD")

    return {
        "score": round(composite, 1),
        "signal": sig_label,
        "sma_score": round(scores.get("sma_cross", 50), 1),
        "rsi_score": round(scores.get("rsi", 50), 1),
        "boll_score": round(scores.get("bollinger", 50), 1),
        "mom_score": round(scores.get("momentum", 50), 1),
        "last_price": round(float(close.iloc[-1]), 2),
        "change_1w_pct": round(ret_1w * 100, 2),
        "change_1m_pct": round(ret_1m * 100, 2),
        "sharpe": round(float(avg_sharpe), 2),
        "total_return_pct": round(float(avg_ret) * 100, 2),
        "max_drawdown_pct": round(float(avg_dd) * 100, 2),
    }


def rank_stocks(codes: list[tuple[str, str]] | None = None,
                top_n: int = 5) -> list[RankedSymbol]:
    """简单模式: A 股全池回测评分排名 (向后兼容)."""
    universe = codes or LIQUID_STOCKS
    results: list[RankedSymbol] = []

    for code, name in universe:
        try:
            prices = _load_stock_prices(code)
            if prices is None:
                continue
            ind = _score_one(prices)
            if ind is None:
                continue
            results.append(RankedSymbol(symbol=code, name=name, **ind))
        except Exception:
            pass

    results.sort(key=lambda x: x.score, reverse=True)
    return results[:top_n]


def rank_futures(top_n: int = 5) -> list[RankedSymbol]:
    """简单模式: 期货全池回测评分排名 (向后兼容)."""
    results: list[RankedSymbol] = []

    for sym, name in FUTURES_UNIVERSE:
        try:
            prices = _load_futures_prices(sym)
            if prices is None:
                continue
            ind = _score_one(prices)
            if ind is None:
                continue
            results.append(RankedSymbol(symbol=sym, name=name, **ind))
        except Exception:
            pass

    results.sort(key=lambda x: x.score, reverse=True)
    return results[:top_n]


# ═══════════════════════════════════════════════════════════════════════
# 增强版排名 (v0.6): 委托到统一管线引擎 pipeline.py
#   6步管线: 策略初筛→ 七日内新闻→ 五行分析→ Top10精选
#            → 二次策略分析(多时间窗口)→ 综合排名+3d/7d/30d预测
# ═══════════════════════════════════════════════════════════════════════

def rank_stocks_enhanced(
    codes: list[tuple[str, str]] | None = None,
    top_n: int = 10,
    use_news: bool = True,
    use_wuxing: bool = True,
    wuxing_weight: float = 0.05,
    apply_correction: bool = False,
    round1_min_score: float = 40.0,
) -> list[RankedSymbol]:
    """6步增强管线 — 委托到 pipeline.run_stock_pipeline()."""
    from .ashare_pipeline import run_stock_pipeline

    results, _log = run_stock_pipeline(
        top_n=top_n, use_news=use_news, use_wuxing=use_wuxing,
        wuxing_weight=wuxing_weight, round1_min_score=round1_min_score,
    )
    out = []
    for pr in results:
        out.append(RankedSymbol(
            symbol=pr.symbol, name=pr.name,
            score=pr.round1_score, signal=pr.signal,
            sma_score=pr.sma_score, rsi_score=pr.rsi_score,
            boll_score=pr.boll_score, mom_score=pr.mom_score,
            last_price=pr.last_price,
            news_sentiment=(pr.news_score - 50) / 40,
            news_label=pr.news_label,
            wuxing_score_val=pr.wuxing_score,
            wuxing_element=pr.wuxing_element,
            wuxing_relation=pr.wuxing_relation,
            corrected_score=pr.final_score,
        ))
    return out


def rank_futures_enhanced(
    top_n: int = 10,
    use_news: bool = True,
    use_wuxing: bool = True,
    wuxing_weight: float = 0.05,
    apply_correction: bool = False,
    round1_min_score: float = 40.0,
) -> list[RankedSymbol]:
    """6步增强管线 — 委托到 pipeline.run_futures_pipeline()."""
    from .ashare_pipeline import run_futures_pipeline

    results, _log = run_futures_pipeline(
        top_n=top_n, use_news=use_news, use_wuxing=use_wuxing,
        wuxing_weight=wuxing_weight, round1_min_score=round1_min_score,
    )
    out = []
    for pr in results:
        out.append(RankedSymbol(
            symbol=pr.symbol, name=pr.name,
            score=pr.round1_score, signal=pr.signal,
            sma_score=pr.sma_score, rsi_score=pr.rsi_score,
            boll_score=pr.boll_score, mom_score=pr.mom_score,
            last_price=pr.last_price,
            news_sentiment=(pr.news_score - 50) / 40,
            news_label=pr.news_label,
            wuxing_score_val=pr.wuxing_score,
            wuxing_element=pr.wuxing_element,
            wuxing_relation=pr.wuxing_relation,
            corrected_score=pr.final_score,
        ))
    return out


def to_dict(r: RankedSymbol) -> dict:
    return {
        "symbol": r.symbol, "name": r.name,
        "score": r.score, "signal": r.signal,
        "sma_score": r.sma_score, "rsi_score": r.rsi_score,
        "boll_score": r.boll_score, "mom_score": r.mom_score,
        "last_price": r.last_price,
        "change_1w_pct": r.change_1w_pct, "change_1m_pct": r.change_1m_pct,
        "sharpe": r.sharpe,
        "total_return_pct": r.total_return_pct,
        "max_drawdown_pct": r.max_drawdown_pct,
        "news_sentiment": r.news_sentiment, "news_label": r.news_label,
        "wuxing_score": r.wuxing_score_val,
        "wuxing_element": r.wuxing_element,
        "wuxing_relation": r.wuxing_relation,
        "corrected_score": r.corrected_score,
    }


def to_pipeline_dict(r) -> dict:
    """将 PipelineResult 或 RankedSymbol 转为完整多维度 dict."""
    from .ashare_pipeline import PipelineResult, result_to_dict
    if isinstance(r, PipelineResult):
        return result_to_dict(r)
    return to_dict(r)
