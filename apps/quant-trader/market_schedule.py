"""A-share / 期货交易日历与开盘收盘高频刷新窗口.

在早晚开关盘前后各 20 分钟内，建议每 20 分钟刷新一次预测数据。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal

WindowKind = Literal[
    "morning_open", "morning_close", "afternoon_open", "afternoon_close", "idle"
]

# 开盘/收盘前后各 20 分钟
REFRESH_WINDOWS: list[tuple[WindowKind, time, time]] = [
    ("morning_open", time(9, 10), time(9, 50)),       # 早盘开盘
    ("morning_close", time(11, 10), time(11, 30)),     # 早盘收盘
    ("afternoon_open", time(12, 40), time(13, 20)),    # 午盘开盘
    ("afternoon_close", time(14, 40), time(15, 20)),  # 午盘收盘
]

REFRESH_INTERVAL_MINUTES = 20


@dataclass
class MarketScheduleStatus:
    now: str
    is_trading_day: bool
    market_session_open: bool
    in_refresh_window: bool
    current_window: WindowKind
    refresh_interval_minutes: int
    seconds_until_next_refresh: int
    next_refresh_at: str
    windows: list[dict]

    def to_dict(self) -> dict:
        return {
            "now": self.now,
            "is_trading_day": self.is_trading_day,
            "market_session_open": self.market_session_open,
            "in_refresh_window": self.in_refresh_window,
            "current_window": self.current_window,
            "refresh_interval_minutes": self.refresh_interval_minutes,
            "seconds_until_next_refresh": self.seconds_until_next_refresh,
            "next_refresh_at": self.next_refresh_at,
            "windows": self.windows,
        }


def _is_weekday(d: date) -> bool:
    return d.weekday() < 5


def _in_session(t: time) -> bool:
    """常规连续交易时段 (不含集合竞价)."""
    return (time(9, 30) <= t <= time(11, 30)) or (time(13, 0) <= t <= time(15, 0))


def _window_at(t: time) -> WindowKind:
    for kind, start, end in REFRESH_WINDOWS:
        if start <= t <= end:
            return kind
    return "idle"


def _next_refresh_slot(now: datetime) -> datetime:
    """距 now 最近的下一个 20 分钟刷新点 (仅在 refresh window 内有效)."""
    interval = REFRESH_INTERVAL_MINUTES
    base = now.replace(second=0, microsecond=0)
    # 对齐到 20 分钟网格
    minute_slot = (base.minute // interval + 1) * interval
    if minute_slot >= 60:
        return base.replace(minute=0) + timedelta(hours=1)
    return base.replace(minute=minute_slot)


def market_schedule(now: datetime | None = None) -> MarketScheduleStatus:
    now = now or datetime.now()
    d, t = now.date(), now.time()
    trading_day = _is_weekday(d)
    session_open = trading_day and _in_session(t)
    window = _window_at(t) if trading_day else "idle"
    in_refresh = trading_day and window != "idle"

    if in_refresh:
        nxt = _next_refresh_slot(now)
        # 若下一格超出当前窗口，则不再自动刷新
        for kind, start, end in REFRESH_WINDOWS:
            if kind == window and nxt.time() > end:
                nxt = now + timedelta(seconds=REFRESH_INTERVAL_MINUTES * 60)
                break
        secs = max(0, int((nxt - now).total_seconds()))
        next_at = nxt.isoformat(timespec="seconds")
    else:
        secs = REFRESH_INTERVAL_MINUTES * 60
        next_at = (now + timedelta(seconds=secs)).isoformat(timespec="seconds")

    windows = [
        {
            "kind": kind,
            "label": {
                "morning_open": "早盘开盘 ±20min",
                "morning_close": "早盘收盘 ±20min",
                "afternoon_open": "午盘开盘 ±20min",
                "afternoon_close": "午盘收盘 ±20min",
            }.get(kind, kind),
            "start": start.strftime("%H:%M"),
            "end": end.strftime("%H:%M"),
            "active": trading_day and start <= t <= end,
        }
        for kind, start, end in REFRESH_WINDOWS
    ]

    return MarketScheduleStatus(
        now=now.isoformat(timespec="seconds"),
        is_trading_day=trading_day,
        market_session_open=session_open,
        in_refresh_window=in_refresh,
        current_window=window,
        refresh_interval_minutes=REFRESH_INTERVAL_MINUTES,
        seconds_until_next_refresh=secs,
        next_refresh_at=next_at,
        windows=windows,
    )
