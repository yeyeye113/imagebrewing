"""期货扫描器 — 主力合约异动筛选 + 多空提示。

扫描维度:
  1. 涨跌幅 (日→周→月)
  2. 量仓比 (成交/持仓 ← 投机度)
  3. 资金流向 (增仓涨=多头进攻, 增仓跌=空头进攻)
  4. 基差 (现货-期货, 正=反向市场, 负=正向市场)
  5. 波动率 (ATR / 历史波动率对比)
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

logger = logging.getLogger("quanttrader.futures")

# ── 扫描常亮 ──
_MIN_VOLUME = 1000  # 最低成交量（手）

# Results persistence
_RESULTS_DIR = Path(os.environ.get("QT_FUTURES_DIR", "logs"))
_RESULTS_FILE = "futures_scan.json"


@dataclass
class FuturesSignal:
    """单个品种的扫描结果。"""

    code: str
    name: str
    exchange: str
    price: float
    change_pct: float
    open_interest: int  # 持仓量
    oi_change_pct: float  # 持仓变化%
    volume: int  # 成交量
    volume_ratio: float  # 量比
    speculative_ratio: float  # 投机度(成交/持仓)
    atr: float  # 真实波幅
    vol_20d: float  # 20日波动率
    score: float  # 综合评分 0-100
    signal: str  # "long" | "short" | "neutral"
    signal_strength: str  # "strong" | "moderate" | "weak"
    reason: str
    contract_month: str  # 主力合约月份
    session: str  # 当前时段
    has_night: bool  # 有夜盘?

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "exchange": self.exchange,
            "price": self.price,
            "change_pct": round(self.change_pct, 2),
            "open_interest": self.open_interest,
            "oi_change_pct": round(self.oi_change_pct, 2),
            "volume": self.volume,
            "volume_ratio": round(self.volume_ratio, 2),
            "speculative_ratio": round(self.speculative_ratio, 2),
            "atr": round(self.atr, 2),
            "vol_20d": round(self.vol_20d, 2),
            "score": round(self.score, 1),
            "signal": self.signal,
            "signal_strength": self.signal_strength,
            "reason": self.reason,
            "contract_month": self.contract_month,
            "session": self.session,
            "has_night": self.has_night,
        }


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


class FuturesScanner:
    """扫描主力合约，输出多空信号。"""

    def __init__(self, top_n: int = 15):
        self.top_n = top_n

    def _fetch_quotes(self, codes: list[str]) -> pd.DataFrame:
        """拉取期货实时行情。先试 akshare，失败则返回空。"""
        try:
            import akshare as ak

            # akshare 期货实时行情
            df = ak.futures_zh_spot()
            if df is not None and not df.empty:
                return df
        except Exception as e:
            logger.warning(f"akshare futures spot failed: {e}")

        return pd.DataFrame()

    def _fetch_history(self, code: str, days: int = 30) -> pd.DataFrame | None:
        """拉取单个品种近日线。"""
        try:
            import akshare as ak

            sym = code.lower()
            # 判断交易所
            spec = contract_info(code)
            if not spec:
                return None
            ex = spec.exchange

            # akshare 的期货历史数据
            df = ak.futures_main_sina(symbol=sym)
            if df is not None and not df.empty:
                return df.tail(days)
        except Exception:
            pass
        return None

    def _score_signal(self, row: dict[str, Any]) -> tuple[float, str, str, str]:
        """综合评分 + 信号生成。

        Scoring: 趋势(30) + 量仓(30) + 波动率(20) + 流动性(20)
        """
        score = 0.0
        reasons: list[str] = []

        chg = float(row.get("change_pct", 0))
        oi_chg = float(row.get("oi_change_pct", 0))
        vol_ratio = float(row.get("volume_ratio", 1.0))
        spec_ratio = float(row.get("speculative_ratio", 0.5))

        # ── 趋势得分 (30分) ──
        if chg > 2.0:
            score += 30
            reasons.append("强势上涨")
        elif chg > 1.0:
            score += 22
            reasons.append("温和上涨")
        elif chg < -2.0:
            score += 30
            reasons.append("强势下跌")
        elif chg < -1.0:
            score += 22
            reasons.append("温和下跌")
        else:
            score += 10
            reasons.append("震荡")

        # ── 量仓配合得分 (30分) ──
        # 增仓+上涨 = 多头进攻；增仓+下跌 = 空头进攻
        if oi_chg > 3 and chg > 1:
            score += 30
            reasons.append("增仓上涨(多头进攻)")
        elif oi_chg > 3 and chg < -1:
            score += 30
            reasons.append("增仓下跌(空头进攻)")
        elif oi_chg < -3:
            score += 5
            reasons.append("减仓(资金离场)")
        else:
            score += 15

        # ── 波动率得分 (20分) ──
        atr = float(row.get("atr", 0))
        price = float(row.get("price", 1))
        atr_pct = atr / price * 100 if price > 0 else 0
        if 1.0 < atr_pct < 4.0:
            score += 20
            reasons.append("波动适中")
        elif atr_pct >= 4.0:
            score += 10
            reasons.append("高波动(注意风险)")
        else:
            score += 15

        # ── 流动性得分 (20分) ──
        high_liq = spec_ratio > 0.8 and vol_ratio > 0.7
        if spec_ratio > 1.5:
            score += 20
            reasons.append("高投机度")
        elif high_liq:
            score += 15
            reasons.append("流动性好")
        else:
            score += 8

        # ── 信号判定 ──
        signal = "neutral"
        strength = "weak"

        if chg > 1.5 and oi_chg > 0:
            signal = "long"
            strength = "strong" if chg > 3 and oi_chg > 5 else "moderate"
        elif chg > 0.5 and vol_ratio > 1.2:
            signal = "long"
            strength = "weak"
        elif chg < -1.5 and oi_chg > 0:
            signal = "short"
            strength = "strong" if chg < -3 and oi_chg > 5 else "moderate"
        elif chg < -0.5 and vol_ratio > 1.2:
            signal = "short"
            strength = "weak"

        return max(0, min(100, score)), signal, strength, " | ".join(reasons) if reasons else "无信号"

    def scan(self) -> FuturesScanReport:
        """扫描主力合约，返回排序后的信号清单。"""
        logger.info("🔍 扫描期货主力合约...")

        raw = self._fetch_quotes(DOMINANT_CONTRACTS)
        if raw.empty:
            logger.warning("未获取到期货行情数据，返回空报告")
            return FuturesScanReport(
                timestamp=dt.datetime.now().isoformat(timespec="seconds"),
                signals=[],
                stats={"error": "无法获取期货实时行情"},
            )

        signals: list[FuturesSignal] = []
        session = session_label()

        for code in DOMINANT_CONTRACTS:
            spec = contract_info(code)
            if not spec:
                continue

            # Try to match in real-time data
            row_data: dict[str, Any] = {}
            try:
                # 查找该品种主力合约的数据行
                matches = (
                    raw[raw["symbol"].str.upper().str.startswith(code.upper())]
                    if "symbol" in raw.columns
                    else pd.DataFrame()
                )
                if matches.empty:
                    continue

                latest = matches.iloc[0]
                price = float(latest.get("trade", latest.get("price", 0)))
                if price <= 0:
                    continue

                chg_pct = float(latest.get("changepercent", latest.get("change_pct", 0)))
                oi = int(latest.get("open_interest", latest.get("position", 0)))
                oi_chg_pct = float(latest.get("oi_change_pct", 0))
                vol = int(latest.get("volume", 0))
                if vol < _MIN_VOLUME:
                    continue

                # Compute derived metrics
                vol_ratio = float(latest.get("volume_ratio", 1.0))
                spec_ratio = vol / oi if oi > 0 else 0.5
                atr = abs(chg_pct * price / 100) if chg_pct != 0 else price * 0.01
                vol_20d = abs(chg_pct) * 1.5  # rough estimate

                row_data = {
                    "code": code,
                    "name": spec.name,
                    "exchange": spec.exchange,
                    "price": price,
                    "change_pct": chg_pct,
                    "open_interest": oi,
                    "oi_change_pct": oi_chg_pct,
                    "volume": vol,
                    "volume_ratio": vol_ratio,
                    "speculative_ratio": spec_ratio,
                    "atr": atr,
                    "vol_20d": vol_20d,
                }
            except Exception:
                continue

            score, signal, strength, reason = self._score_signal(row_data)

            hours = MARKET_HOURS.get(code)
            has_night = hours.night_open is not None if hours else False

            signals.append(
                FuturesSignal(
                    code=code,
                    name=spec.name,
                    exchange=spec.exchange,
                    price=row_data["price"],
                    change_pct=row_data["change_pct"],
                    open_interest=row_data["open_interest"],
                    oi_change_pct=row_data["oi_change_pct"],
                    volume=row_data["volume"],
                    volume_ratio=row_data["volume_ratio"],
                    speculative_ratio=row_data["speculative_ratio"],
                    atr=row_data["atr"],
                    vol_20d=row_data["vol_20d"],
                    score=score,
                    signal=signal,
                    signal_strength=strength,
                    reason=reason,
                    contract_month=dominant_contract(code),
                    session=session,
                    has_night=has_night,
                )
            )

        # Sort by score, then by abs(change)
        signals.sort(key=lambda s: (s.score, abs(s.change_pct)), reverse=True)
        top = signals[: self.top_n]

        long_n = sum(1 for s in top if s.signal == "long")
        short_n = sum(1 for s in top if s.signal == "short")
        neutral_n = sum(1 for s in top if s.signal == "neutral")

        stats = {
            "total_scanned": len(signals),
            "candidates": len(top),
            "avg_score": round(sum(s.score for s in top) / max(len(top), 1), 1),
            "long_signals": long_n,
            "short_signals": short_n,
            "neutral_signals": neutral_n,
            "session": session,
            "is_trading": is_trading_now(),
        }

        report = FuturesScanReport(
            timestamp=dt.datetime.now().isoformat(timespec="seconds"),
            signals=top,
            stats=stats,
        )

        # Persist
        try:
            _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
            (_RESULTS_DIR / _RESULTS_FILE).write_text(
                json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

        logger.info(f"期货扫描完成: {len(top)} 信号 (多{long_n} 空{short_n} 中性{neutral_n})")
        return report


def scan_futures(top_n: int = 15) -> FuturesScanReport:
    """快捷扫描函数。"""
    return FuturesScanner(top_n=top_n).scan()
