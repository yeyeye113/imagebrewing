"""修复版期货扫描器 — 用 Sina 主力合约接口替代 akshare spot。

akshare 1.18 futures_zh_spot() 有 pandas 列不匹配bug。
改用 futures_main_sina() 逐个获取主力合约数据，兼容中文列名。
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from .contracts import (
    DOMINANT_CONTRACTS,
    MARKET_HOURS,
    contract_info,
    dominant_contract,
    is_trading_now,
    session_label,
)
from .scanner import FuturesSignal

logger = logging.getLogger("quanttrader.futures")

_MIN_VOLUME = 1000

_RESULTS_DIR = Path(os.environ.get("QT_FUTURES_DIR", "logs"))
_RESULTS_FILE = "futures_scan.json"


# akshare 中文列名映射
_CN_COL_MAP = {
    "日期": "date",
    "开盘价": "open",
    "最高价": "high",
    "最低价": "low",
    "收盘价": "close",
    "成交量": "volume",
    "持仓量": "open_interest",
    "动态结算": "settle",
}


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """规范化 akshare 中文列名为英文。"""
    # rename 会自动忽略不存在的键，无需逐列判断存在性
    return df.rename(columns=_CN_COL_MAP)


# FuturesSignal 复用 scanner.py 的定义 (顶部 import, 字段完全一致, 消除重复维护);
# `from .scanner_v2 import FuturesSignal` 的既有用法仍然成立。


@dataclass
class FuturesScanReport:
    timestamp: str
    signals: list[FuturesSignal]
    stats: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "stats": self.stats,
            "signals": [s.to_dict() for s in self.signals],
        }


def _fetch_single(code: str) -> pd.DataFrame | None:
    """拉取单个品种主力合约日线。"""
    try:
        import akshare as ak

        sym = f"{code.upper()}0"  # RB → RB0 for main contract
        df = ak.futures_main_sina(symbol=sym)
        if df is None or df.empty:
            return None
        return _normalize_df(df)
    except Exception as e:
        logger.debug(f"{code}: fetch failed ({e})")
        return None


def _score_signal(
    price: float, chg_pct: float, oi_chg_pct: float, vol_ratio: float, spec_ratio: float, atr: float
) -> tuple[float, str, str, str]:
    """评分 + 信号。"""
    score = 0.0
    reasons: list[str] = []

    # 趋势 (30)
    if chg_pct > 2.0:
        score += 30
        reasons.append("强势上涨")
    elif chg_pct > 1.0:
        score += 22
        reasons.append("温和上涨")
    elif chg_pct < -2.0:
        score += 30
        reasons.append("强势下跌")
    elif chg_pct < -1.0:
        score += 22
        reasons.append("温和下跌")
    else:
        score += 10
        reasons.append("震荡")

    # 量仓 (30)
    if oi_chg_pct > 3 and chg_pct > 1:
        score += 30
        reasons.append("增仓上涨(多头进攻)")
    elif oi_chg_pct > 3 and chg_pct < -1:
        score += 30
        reasons.append("增仓下跌(空头进攻)")
    elif oi_chg_pct < -3:
        score += 5
        reasons.append("减仓(资金离场)")
    else:
        score += 15

    # 波动率 (20)
    atr_pct = atr / price * 100 if price > 0 else 0
    if 1.0 < atr_pct < 4.0:
        score += 20
        reasons.append("波动适中")
    elif atr_pct >= 4.0:
        score += 10
        reasons.append("高波动")
    else:
        score += 15

    # 流动性 (20)
    if spec_ratio > 1.5:
        score += 20
        reasons.append("高投机度")
    elif spec_ratio > 0.8 and vol_ratio > 0.7:
        score += 15
        reasons.append("流动性好")
    else:
        score += 8

    signal = "neutral"
    strength = "weak"
    if chg_pct > 1.5 and oi_chg_pct > 0:
        signal = "long"
        strength = "strong" if chg_pct > 3 and oi_chg_pct > 5 else "moderate"
    elif chg_pct > 0.5 and vol_ratio > 1.2:
        signal = "long"
        strength = "weak"
    elif chg_pct < -1.5 and oi_chg_pct > 0:
        signal = "short"
        strength = "strong" if chg_pct < -3 and oi_chg_pct > 5 else "moderate"
    elif chg_pct < -0.5 and vol_ratio > 1.2:
        signal = "short"
        strength = "weak"

    return max(0, min(100, score)), signal, strength, " | ".join(reasons) if reasons else "无信号"


def scan_futures(top_n: int = 12) -> FuturesScanReport:
    """逐个拉取主力合约数据并评分。默认只扫前15个活跃品种。"""
    logger.info("Scanning futures main contracts (Sina individual)...")

    signals: list[FuturesSignal] = []
    session = session_label()

    # 只扫前15个最活跃品种，避免超时
    scan_codes = DOMINANT_CONTRACTS[:15]

    for code in scan_codes:
        spec = contract_info(code)
        if not spec:
            continue

        try:
            df = _fetch_single(code)
        except Exception:
            continue

        if df is None or len(df) < 5:
            continue

        try:
            # 从标准化后的DataFrame提取数据
            closes = df["close"].astype(float)
            volumes = df["volume"].astype(float) if "volume" in df.columns else pd.Series(0, index=closes.index)
            oi_col = "open_interest" if "open_interest" in df.columns else None

            price = float(closes.iloc[-1])
            prev = float(closes.iloc[-2]) if len(closes) >= 2 else price
            chg_pct = (price / prev - 1) * 100

            # 成交量
            today_vol = int(volumes.iloc[-1]) if len(volumes) > 0 else 0
            avg_vol_5 = float(volumes.tail(6).iloc[:-1].mean()) if len(volumes) >= 6 else today_vol
            vol_ratio = today_vol / avg_vol_5 if avg_vol_5 > 0 else 1.0

            # 持仓
            oi = 0
            oi_chg_pct = 0.0
            if oi_col:
                oi = int(df[oi_col].iloc[-1])
                prev_oi = int(df[oi_col].iloc[-2]) if len(df) >= 2 else oi
                oi_chg_pct = (oi / prev_oi - 1) * 100 if prev_oi > 0 else 0.0

            # ATR
            highs = df["high"].astype(float) if "high" in df.columns else closes
            lows = df["low"].astype(float) if "low" in df.columns else closes
            trs = []
            for i in range(1, min(22, len(closes))):
                h, l, pc = float(highs.iloc[-i]), float(lows.iloc[-i]), float(closes.iloc[-i - 1])
                trs.append(max(h - l, abs(h - pc), abs(l - pc)))
            atr = float(sum(trs[:5]) / 5) if len(trs) >= 5 else abs(chg_pct * price / 100)

            spec_ratio = today_vol / oi if oi > 0 else 0.5
            vol_20d = float(closes.pct_change().tail(20).std() * 100) if len(closes) >= 20 else abs(chg_pct) * 1.5
        except Exception as e:
            logger.debug(f"{code}: parse error ({e})")
            continue

        score, signal, strength, reason = _score_signal(price, chg_pct, oi_chg_pct, vol_ratio, spec_ratio, atr)

        hours = MARKET_HOURS.get(code)
        has_night = hours.night_open is not None if hours else False

        signals.append(
            FuturesSignal(
                code=code,
                name=spec.name,
                exchange=spec.exchange,
                price=price,
                change_pct=chg_pct,
                open_interest=oi,
                oi_change_pct=round(oi_chg_pct, 2),
                volume=today_vol,
                volume_ratio=round(vol_ratio, 2),
                speculative_ratio=round(spec_ratio, 2),
                atr=round(atr, 2),
                vol_20d=round(vol_20d, 2),
                score=score,
                signal=signal,
                signal_strength=strength,
                reason=reason,
                contract_month=dominant_contract(code),
                session=session,
                has_night=has_night,
            )
        )

    signals.sort(key=lambda s: (s.score, abs(s.change_pct)), reverse=True)
    top = signals[:top_n]

    long_n = sum(1 for s in top if s.signal == "long")
    short_n = sum(1 for s in top if s.signal == "short")

    stats = {
        "total_scanned": len(signals),
        "candidates": len(top),
        "avg_score": round(sum(s.score for s in top) / max(len(top), 1), 1),
        "long_signals": long_n,
        "short_signals": short_n,
        "neutral_signals": len(top) - long_n - short_n,
        "session": session,
        "is_trading": is_trading_now(),
    }

    report = FuturesScanReport(
        timestamp=dt.datetime.now().isoformat(timespec="seconds"),
        signals=top,
        stats=stats,
    )

    try:
        _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        (_RESULTS_DIR / _RESULTS_FILE).write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass

    logger.info(f"Futures scan: {len(top)} signals (long={long_n} short={short_n})")
    return report
