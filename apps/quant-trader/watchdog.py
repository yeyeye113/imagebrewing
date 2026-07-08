"""盯盘异动检测引擎 — watchdog anomaly detection.

检测规则（可配置阈值）:
  1. 价格异动: 涨跌幅超过阈值 (默认 ±3%)
  2. 量能爆发: 成交量大于是前 5 日均量的 N 倍 (默认 2x)
  3. 均线突破: 价格穿越 SMA10/SMA20/SMA60
  4. 连续大单: N 根 K 线内持续同向 (>3 根)
  5. 跳空缺口: 开盘价与前收盘价差距超过阈值
  6. 波动率突增: 当前 ATR 超过 20 日均值的 N 倍

每个事件即时分派: 轻量(仅通知) / 中度(调 LLM 研判) / 严重(自动风控)
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

# ══════════════════════════════════════════════════════════════════
# 事件定义
# ══════════════════════════════════════════════════════════════════


class AlertLevel:
    INFO = "info"  # 仅记录
    WATCH = "watch"  # 关注，推送通知
    WARN = "warn"  # 警告，调 LLM 研判
    ACTION = "action"  # 行动级，建议立即操作


@dataclass
class WatchEvent:
    """单条异动事件。"""

    timestamp: str
    symbol: str
    event_type: str  # price_surge / price_plunge / volume_spike / ma_breakout / gap / vol_surge
    level: str  # info / watch / warn / action
    title: str  # 一行摘要
    detail: str  # 数据详情
    price: float
    change_pct: float
    suggestion: str = ""  # LLM 研判后的建议（异步填充）


# ══════════════════════════════════════════════════════════════════
# 检测规则配置
# ══════════════════════════════════════════════════════════════════


@dataclass
class WatchConfig:
    """异动检测阈值配置。"""

    # 价格异动
    price_surge_pct: float = 3.0  # 涨超 N% 触发
    price_plunge_pct: float = -3.0  # 跌超 N% 触发
    price_intra_surge_pct: float = 1.5  # 盘中快速拉升 (5分钟内)
    price_intra_plunge_pct: float = -1.5

    # 量能
    volume_spike_ratio: float = 2.0  # 量比 > N
    volume_dry_ratio: float = 0.3  # 量比 < N (缩量)

    # 均线
    ma_periods: tuple = (10, 20, 60)  # 检测均线穿越
    ma_breakout_confirm: int = 2  # 连续 N 根确认

    # 连续K线
    consecutive_bars: int = 3  # 连续 N 根同向
    consecutive_min_chg: float = 0.5  # 每根最小涨跌%

    # 跳空
    gap_pct: float = 2.0  # 开盘跳空 > N%

    # 波动率
    vol_regime_threshold: float = 2.0  # ATR > 20日均值 * N

    # 冷却: 同一品种同一类型事件 N 秒内不重复
    cooldown_seconds: int = 300


class Watchdog:
    """异动检测引擎 — 接收 OHLCV 数据流，产出 WatchEvent 事件流。"""

    def __init__(
        self,
        config: WatchConfig | None = None,
        on_event: Callable[[WatchEvent], None] | None = None,
        on_action: Callable[[WatchEvent], None] | None = None,
    ):
        self.cfg = config or WatchConfig()
        self.on_event = on_event  # 所有事件回调
        self.on_action = on_action  # ACTION 级事件专用回调
        self._last_alert: dict[str, float] = {}  # symbol:type → last_ts
        self.events: list[WatchEvent] = []

    # ── 冷却检查 ──

    def _cooled(self, symbol: str, etype: str) -> bool:
        key = f"{symbol}:{etype}"
        now = dt.datetime.now().timestamp()
        last = self._last_alert.get(key, 0)
        if now - last < self.cfg.cooldown_seconds:
            return True
        self._last_alert[key] = now
        return False

    # ── 价格异动 ──

    def _check_price(self, symbol: str, prices: pd.DataFrame) -> list[WatchEvent]:
        events: list[WatchEvent] = []
        closes = prices["close"].astype(float)
        if len(closes) < 2:
            return events

        now = dt.datetime.now().isoformat(timespec="seconds")
        price = float(closes.iloc[-1])
        prev = float(closes.iloc[-2])
        chg = (price / prev - 1) * 100

        # 单根涨跌
        if chg >= self.cfg.price_surge_pct:
            if not self._cooled(symbol, "price_surge"):
                events.append(
                    WatchEvent(
                        timestamp=now,
                        symbol=symbol,
                        event_type="price_surge",
                        level=AlertLevel.WARN if chg >= 5 else AlertLevel.WATCH,
                        title=f"🚀 {symbol} 急涨 {chg:+.1f}%",
                        detail=f"价格 {prev:.2f} → {price:.2f} 单根涨幅 {chg:+.1f}%",
                        price=price,
                        change_pct=chg,
                    )
                )
        elif chg <= self.cfg.price_plunge_pct:
            if not self._cooled(symbol, "price_plunge"):
                events.append(
                    WatchEvent(
                        timestamp=now,
                        symbol=symbol,
                        event_type="price_plunge",
                        level=AlertLevel.WARN if chg <= -5 else AlertLevel.WATCH,
                        title=f"🔻 {symbol} 急跌 {chg:+.1f}%",
                        detail=f"价格 {prev:.2f} → {price:.2f} 单根跌幅 {chg:+.1f}%",
                        price=price,
                        change_pct=chg,
                    )
                )

        # 连续同向 K 线
        if len(closes) >= self.cfg.consecutive_bars:
            recent = closes.iloc[-self.cfg.consecutive_bars :]
            all_up = all(
                (recent.iloc[i] / recent.iloc[i - 1] - 1) * 100 >= self.cfg.consecutive_min_chg
                for i in range(1, len(recent))
            )
            all_down = all(
                (recent.iloc[i] / recent.iloc[i - 1] - 1) * 100 <= -self.cfg.consecutive_min_chg
                for i in range(1, len(recent))
            )
            if all_up and not self._cooled(symbol, "consec_up"):
                total = (closes.iloc[-1] / closes.iloc[-self.cfg.consecutive_bars] - 1) * 100
                events.append(
                    WatchEvent(
                        timestamp=now,
                        symbol=symbol,
                        event_type="consecutive_up",
                        level=AlertLevel.WARN if total > 5 else AlertLevel.WATCH,
                        title=f"📈 {symbol} 连续 {self.cfg.consecutive_bars} 阳",
                        detail=f"累计涨幅 {total:+.1f}%",
                        price=price,
                        change_pct=total,
                    )
                )
            if all_down and not self._cooled(symbol, "consec_down"):
                total = (closes.iloc[-1] / closes.iloc[-self.cfg.consecutive_bars] - 1) * 100
                events.append(
                    WatchEvent(
                        timestamp=now,
                        symbol=symbol,
                        event_type="consecutive_down",
                        level=AlertLevel.WARN if total < -5 else AlertLevel.WATCH,
                        title=f"📉 {symbol} 连续 {self.cfg.consecutive_bars} 阴",
                        detail=f"累计跌幅 {total:+.1f}%",
                        price=price,
                        change_pct=total,
                    )
                )

        return events

    # ── 量能异动 ──

    def _check_volume(self, symbol: str, prices: pd.DataFrame) -> list[WatchEvent]:
        events: list[WatchEvent] = []
        if "volume" not in prices.columns:
            return events

        vols = prices["volume"].astype(float)
        if len(vols) < 6:
            return events

        now = dt.datetime.now().isoformat(timespec="seconds")
        price = float(prices["close"].iloc[-1])
        chg = float((prices["close"].iloc[-1] / prices["close"].iloc[-2] - 1) * 100)

        today_vol = float(vols.iloc[-1])
        avg_vol_5 = float(vols.iloc[-6:-1].mean())
        avg_vol_20 = float(vols.tail(20).mean()) if len(vols) >= 20 else avg_vol_5
        ratio_5 = today_vol / avg_vol_5 if avg_vol_5 > 0 else 1.0
        ratio_20 = today_vol / avg_vol_20 if avg_vol_20 > 0 else 1.0

        # 放量
        if ratio_5 >= self.cfg.volume_spike_ratio:
            if not self._cooled(symbol, "volume_spike"):
                direction = "放量涨" if chg > 0 else "放量跌"
                events.append(
                    WatchEvent(
                        timestamp=now,
                        symbol=symbol,
                        event_type="volume_spike",
                        level=AlertLevel.WARN if ratio_5 >= 3 else AlertLevel.WATCH,
                        title=f"📊 {symbol} {direction} 量比 {ratio_5:.1f}x",
                        detail=f"今日量 {today_vol:.0f} vs 5日均 {avg_vol_5:.0f} ({ratio_5:.1f}x) "
                        f"| 20日均 {avg_vol_20:.0f} ({ratio_20:.1f}x) | {direction}",
                        price=price,
                        change_pct=chg,
                    )
                )

        # 缩量（可能变盘）
        if ratio_20 <= self.cfg.volume_dry_ratio and today_vol > 0:
            if not self._cooled(symbol, "volume_dry"):
                events.append(
                    WatchEvent(
                        timestamp=now,
                        symbol=symbol,
                        event_type="volume_dry",
                        level=AlertLevel.INFO,
                        title=f"📉 {symbol} 缩量 量比 {ratio_20:.1f}x",
                        detail=f"今日量 {today_vol:.0f} 仅为 20 日均的 {ratio_20 * 100:.0f}%，注意变盘",
                        price=price,
                        change_pct=chg,
                    )
                )

        return events

    # ── 均线突破 ──

    def _check_ma_breakout(self, symbol: str, prices: pd.DataFrame) -> list[WatchEvent]:
        events: list[WatchEvent] = []
        closes = prices["close"].astype(float)
        if len(closes) < max(self.cfg.ma_periods) + self.cfg.ma_breakout_confirm:
            return events

        now = dt.datetime.now().isoformat(timespec="seconds")
        price = float(closes.iloc[-1])
        chg = float((closes.iloc[-1] / closes.iloc[-2] - 1) * 100)

        for period in self.cfg.ma_periods:
            if len(closes) < period + 2:
                continue
            sma = float(closes.tail(period).mean())
            prev_sma = float(closes.iloc[-period - 1 : -1].mean())

            # 上穿
            if price > sma and closes.iloc[-2] <= prev_sma:
                if not self._cooled(symbol, f"ma{period}_up"):
                    events.append(
                        WatchEvent(
                            timestamp=now,
                            symbol=symbol,
                            event_type=f"ma{period}_breakout_up",
                            level=AlertLevel.WATCH,
                            title=f"⬆️ {symbol} 突破 SMA{period} ({sma:.2f})",
                            detail=f"价格 {price:.2f} 上穿 SMA{period}({sma:.2f}) | "
                            f"距均线 {((price / sma - 1) * 100):+.1f}%",
                            price=price,
                            change_pct=chg,
                        )
                    )
            # 下穿
            elif price < sma and closes.iloc[-2] >= prev_sma:
                if not self._cooled(symbol, f"ma{period}_down"):
                    events.append(
                        WatchEvent(
                            timestamp=now,
                            symbol=symbol,
                            event_type=f"ma{period}_breakout_down",
                            level=AlertLevel.WATCH,
                            title=f"⬇️ {symbol} 跌破 SMA{period} ({sma:.2f})",
                            detail=f"价格 {price:.2f} 下穿 SMA{period}({sma:.2f}) | "
                            f"距均线 {((price / sma - 1) * 100):+.1f}%",
                            price=price,
                            change_pct=chg,
                        )
                    )

        return events

    # ── 跳空缺口 ──

    def _check_gap(self, symbol: str, prices: pd.DataFrame) -> list[WatchEvent]:
        events: list[WatchEvent] = []
        if "open" not in prices.columns or len(prices) < 2:
            return events

        now = dt.datetime.now().isoformat(timespec="seconds")
        today_open = float(prices["open"].iloc[-1])
        yesterday_close = float(prices["close"].iloc[-2])
        if yesterday_close <= 0:
            return events

        gap = (today_open / yesterday_close - 1) * 100
        price = float(prices["close"].iloc[-1])

        if abs(gap) >= self.cfg.gap_pct:
            gap_type = "向上跳空" if gap > 0 else "向下跳空"
            if not self._cooled(symbol, "gap"):
                events.append(
                    WatchEvent(
                        timestamp=now,
                        symbol=symbol,
                        event_type="gap",
                        level=AlertLevel.WARN if abs(gap) > 4 else AlertLevel.WATCH,
                        title=f"⚡ {symbol} {gap_type} {gap:+.1f}%",
                        detail=f"昨收 {yesterday_close:.2f} → 今开 {today_open:.2f} ({gap:+.1f}%)",
                        price=price,
                        change_pct=gap,
                    )
                )

        return events

    # ── 波动率突变 ──

    def _check_volatility(self, symbol: str, prices: pd.DataFrame) -> list[WatchEvent]:
        events: list[WatchEvent] = []
        closes = prices["close"].astype(float)
        highs = prices["high"].astype(float) if "high" in prices.columns else closes
        lows = prices["low"].astype(float) if "low" in prices.columns else closes

        if len(closes) < 22:
            return events

        now = dt.datetime.now().isoformat(timespec="seconds")
        price = float(closes.iloc[-1])

        # ATR simple
        trs = []
        for i in range(1, min(22, len(closes))):
            h = float(highs.iloc[-i])
            l = float(lows.iloc[-i])
            pc = float(closes.iloc[-i - 1])
            tr = max(h - l, abs(h - pc), abs(l - pc))
            trs.append(tr)
        if not trs:
            return events

        atr_now = float(np.mean(trs[:5])) if len(trs) >= 5 else trs[0]
        atr_20 = float(np.mean(trs)) if len(trs) >= 20 else atr_now
        atr_ratio = atr_now / atr_20 if atr_20 > 0 else 1.0

        if atr_ratio >= self.cfg.vol_regime_threshold:
            if not self._cooled(symbol, "vol_surge"):
                events.append(
                    WatchEvent(
                        timestamp=now,
                        symbol=symbol,
                        event_type="volatility_surge",
                        level=AlertLevel.WARN,
                        title=f"🌊 {symbol} 波动率激增 {atr_ratio:.1f}x",
                        detail=f"5日 ATR {atr_now:.2f} vs 20日 ATR {atr_20:.2f} ({atr_ratio:.1f}x) | "
                        f"当前波动率 {atr_now / price * 100:.1f}%",
                        price=price,
                        change_pct=atr_now / price * 100,
                    )
                )

        return events

    # ── 总检测入口 ──

    def scan(self, symbol: str, prices: pd.DataFrame) -> list[WatchEvent]:
        """扫描一个标的的 OHLCV 数据，返回所有异动事件。"""
        if prices.empty or len(prices) < 2:
            return []

        all_events: list[WatchEvent] = []
        all_events.extend(self._check_price(symbol, prices))
        all_events.extend(self._check_volume(symbol, prices))
        all_events.extend(self._check_ma_breakout(symbol, prices))
        all_events.extend(self._check_gap(symbol, prices))
        all_events.extend(self._check_volatility(symbol, prices))

        # Sort by severity: action > warn > watch > info
        level_order = {AlertLevel.ACTION: 0, AlertLevel.WARN: 1, AlertLevel.WATCH: 2, AlertLevel.INFO: 3}
        all_events.sort(key=lambda e: (level_order.get(e.level, 99), -abs(e.change_pct)))

        self.events.extend(all_events)
        self.events = self.events[-200:]  # keep last 200

        # Callback
        for e in all_events:
            if self.on_event:
                self.on_event(e)
            if e.level == AlertLevel.ACTION and self.on_action:
                self.on_action(e)

        return all_events

    def scan_multi(self, data: dict[str, pd.DataFrame]) -> list[WatchEvent]:
        """扫描多个标的。"""
        all_events: list[WatchEvent] = []
        for symbol, prices in data.items():
            all_events.extend(self.scan(symbol, prices))
        return sorted(all_events, key=lambda e: -abs(e.change_pct))

    def summary(self) -> str:
        """生成最近事件的文本摘要。"""
        recent = self.events[-20:]
        if not recent:
            return "👁️ 盯盘中...暂无异动"

        warns = [e for e in recent if e.level in (AlertLevel.WARN, AlertLevel.ACTION)]
        lines = [f"👁️ 最近异动 ({len(recent)} 条)"]
        for e in recent[-8:]:
            icon = {"info": "ℹ️", "watch": "👀", "warn": "⚠️", "action": "🚨"}.get(e.level, "•")
            lines.append(f"  {icon} {e.title}")
        if warns:
            lines.append(f"\n⚠️ {len(warns)} 条需关注")
        return "\n".join(lines)

    def to_dict_list(self) -> list[dict[str, Any]]:
        return [
            {
                "ts": e.timestamp,
                "symbol": e.symbol,
                "type": e.event_type,
                "level": e.level,
                "title": e.title,
                "detail": e.detail,
                "price": e.price,
                "change_pct": round(e.change_pct, 2),
                "suggestion": e.suggestion,
            }
            for e in self.events[-50:]
        ]


# ══════════════════════════════════════════════════════════════════
# 便捷函数
# ══════════════════════════════════════════════════════════════════

_default_watchdog: Watchdog | None = None


def get_watchdog(config: WatchConfig | None = None) -> Watchdog:
    global _default_watchdog
    if _default_watchdog is None:
        _default_watchdog = Watchdog(config=config)
    return _default_watchdog


def scan_symbol(symbol: str, prices: pd.DataFrame) -> list[WatchEvent]:
    return get_watchdog().scan(symbol, prices)
