"""预测自学习引擎 — 验证→调整→提升。

核心循环:
  1. 每天预测后自动归档 (logs/reports/forecast_*.json)
  2. 第二天自动验证: 回看昨天预测 vs 模拟"实际"走势
  3. 统计准确率: 按品种/信号分组
  4. 策略调整: 根据历史准确率动态调整 LLM 温度/置信度阈值/风控参数

数据结构:
  logs/tracker.json — 预测追踪表，每行一条预测+验证结果
  logs/strategy_params.json — 动态调整后的策略参数
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_LOG_DIR = Path(os.environ.get("QT_LOG_DIR", "logs"))
_TRACKER_FILE = _LOG_DIR / "tracker.json"
_PARAMS_FILE = _LOG_DIR / "strategy_params.json"

_tracker_logger = logging.getLogger("quanttrader.tracker")
_tracker_logger.setLevel(logging.DEBUG)
if not _tracker_logger.handlers:
    _fh = logging.FileHandler(_LOG_DIR / f"tracker_{dt.date.today().strftime('%Y%m%d')}.log", encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    _tracker_logger.addHandler(_fh)
log_tracker = _tracker_logger


# ══════════════════════════════════════════════════════════════════
# 数据结构
# ══════════════════════════════════════════════════════════════════


@dataclass
class TrackedPrediction:
    """一条被追踪的预测记录。"""

    id: str  # 唯一ID: {date}_{symbol}
    date: str  # 预测日期 YYYY-MM-DD
    symbol: str
    market: str  # stock/future
    signal: str  # BUY/SELL/HOLD/LONG/SHORT/NEUTRAL
    confidence: float
    forecast_price: float  # 预测时的价格
    direction: int  # 1=看涨 -1=看跌 0=中性
    hexagram: str = ""  # 卦象
    hexagram_sent: str = ""  # 吉凶
    news_sentiment: str = ""  # 新闻情绪
    llm_reason: str = ""  # LLM 理由

    # 验证字段 (第二天填入)
    verified: bool = False
    actual_price: float = 0.0  # 第二天的"实际"价格
    actual_change_pct: float = 0.0  # 实际涨跌%
    was_correct: bool | None = None  # 预测是否正确 (None=未验证)
    verified_date: str = ""


@dataclass
class PredictionStats:
    """预测统计 — 分组准确率。"""

    total: int = 0
    verified: int = 0
    correct: int = 0
    accuracy: float = 0.0

    # 分组统计
    by_signal: dict[str, dict] = field(default_factory=dict)  # {BUY: {total, correct}}
    by_hexagram: dict[str, dict] = field(default_factory=dict)  # {吉: {total, correct}}
    by_sentiment: dict[str, dict] = field(default_factory=dict)  # {bullish: {total, correct}}
    by_market: dict[str, dict] = field(default_factory=dict)  # {stock: {total, correct}}
    by_source: dict[str, dict] = field(default_factory=dict)  # {live/cold_start: {total, correct}}

    # 策略参数建议
    llm_temperature: float = 0.2
    min_confidence: float = 0.6
    stop_loss_pct: float = 0.08

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "verified": self.verified,
            "correct": self.correct,
            "accuracy": round(self.accuracy, 3),
            "by_signal": self.by_signal,
            "by_hexagram": self.by_hexagram,
            "by_sentiment": self.by_sentiment,
            "by_market": self.by_market,
            "by_source": self.by_source,
            "params": {
                "llm_temperature": self.llm_temperature,
                "min_confidence": self.min_confidence,
                "stop_loss_pct": self.stop_loss_pct,
            },
        }


# ══════════════════════════════════════════════════════════════════
# 追踪器
# ══════════════════════════════════════════════════════════════════


def _load_tracker() -> list[dict]:
    if _TRACKER_FILE.exists():
        try:
            data = json.loads(_TRACKER_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


def _save_tracker(records: list[dict]) -> None:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _TRACKER_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_TRACKER_FILE)  # 原子替换，防断电损坏


def prediction_source(record: dict) -> str:
    """判定一条记录的来源: "live"(每日真实预测) 或 "cold_start"(历史回填基线)。

    新记录带显式 source 字段；存量旧记录无该字段, 按 llm_reason 的
    "[cold_start" 前缀推断(两个冷启动回填函数写入的固定标记), 其余视为 live。
    冷启动样本是 SMA 基线信号, 与实盘预测能力无关——考核实盘命中率时必须分开,
    否则 3800+ 条基线会永久稀释真实预测的统计信号。
    """
    src = record.get("source")
    if src:
        return str(src)
    return "cold_start" if str(record.get("llm_reason", "")).startswith("[cold_start") else "live"


def record_prediction(
    symbol: str,
    market: str,
    signal: str,
    confidence: float,
    forecast_price: float,
    hexagram: str = "",
    hexagram_sent: str = "",
    news_sentiment: str = "",
    llm_reason: str = "",
    source: str = "live",
) -> str:
    """记录一条预测到追踪表。返回预测ID。"""
    today = dt.date.today().isoformat()
    pid = f"{today}_{symbol}_{market}"

    direction = 1 if signal in ("BUY", "LONG") else (-1 if signal in ("SELL", "SHORT") else 0)

    record = {
        "id": pid,
        "date": today,
        "symbol": symbol,
        "market": market,
        "signal": signal,
        "confidence": confidence,
        "forecast_price": forecast_price,
        "direction": direction,
        "hexagram": hexagram,
        "hexagram_sent": hexagram_sent,
        "news_sentiment": news_sentiment,
        "llm_reason": llm_reason[:200],
        "source": source,
        "verified": False,
        "actual_price": 0,
        "actual_change_pct": 0,
        "was_correct": None,
        "verified_date": "",
    }

    records = _load_tracker()
    # 如果今天已有同标的记录，更新它
    existing = [i for i, r in enumerate(records) if r.get("id") == pid]
    if existing:
        records[existing[0]] = record
    else:
        records.append(record)

    _save_tracker(records)
    log_tracker.info(f"记录预测: {pid} {signal} conf={confidence:.0%} @ {forecast_price:.2f}")
    return pid


def _fetch_actual_price(symbol: str, date: str) -> float | None:
    """获取标的在指定日期的收盘价：股票走 Sina 日K，期货走 akshare 主力连续。

    原实现只按股票拼 sh/sz 前缀，期货代码(RB/AG/M)会被误当作 szRB 拉取失败、
    恒返回 None → 实盘期货方向预测永远无法验证。此处按代码特征分流修复。
    """
    code = symbol.strip()
    # 期货：含字母且非 sh/sz/bj 前缀 → akshare 期货主力连续
    if any(ch.isalpha() for ch in code) and not code.lower().startswith(("sh", "sz", "bj")):
        try:
            from quanttrader.data.futures_history import get_futures_history

            fdf = get_futures_history(code, days=15)
            if fdf is not None and len(fdf) > 0:
                frow = fdf[fdf.index == pd.Timestamp(date)]
                if len(frow) > 0:
                    return float(frow["close"].iloc[-1])
        except Exception:
            pass
        return None

    import requests as _req

    try:
        # Normalize symbol: "600519" → "sh600519"
        code = symbol.strip()
        if code.startswith(("sh", "sz", "bj")):
            sina_code = code
        elif code.startswith(("6", "9")):
            sina_code = f"sh{code}"
        else:
            sina_code = f"sz{code}"

        s = _req.Session()
        s.trust_env = False
        r = s.get(
            "https://quotes.sina.cn/cn/api/jsonp_v2.php/var/CN_MarketDataService.getKLineData",
            params={"symbol": sina_code, "scale": "240", "ma": "no", "datalen": 10},
            timeout=10,
        )
        if r.status_code != 200:
            return None
        text = r.text.strip()
        start = text.find("([")
        end = text.rfind("])")
        if start == -1 or end == -1:
            return None
        klines = json.loads(text[start + 1 : end + 1])
        for kl in klines:
            if kl.get("day", "") == date:
                return float(kl["close"])
    except Exception:
        pass
    return None


def _next_trading_day(date: str) -> str:
    """预测日的下一交易日(近似)：日历日 +1 并跳过周末。

    A股/期货 T+1，需用下一交易日收盘价验证方向。原实现直接 +1 日历日，
    导致周五预测→周六(无行情)→_fetch_actual_price 恒为 None→该条预测
    永久无法验证，系统性丢失约 1/5 样本。跳过周末修正主要偏差；法定
    节假日仍由数据源无数据时的既有跳过逻辑兜底。
    """
    d = dt.date.fromisoformat(date) + dt.timedelta(days=1)
    while d.weekday() >= 5:  # 5=周六, 6=周日
        d += dt.timedelta(days=1)
    return d.isoformat()


def verify_predictions(date: str | None = None) -> list[dict]:
    """验证昨天(或指定日期)的预测 — 拉取真实收盘价对比。"""
    target_date = date or (dt.date.today() - dt.timedelta(days=1)).isoformat()
    records = _load_tracker()
    target = [r for r in records if r["date"] == target_date and not r.get("verified")]

    if not target:
        log_tracker.info(f"无需验证: {target_date} 无待验证预测")
        return []

    log_tracker.info(f"验证 {target_date} 的 {len(target)} 条预测...")

    # 验证日期 = 预测日期的下一个交易日(跳过周末)
    verify_date = _next_trading_day(target_date)

    for rec in target:
        actual = _fetch_actual_price(rec["symbol"], verify_date)

        if actual is None:
            # 无法获取真实数据时跳过，不伪造
            log_tracker.warning(f"  ⏭️ {rec['symbol']} 无法获取 {verify_date} 收盘价，跳过验证")
            continue

        actual_chg = (actual / rec["forecast_price"] - 1) * 100 if rec["forecast_price"] > 0 else 0

        direction = rec["direction"]
        was_correct = None
        if direction == 1:
            was_correct = actual_chg > 0.3
        elif direction == -1:
            was_correct = actual_chg < -0.3
        elif rec["signal"] in ("HOLD", "NEUTRAL"):
            was_correct = abs(actual_chg) < 1.0
        else:
            was_correct = None

        rec["verified"] = True
        rec["actual_price"] = round(actual, 2)
        rec["actual_change_pct"] = round(actual_chg, 2)
        rec["was_correct"] = was_correct
        rec["verified_date"] = dt.date.today().isoformat()

        mark = "✅" if was_correct else ("❌" if was_correct is False else "⏭️")
        log_tracker.info(
            f"  {mark} {rec['symbol']} {rec['signal']} "
            f"预测 ¥{rec['forecast_price']:.2f} → 实际 ¥{actual:.2f} ({actual_chg:+.1f}%)"
        )

    _save_tracker(records)
    verified_count = sum(1 for r in target if r.get("verified") and r["was_correct"] is not None)
    correct_count = sum(1 for r in target if r.get("was_correct"))
    log_tracker.info(f"验证完成: {correct_count}/{verified_count} 正确 (跳过 {len(target) - verified_count} 条)")
    return target


def compute_stats(source: str | None = None) -> PredictionStats:
    """计算已验证预测的准确率统计。

    Args:
        source: None=全部(含冷启动回填, 向后兼容自动调参用途);
                "live"=只统计每日真实预测; "cold_start"=只统计回填基线。
    """
    records = _load_tracker()
    if source is not None:
        records = [r for r in records if prediction_source(r) == source]
    verified = [r for r in records if r.get("verified") and r.get("was_correct") is not None]

    stats = PredictionStats()
    stats.total = len(records)
    stats.verified = len(verified)
    stats.correct = sum(1 for r in verified if r["was_correct"])

    if stats.verified > 0:
        stats.accuracy = stats.correct / stats.verified
    else:
        stats.accuracy = 0.0

    # 分组: 按信号
    for sig in ["BUY", "SELL", "HOLD", "LONG", "SHORT", "NEUTRAL"]:
        subset = [r for r in verified if r["signal"] == sig]
        if subset:
            correct = sum(1 for r in subset if r["was_correct"])
            stats.by_signal[sig] = {
                "total": len(subset),
                "correct": correct,
                "accuracy": round(correct / len(subset), 3),
            }

    # 分组: 按卦象吉凶
    for sent in ["吉", "平", "凶", "注意"]:
        subset = [r for r in verified if r.get("hexagram_sent") == sent]
        if subset:
            correct = sum(1 for r in subset if r["was_correct"])
            stats.by_hexagram[sent] = {
                "total": len(subset),
                "correct": correct,
                "accuracy": round(correct / len(subset), 3),
            }

    # 分组: 按新闻情绪
    for sent in ["bullish", "bearish", "neutral"]:
        subset = [r for r in verified if r.get("news_sentiment") == sent]
        if subset:
            correct = sum(1 for r in subset if r["was_correct"])
            stats.by_sentiment[sent] = {
                "total": len(subset),
                "correct": correct,
                "accuracy": round(correct / len(subset), 3),
            }

    # 分组: 按市场
    for mkt in ["stock", "future"]:
        subset = [r for r in verified if r.get("market") == mkt]
        if subset:
            correct = sum(1 for r in subset if r["was_correct"])
            stats.by_market[mkt] = {
                "total": len(subset),
                "correct": correct,
                "accuracy": round(correct / len(subset), 3),
            }

    # 分组: 按来源(真实预测 vs 冷启动回填) — 实盘考核只看 live 一档
    for src in ["live", "cold_start"]:
        subset = [r for r in verified if prediction_source(r) == src]
        if subset:
            correct = sum(1 for r in subset if r["was_correct"])
            stats.by_source[src] = {
                "total": len(subset),
                "correct": correct,
                "accuracy": round(correct / len(subset), 3),
            }

    # ── 策略参数调整 ──
    stats.llm_temperature = _adjust_temperature(stats)
    stats.min_confidence = _adjust_min_confidence(stats)
    stats.stop_loss_pct = _adjust_stop_loss(stats)

    return stats


def should_use_divination() -> bool:
    """玄学推演已下线，恒为 False。"""
    return False


def divination_weight() -> float:
    """玄学推演已下线，权重恒为 0。"""
    return 0.0


# ══════════════════════════════════════════════════════════════════
# 策略参数自适应
# ══════════════════════════════════════════════════════════════════


def _adjust_temperature(stats: PredictionStats) -> float:
    """根据历史准确率动态调整 LLM temperature。

    准确率高 → 降低温度(更确定) | 准确率低 → 提高温度(更多探索)
    """
    if stats.verified < 10:
        return 0.2  # 默认
    acc = stats.accuracy
    if acc >= 0.70:
        return 0.10  # 高准确率 → 更保守、更确定
    elif acc >= 0.55:
        return 0.20
    elif acc >= 0.40:
        return 0.30  # 低准确率 → 更多随机性, 探索不同信号
    else:
        return 0.40  # 很差 → 大幅探索


def _adjust_min_confidence(stats: PredictionStats) -> float:
    """根据准确率调整最低置信度阈值。

    准确率高 → 放宽（让更多白名单信号通过）
    准确率低 → 轻微收紧，但绝不超过 0.60（旧版 0.75 导致零成交）
    """
    from .engine.confidence_policy import DEFAULT_MIN_CONFIDENCE, MAX_MIN_CONFIDENCE

    if stats.verified < 10:
        return DEFAULT_MIN_CONFIDENCE
    acc = stats.accuracy
    if acc >= 0.65:
        return 0.42
    if acc >= 0.55:
        return 0.48
    if acc >= 0.50:
        return DEFAULT_MIN_CONFIDENCE
    return min(0.55, MAX_MIN_CONFIDENCE)


def _adjust_stop_loss(stats: PredictionStats) -> float:
    """根据准确率调整止损百分比。

    准确率高 → 可以放宽止损(给利润更多空间)
    准确率低 → 收紧止损(更快截断亏损)
    """
    if stats.verified < 10:
        return 0.08
    acc = stats.accuracy
    if acc >= 0.70:
        return 0.10
    elif acc >= 0.50:
        return 0.08
    else:
        return 0.05  # 准确率低 → 紧止损


def load_strategy_params() -> dict[str, Any]:
    """加载动态策略参数。"""
    from .engine.confidence_policy import migrate_strategy_params

    if _PARAMS_FILE.exists():
        try:
            params = json.loads(_PARAMS_FILE.read_text(encoding="utf-8"))
            return migrate_strategy_params(params)
        except Exception:
            pass
    return migrate_strategy_params({
        "llm_temperature": 0.2,
        "min_confidence": 0.5,
        "stop_loss_pct": 0.08,
    })


def save_strategy_params(params: dict[str, Any]) -> None:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _PARAMS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(params, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_PARAMS_FILE)


def _build_whitelist_tiers(
    symbol_stats: dict[str, list[bool]],
    *,
    relaxed: bool = False,
) -> tuple[list[dict], list[dict], list[dict]]:
    """从 symbol+direction 统计生成分层白名单."""
    tier1, tier2, tier3 = [], [], []
    if relaxed:
        rules = (
            (75.0, 15, "tier1"),
            (65.0, 15, "tier2"),
            (55.0, 20, "tier3"),
        )
    else:
        rules = (
            (75.0, 20, "tier1"),
            (65.0, 20, "tier2"),
            (60.0, 30, "tier3"),
        )

    ranked: list[tuple[float, int, str]] = []
    for key, results in symbol_stats.items():
        n = len(results)
        if n == 0:
            continue
        acc = sum(results) / n * 100
        placed = False
        for min_acc, min_n, tier in rules:
            if acc >= min_acc and n >= min_n:
                bucket = {"name": key, "acc": round(acc, 1), "n": n, "tier": tier}
                if tier == "tier1":
                    tier1.append(bucket)
                elif tier == "tier2":
                    tier2.append(bucket)
                else:
                    tier3.append(bucket)
                placed = True
                break
        if not placed:
            ranked.append((acc, n, key))

    # 绝对门槛无入选时：按准确率分位数取 Top 组合 (利用 43K 级历史样本)
    if not (tier1 or tier2 or tier3) and ranked:
        ranked.sort(key=lambda x: (x[0], x[1]), reverse=True)
        for acc, n, key in ranked[:16]:
            if n < 10:
                continue
            if acc >= 54 and n >= 25:
                tier = "tier1"
            elif acc >= 51 and n >= 15:
                tier = "tier2"
            elif acc >= 48:
                tier = "tier3"
            else:
                continue
            bucket = {"name": key, "acc": round(acc, 1), "n": n, "tier": tier}
            if tier == "tier1":
                tier1.append(bucket)
            elif tier == "tier2":
                tier2.append(bucket)
            else:
                tier3.append(bucket)

    return tier1, tier2, tier3


def rebuild_whitelist_from_tracker(relaxed: bool = True) -> dict[str, Any]:
    """用 tracker 已验证记录重建 SymbolFilter 白名单并写入 strategy_params."""
    records = _load_tracker()
    verified = [r for r in records if r.get("verified") and r.get("was_correct") is not None]

    symbol_stats: dict[str, list[bool]] = {}
    for r in verified:
        sym = str(r.get("symbol", "")).upper().rstrip("0")
        sig = r.get("signal", "")
        if sig not in ("BUY", "SELL"):
            continue
        key = f"{sym}+{sig}"
        symbol_stats.setdefault(key, []).append(bool(r.get("was_correct")))

    tier1, tier2, tier3 = _build_whitelist_tiers(symbol_stats, relaxed=relaxed)
    all_combos = sorted(tier1 + tier2 + tier3, key=lambda x: x["acc"], reverse=True)

    params = load_strategy_params()
    params["best_combos_10d"] = all_combos
    params["whitelist_rebuilt_at"] = dt.datetime.now().isoformat()
    params["whitelist_mode"] = "relaxed" if relaxed else "strict"
    params["tier_summary"] = {"tier1": len(tier1), "tier2": len(tier2), "tier3": len(tier3)}
    save_strategy_params(params)

    log_tracker.info(
        f"白名单重建: T1={len(tier1)} T2={len(tier2)} T3={len(tier3)} "
        f"(样本={len(verified)} 组合={len(symbol_stats)})"
    )
    return {
        "tier1": len(tier1),
        "tier2": len(tier2),
        "tier3": len(tier3),
        "combos": all_combos[:20],
        "verified": len(verified),
    }


def auto_tune() -> dict[str, Any]:
    """自动调参: 计算统计 → 调整参数 → 分层白名单 → 保存。返回新参数。"""
    stats = compute_stats()

    # ── 计算 per-symbol+direction 准确率，生成分层白名单 ──
    records = _load_tracker()
    verified = [r for r in records if r.get("verified") and r.get("was_correct") is not None]

    symbol_stats: dict[str, list[bool]] = {}
    for r in verified:
        sym = r.get("symbol", "")
        sig = r.get("signal", "")
        if sig not in ("BUY", "SELL"):
            continue
        key = f"{sym}+{sig}"
        if key not in symbol_stats:
            symbol_stats[key] = []
        symbol_stats[key].append(r.get("was_correct", False))

    # 分层构建白名单 (冷启动数据用 relaxed 门槛)
    tier1, tier2, tier3 = _build_whitelist_tiers(symbol_stats, relaxed=True)
    if not (tier1 or tier2 or tier3) and len(verified) >= 50:
        tier1, tier2, tier3 = _build_whitelist_tiers(symbol_stats, relaxed=False)

    all_combos = tier1 + tier2 + tier3
    all_combos.sort(key=lambda x: x["acc"], reverse=True)

    # SF 白名单平均准确率 (用于 ML 协调)
    sf_acc = 0.0
    if all_combos:
        sf_acc = sum(c["acc"] for c in all_combos) / len(all_combos) / 100.0

    # ML v15 OOS (若模型存在)
    ml_acc = 0.0
    try:
        from pathlib import Path

        import joblib
        mp = Path("logs/ml_v15_GLOBAL.pkl")
        if mp.exists():
            md = joblib.load(mp)
            ml_acc = float(md.get("oos_accuracy", 0))
    except Exception:
        pass

    from .engine.sf_ml_conflicts import aggregate_for_auto_tune
    from .engine.sf_ml_coordinator import auto_tune_sf_ml_params, merge_sf_ml_into_params

    conflict_count, sf_won_conflict = aggregate_for_auto_tune()
    sf_ml = auto_tune_sf_ml_params(
        sf_accuracy=sf_acc,
        ml_accuracy=ml_acc,
        conflict_count=conflict_count,
        sf_won_when_conflict=sf_won_conflict,
    )

    params = {
        "version": "v15_tiered_filter",
        "llm_temperature": stats.llm_temperature,
        "min_confidence": stats.min_confidence,
        "stop_loss_pct": stats.stop_loss_pct,
        "updated_at": dt.datetime.now().isoformat(),
        "based_on": f"{stats.verified} verified predictions, accuracy={stats.accuracy:.1%}",
        "total_records": stats.total,
        "verified": stats.verified,
        "overall_accuracy": round(stats.accuracy * 100, 1),
        "best_combos_10d": all_combos,
        "tier_summary": {
            "tier1": len(tier1),
            "tier2": len(tier2),
            "tier3": len(tier3),
        },
        "trading_rules": {
            "strategy": "分层白名单 + 投票器 + LLM确认 + M专属 + 时间过滤",
            "hold_period": "10天 (M豆粕7天)",
            "tier1": "acc>=75% n>=20 → 仓位×1.2",
            "tier2": "acc>=65% n>=20 → 标准仓位",
            "tier3": "acc>=60% n>=30 → 仓位×0.8",
            "stop_loss": "ATR×1.5 (M豆粕ATR×1.0)",
            "take_profit": "ATR×3 (M豆粕ATR×2.5)",
        },
    }
    params = merge_sf_ml_into_params(params, sf_ml)
    from .engine.confidence_policy import migrate_strategy_params
    params = migrate_strategy_params(params)
    save_strategy_params(params)

    sf_ml_raw = params.get("sf_ml")
    sf_ml_cfg = sf_ml_raw if isinstance(sf_ml_raw, dict) else {}
    log_tracker.info(
        f"自动调参: 准确率={stats.accuracy:.1%} ({stats.correct}/{stats.verified}) → "
        f"temperature={params['llm_temperature']:.2f} "
        f"min_conf={params['min_confidence']:.0%} "
        f"stop_loss={params['stop_loss_pct']:.0%} "
        f"白名单: T1={len(tier1)} T2={len(tier2)} T3={len(tier3)} "
        f"sf_ml={sf_ml_cfg.get('ml_mode', 'advisory')} "
        f"use_v15={sf_ml_cfg.get('use_v15', False)}"
    )
    return params


# ══════════════════════════════════════════════════════════════════
# 便捷函数 — 每天自动调用
# ══════════════════════════════════════════════════════════════════


def daily_cycle(
    *,
    retrain_ml: bool = True,
    bootstrap_if_empty: bool = True,
) -> dict[str, Any]:
    """每日循环: 验证 → 统计 → 调参 → 可选 v15 重训。返回状态。"""
    today = dt.date.today()

    log_tracker.info("═" * 50)
    log_tracker.info(f"每日自学习循环 — {today.isoformat()}")
    log_tracker.info("═" * 50)

    if bootstrap_if_empty:
        bootstrap_self_learning_if_needed()

    # 1. 回溯验证: 最近7天中未验证的预测
    all_verified = []
    for days_back in range(1, 8):
        check_date = (today - dt.timedelta(days=days_back)).isoformat()
        batch = verify_predictions(check_date)
        all_verified.extend(batch)
    verified = all_verified

    # 1.5 高低点闭环: 回溯验证近7天 HL 预测 + 记录今日预测(供 T+horizon 验证)。
    #     此前 HL 链路因数据源失效从未积累过 live 样本, 接入每日循环后自动滚动。
    hl_verified: list[dict] = []
    for days_back in range(1, 8):
        check_date = (today - dt.timedelta(days=days_back)).isoformat()
        try:
            hl_verified.extend(verify_hl_predictions(check_date))
        except Exception as e:
            log_tracker.debug(f"HL验证跳过 {check_date}: {e}")
    try:
        hl_recorded = record_daily_hl_predictions()
    except Exception as e:
        log_tracker.debug(f"HL记录跳过: {e}")
        hl_recorded = 0

    # 2. 统计
    stats = compute_stats()

    # 3. 调参
    params = auto_tune()

    retrain_result = None
    if retrain_ml:
        try:
            from .ml.retrain_pipeline import maybe_retrain_v15

            retrain_result = maybe_retrain_v15(dry_run=False)
        except Exception as e:
            log_tracker.debug(f"v15 重训跳过: {e}")
            retrain_result = {"skipped": True, "error": str(e)}

    edge_result = None
    try:
        from .edge_journal import daily_edge_cycle

        edge_result = daily_edge_cycle()
        log_tracker.info(
            f"Edge台账: logged={edge_result.get('logged_today')} "
            f"filled={edge_result.get('filled_total')} "
            f"acc={edge_result.get('overall_accuracy')}"
        )
    except Exception as e:
        log_tracker.debug(f"Edge台账跳过: {e}")

    result = {
        "date": dt.date.today().isoformat(),
        "verified_yesterday": len(verified),
        "newly_correct": sum(1 for r in verified if r.get("was_correct")),
        "total_verified": stats.verified,
        "total_accuracy": round(stats.accuracy, 3),
        "params": params,
        "by_signal": stats.by_signal,
        "by_hexagram": stats.by_hexagram,
        "ml_retrain": retrain_result,
        "edge_journal": edge_result,
        "hl_verified": len(hl_verified),
        "hl_recorded": hl_recorded,
        "hl_stats": compute_hl_stats(),
    }

    log_tracker.info(f"循环结果: 验证{len(verified)}条 累计准确率{stats.accuracy:.1%}")
    return result


# ══════════════════════════════════════════════════════════════════
# 冷启动：用历史回测模拟填充 tracker，让自学习立即生效
# ══════════════════════════════════════════════════════════════════


def cold_start_bootstrap(symbol: str = "600519", days: int = 120, min_records: int = 20) -> dict:
    """用 SMA 策略回测历史数据，模拟「过去N天每天做了一次预测」。

    原理:
      1. 拉取最近 days 天的日线数据 (akshare → synthetic fallback)
      2. 用 SMA 交叉策略生成信号
      3. 对每个有信号的交易日，记录为一条「预测」
      4. 用下一天的真实收盘价验证方向是否正确
      5. 写入 tracker.json，让 compute_stats() 立即可用

    返回: {"seeded": N, "accuracy": X.X%}
    """

    records = _load_tracker()
    existing_ids = {r.get("id") for r in records}

    # 1) 拉数据
    prices = None
    try:
        from quanttrader.data.base import BarRequest, get_feed

        req = BarRequest(symbol=symbol, start="", end="", interval="1d")
        prices = get_feed("akshare").history(req)
    except Exception as e:
        log_tracker.info(f"akshare 拉取失败 ({e})，尝试 synthetic fallback")

    # Fallback: 用 synthetic 生成合理的模拟行情
    if prices is None or len(prices) < 30:
        try:
            from quanttrader.data.base import BarRequest, get_feed

            req = BarRequest(symbol=symbol, start="", end="", interval="1d")
            prices = get_feed("synthetic").history(req)
        except Exception as e:
            log_tracker.warning(f"冷启动拉取数据失败: {e}")
            return {"seeded": 0, "error": str(e)}

    if prices is None or len(prices) < 30:
        return {"seeded": 0, "error": "数据不足30条"}

    # 限制天数
    if len(prices) > days:
        prices = prices.tail(days)

    # 2) 生成信号
    from quanttrader.strategy.sma_cross import SmaCrossStrategy

    strat = SmaCrossStrategy(fast=20, slow=60)
    signals = strat.generate(prices)

    # 3) 模拟预测：每个 BUY/SELL 信号日记录一条
    closes = prices["close"].astype(float)
    seeded = 0
    today = dt.date.today()

    for i in range(60, len(prices) - 1):  # 从第60根开始（SMA60需要）
        sig_val = int(signals.iloc[i])
        if sig_val == 0:
            continue  # HOLD 不记录

        sig_name = "BUY" if sig_val == 1 else "SELL"
        forecast_price = float(closes.iloc[i])
        next_price = float(closes.iloc[i + 1])
        actual_chg_pct = (next_price / forecast_price - 1) * 100

        # 方向判断
        if sig_name == "BUY":
            was_correct = actual_chg_pct > 0.1  # 涨了就算对
        else:
            was_correct = actual_chg_pct < -0.1  # 跌了就算对

        # 构造日期：用数据的实际日期
        ts = prices.index[i]
        if hasattr(ts, "date"):
            pred_date = ts.date().isoformat()
        else:
            pred_date = str(ts)[:10]

        pid = f"{pred_date}_{symbol}_stock"

        # 跳过已存在的记录
        if pid in existing_ids:
            continue

        # 冷启动记录不再写入卦象字段（玄学已下线）
        record = {
            "id": pid,
            "date": pred_date,
            "symbol": symbol,
            "market": "stock",
            "signal": sig_name,
            "confidence": 0.65,
            "forecast_price": round(forecast_price, 2),
            "direction": 1 if sig_name == "BUY" else -1,
            "hexagram": "",
            "hexagram_sent": "",
            "news_sentiment": "neutral",
            "llm_reason": "[cold_start] SMA策略信号",
            "source": "cold_start",
            "verified": True,
            "actual_price": round(next_price, 2),
            "actual_change_pct": round(actual_chg_pct, 2),
            "was_correct": was_correct,
            "verified_date": pred_date,
        }
        records.append(record)
        existing_ids.add(pid)
        seeded += 1

    _save_tracker(records)

    # 4) 立即统计
    stats = compute_stats()
    log_tracker.info(
        f"冷启动完成: 注入{seeded}条模拟预测 → 准确率={stats.accuracy:.1%} ({stats.correct}/{stats.verified})"
    )
    return {"seeded": seeded, "accuracy": round(stats.accuracy, 3), "total_verified": stats.verified}


def bootstrap_self_learning_if_needed(
    min_verified: int = 30,
    stock_symbol: str = "600519",
    futures_symbols: list[str] | None = None,
) -> dict[str, Any]:
    """冷启动自学习：tracker 样本不足时用历史 K 线回填预测记录。"""
    stats = compute_stats()
    if stats.verified >= min_verified:
        return {"bootstrapped": False, "verified": stats.verified}

    log_tracker.info(
        f"自学习冷启动: verified={stats.verified} < {min_verified}，开始回填历史样本"
    )
    stock_res = cold_start_bootstrap(symbol=stock_symbol, days=800, min_records=10)
    fut_res = cold_start_futures_bootstrap(
        symbols=futures_symbols or ["M", "RB", "AG", "AU", "I", "SI"],
        days=1260,
    )
    auto_tune()
    stats2 = compute_stats()
    rebuild_whitelist_from_tracker(relaxed=True)
    return {
        "bootstrapped": True,
        "stock": stock_res,
        "futures": fut_res,
        "verified_after": stats2.verified,
        "accuracy_after": round(stats2.accuracy, 3),
    }


def cold_start_futures_bootstrap(
    symbols: list[str],
    days: int = 1260,
    min_bars: int = 120,
) -> dict[str, Any]:
    """用期货主力连续日线 + SMA 信号回填 tracker（利用长历史样本）。"""
    from .data.futures_history import get_futures_history
    from .strategy.sma_cross import SmaCrossStrategy

    records = _load_tracker()
    existing_ids = {r.get("id") for r in records}
    seeded = 0

    for sym in symbols:
        try:
            prices = get_futures_history(sym, days=days)
        except Exception as e:
            log_tracker.debug(f"期货冷启动跳过 {sym}: {e}")
            continue
        if prices is None or len(prices) < min_bars:
            continue

        strat = SmaCrossStrategy(fast=20, slow=60)
        signals = strat.generate(prices)
        closes = prices["close"].astype(float)

        for i in range(60, len(prices) - 1):
            sig_val = int(signals.iloc[i])
            if sig_val == 0:
                continue
            sig_name = "BUY" if sig_val == 1 else "SELL"
            forecast_price = float(closes.iloc[i])
            next_price = float(closes.iloc[i + 1])
            actual_chg_pct = (next_price / forecast_price - 1) * 100
            was_correct = actual_chg_pct > 0.1 if sig_name == "BUY" else actual_chg_pct < -0.1

            ts = prices.index[i]
            pred_date = ts.date().isoformat() if hasattr(ts, "date") else str(ts)[:10]
            pid = f"{pred_date}_{sym}_future"
            if pid in existing_ids:
                continue

            records.append({
                "id": pid,
                "date": pred_date,
                "symbol": sym,
                "market": "future",
                "signal": sig_name,
                "confidence": 0.58,
                "forecast_price": round(forecast_price, 2),
                "direction": sig_val,
                "hexagram": "",
                "hexagram_sent": "",
                "news_sentiment": "neutral",
                "llm_reason": "[cold_start_futures] SMA信号",
                "source": "cold_start",
                "verified": True,
                "actual_price": round(next_price, 2),
                "actual_change_pct": round(actual_chg_pct, 2),
                "was_correct": was_correct,
                "verified_date": pred_date,
            })
            existing_ids.add(pid)
            seeded += 1

    if seeded:
        _save_tracker(records)
        log_tracker.info(f"期货冷启动: 注入 {seeded} 条 ({len(symbols)} 品种)")

    return {"seeded": seeded, "symbols": symbols}


# ══════════════════════════════════════════════════════════════════
# 高低点预测追踪
# ══════════════════════════════════════════════════════════════════

_HL_PREDICTIONS_FILE = _LOG_DIR / "hl_predictions.json"

# 高低点验证窗口(交易日)：与 predictor.hl_predict.predict_range 默认 horizon 对齐。
HL_VERIFY_HORIZON = 2


def record_hl_prediction(
    symbol: str,
    predicted_high: float,
    predicted_low: float,
    current_price: float,
    regime: str = "unknown",
    method_weights: dict | None = None,
) -> None:
    """记录高低点预测，用于后续验证。"""
    records = _load_hl_predictions()
    today = dt.date.today().isoformat()
    pred_id = f"{today}_{symbol}"

    record = {
        "id": pred_id,
        "date": today,
        "symbol": symbol,
        "current_price": round(current_price, 2),
        "predicted_high": round(predicted_high, 2),
        "predicted_low": round(predicted_low, 2),
        "regime": regime,
        "method_weights": method_weights or {},
        "verified": False,
        "actual_high": 0.0,
        "actual_low": 0.0,
        "high_error_pct": 0.0,
        "low_error_pct": 0.0,
        "verified_date": "",
    }

    # 覆盖同日同品种
    records = [r for r in records if r.get("id") != pred_id]
    records.append(record)
    _save_hl_predictions(records)
    log_tracker.info(f"HL记录: {symbol} 高={predicted_high:,.2f} 低={predicted_low:,.2f} regime={regime}")


# 每日 HL 例行预测的默认品种池(与冷启动/覆盖率校准所用主力品种一致)
HL_DAILY_SYMBOLS = ["AU", "AG", "I", "M", "RB", "SI"]


def record_daily_hl_predictions(symbols: list[str] | None = None) -> int:
    """对品种池逐一预测未来 horizon 天高低点并落盘, 返回成功记录数。

    供 daily_cycle 每日例行调用: 今日 record → T+horizon 由
    verify_hl_predictions 自动验证, 持续积累 live 样本。同日重复调用
    会覆盖同 id 记录, 天然幂等; 单品种失败不影响其余品种。
    """
    from quanttrader.data.futures_history import get_futures_history
    from quanttrader.data.synthetic_futures_provider import is_synthetic
    from quanttrader.predictor.hl_predict import predict_range

    recorded = 0
    for sym in symbols or HL_DAILY_SYMBOLS:
        try:
            df = get_futures_history(sym, days=120)
            # 合成数据只在无 akshare 的测试环境出现, 不得混入 live 追踪
            if df is None or len(df) < 60 or is_synthetic(df):
                continue
            pred = predict_range(
                sym,
                df["close"].to_numpy(dtype=float),
                df["high"].to_numpy(dtype=float),
                df["low"].to_numpy(dtype=float),
                horizon=HL_VERIFY_HORIZON,
            )
            if pred is None:
                continue
            record_hl_prediction(
                symbol=sym,
                predicted_high=pred.predicted_high,
                predicted_low=pred.predicted_low,
                current_price=pred.current_price,
                regime=pred.volatility,
            )
            recorded += 1
        except Exception as e:
            log_tracker.debug(f"HL每日记录失败 {sym}: {e}")
    if recorded:
        log_tracker.info(f"HL每日记录: {recorded}/{len(symbols or HL_DAILY_SYMBOLS)} 品种")
    return recorded


def _hl_actual_range(df, pred_date: str, horizon: int) -> tuple[float, float] | None:
    """从日线 df 取「预测日之后前 horizon 个交易日」的实际最高/最低价。

    修正原验证口径三处偏差：
    1) index > pred_date 严格排除预测日当天(其高低点在预测时已部分已知，计入即前视)；
    2) .head(horizon) 固定窗口长度，与「预测未来 horizon 天高低点」语义对齐，
       替代原「预测日至今」随距今天数漂移的可变窗口；
    3) 窗口内无交易日时返回 None(暂不验证)，替代原退化到 df.tail(1) 的错配。
    """
    if df is None or len(df) == 0:
        return None
    future = df[df.index > pd.Timestamp(pred_date)]
    if len(future) < 1:
        return None
    window = future.head(horizon)
    return float(window["high"].max()), float(window["low"].min())


def verify_hl_predictions(date: str | None = None, horizon: int = HL_VERIFY_HORIZON) -> list[dict]:
    """验证指定日期的高低点预测(用 akshare 期货主力连续真实数据)。"""
    records = _load_hl_predictions()
    if date is None:
        date = (dt.date.today() - dt.timedelta(days=1)).isoformat()

    unverified = [r for r in records if r["date"] == date and not r.get("verified")]
    if not unverified:
        return []

    verified = []
    for rec in unverified:
        symbol = rec["symbol"]
        try:
            # 原实现依赖已禁用的 sina_futures.get_history(抛 NotImplementedError→验证从不发生)，
            # 改用可用的 akshare 主力连续真实数据源。
            from quanttrader.data.futures_history import get_futures_history
            df = get_futures_history(symbol, days=horizon + 20)
            rng = _hl_actual_range(df, date, horizon)
            if rng is None:
                continue
            actual_high, actual_low = rng

            high_err = abs(rec["predicted_high"] - actual_high) / actual_high * 100 if actual_high else 0.0
            low_err = abs(rec["predicted_low"] - actual_low) / actual_low * 100 if actual_low else 0.0

            rec["verified"] = True
            rec["actual_high"] = round(actual_high, 2)
            rec["actual_low"] = round(actual_low, 2)
            rec["high_error_pct"] = round(high_err, 3)
            rec["low_error_pct"] = round(low_err, 3)
            rec["verified_date"] = dt.date.today().isoformat()
            verified.append(rec)

        except Exception as e:
            log_tracker.debug(f"HL验证失败 {symbol}: {e}")

    _save_hl_predictions(records)
    if verified:
        log_tracker.info(f"HL验证: {len(verified)}条 高点均误差={np.mean([r['high_error_pct'] for r in verified]):.2f}% 低点均误差={np.mean([r['low_error_pct'] for r in verified]):.2f}%")
    return verified


def compute_hl_stats() -> dict:
    """统计高低点预测准确率。"""
    records = _load_hl_predictions()
    verified = [r for r in records if r.get("verified")]
    if not verified:
        return {"total": 0, "high_avg_error": 0, "low_avg_error": 0}

    high_errors = [r["high_error_pct"] for r in verified]
    low_errors = [r["low_error_pct"] for r in verified]

    return {
        "total": len(verified),
        "high_avg_error": round(float(np.mean(high_errors)), 3),
        "low_avg_error": round(float(np.mean(low_errors)), 3),
        "high_median_error": round(float(np.median(high_errors)), 3),
        "low_median_error": round(float(np.median(low_errors)), 3),
        "high_acc_3pct": round(sum(1 for e in high_errors if e < 3) / len(high_errors), 3),
        "low_acc_3pct": round(sum(1 for e in low_errors if e < 3) / len(low_errors), 3),
    }


def auto_tune_hl() -> dict:
    """根据验证结果更新 hl_method_weights.json。"""
    records = _load_hl_predictions()
    verified = [r for r in records if r.get("verified")]
    if len(verified) < 10:
        log_tracker.info(f"HL数据不足({len(verified)}条)，跳过调优")
        return {}

    # 按regime统计误差
    regime_errors: dict[str, dict[str, list[float]]] = {}
    for r in verified:
        reg = r.get("regime", "unknown")
        if reg not in regime_errors:
            regime_errors[reg] = {"high": [], "low": []}
        regime_errors[reg]["high"].append(r["high_error_pct"])
        regime_errors[reg]["low"].append(r["low_error_pct"])

    # 加载权重文件
    weights_path = _LOG_DIR / "hl_method_weights.json"
    if weights_path.exists():
        try:
            weights = json.loads(weights_path.read_text(encoding="utf-8"))
        except Exception:
            weights = {}
    else:
        weights = {}

    # 更新regime默认权重: 误差大的regime → 调整对应方法权重
    # (简单策略: 误差>4%的regime，给volatility方法更高权重)
    methods = weights.get("methods", {})
    for reg, errs in regime_errors.items():
        avg_high = float(np.mean(errs["high"]))
        avg_low = float(np.mean(errs["low"]))
        avg_err = (avg_high + avg_low) / 2

        if avg_err > 4.0:
            # 高误差 → 降低该regime对应方法的权重(更激进: *0.7)
            for m in methods:
                methods[m]["accuracy"] = max(0.5, methods[m]["accuracy"] * 0.7)
        elif avg_err < 2.5:
            # 低误差 → 提升准确率
            for m in methods:
                methods[m]["accuracy"] = min(0.95, methods[m]["accuracy"] * 1.05)

    weights["methods"] = methods
    weights["updated_at"] = dt.datetime.now().isoformat()
    weights["hl_total_verified"] = len(verified)

    weights_path.write_text(json.dumps(weights, ensure_ascii=False, indent=2), encoding="utf-8")
    log_tracker.info(f"HL调优完成: {len(verified)}条验证数据, regimes={list(regime_errors.keys())}")
    return {"verified": len(verified), "regimes": list(regime_errors.keys())}


def _load_hl_predictions() -> list[dict]:
    """加载HL预测记录。"""
    if _HL_PREDICTIONS_FILE.exists():
        try:
            data = json.loads(_HL_PREDICTIONS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


def _save_hl_predictions(records: list[dict]) -> None:
    """保存HL预测记录。"""
    _HL_PREDICTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _HL_PREDICTIONS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_HL_PREDICTIONS_FILE)
