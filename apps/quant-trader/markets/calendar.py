"""Trading calendar and market-hours utilities.

Handles:
- Per-market timezone conversion (UTC <-> local)
- Trading session windows (pre-market, regular, after-hours)
- Holiday detection for CN / HK / US markets
- is_trading_day() / is_market_open() helpers
"""

from __future__ import annotations

import datetime as _dt
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Timezone helpers
# ---------------------------------------------------------------------------


def _ensure_tzinfo() -> None:
    """Verify zoneinfo is available (stdlib 3.9+)."""
    try:
        from zoneinfo import ZoneInfo  # noqa: F401 — guard import
    except ImportError:
        raise ImportError("zoneinfo is required. On Python <3.9 install `tzdata` and `backports.zoneinfo`.")


def utc_now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


def to_utc(local_dt: _dt.datetime, tz_name: str) -> _dt.datetime:
    """Convert a naive or aware datetime in *tz_name* to UTC."""
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(tz_name)
    if local_dt.tzinfo is None:
        local_dt = local_dt.replace(tzinfo=tz)
    return local_dt.astimezone(_dt.UTC)


def to_local(utc_dt: _dt.datetime, tz_name: str) -> _dt.datetime:
    """Convert a UTC datetime to local time in *tz_name*."""
    from zoneinfo import ZoneInfo

    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=_dt.UTC)
    return utc_dt.astimezone(ZoneInfo(tz_name))


# ---------------------------------------------------------------------------
# Trading session window
# ---------------------------------------------------------------------------


class Session(NamedTuple):
    open_hour: int
    open_minute: int
    close_hour: int
    close_minute: int
    pre_open_hour: int = 0
    pre_open_minute: int = 0
    post_close_hour: int = 0
    post_close_minute: int = 0


# ---------------------------------------------------------------------------
# Static holiday tables (YYYY-MM-DD).  Updated yearly.
# ---------------------------------------------------------------------------

_CN_HOLIDAYS_2025 = {
    "2025-01-01",
    "2025-01-28",
    "2025-01-29",
    "2025-01-30",
    "2025-01-31",
    "2025-02-01",
    "2025-02-02",
    "2025-02-03",
    "2025-02-04",
    "2025-04-04",
    "2025-04-05",
    "2025-04-06",
    "2025-05-01",
    "2025-05-02",
    "2025-05-03",
    "2025-05-04",
    "2025-05-05",
    "2025-06-02",
    "2025-10-01",
    "2025-10-02",
    "2025-10-03",
    "2025-10-04",
    "2025-10-05",
    "2025-10-06",
    "2025-10-07",
}
_CN_HOLIDAYS_2026 = {
    "2026-01-01",
    "2026-01-02",
    "2026-01-03",
    "2026-02-16",
    "2026-02-17",
    "2026-02-18",
    "2026-02-19",
    "2026-02-20",
    "2026-04-04",
    "2026-04-05",
    "2026-04-06",
    "2026-05-01",
    "2026-05-02",
    "2026-05-03",
    "2026-06-19",
    "2026-10-01",
    "2026-10-02",
    "2026-10-03",
    "2026-10-04",
    "2026-10-05",
    "2026-10-06",
    "2026-10-07",
}
_CN_HOLIDAYS: set[str] = _CN_HOLIDAYS_2025 | _CN_HOLIDAYS_2026

_HK_HOLIDAYS_2025 = {
    "2025-01-01",
    "2025-01-29",
    "2025-01-30",
    "2025-01-31",
    "2025-04-04",
    "2025-04-18",
    "2025-04-19",
    "2025-04-21",
    "2025-05-01",
    "2025-05-05",
    "2025-06-02",
    "2025-10-01",
    "2025-10-07",
    "2025-10-29",
    "2025-12-25",
    "2025-12-26",
}
_HK_HOLIDAYS_2026 = {
    "2026-01-01",
    "2026-01-02",
    "2026-02-17",
    "2026-02-18",
    "2026-02-19",
    "2026-02-20",
    "2026-04-03",
    "2026-04-06",
    "2026-04-07",
    "2026-05-01",
    "2026-06-19",
    "2026-10-01",
    "2026-10-07",
    "2026-12-25",
    "2026-12-28",
}
_HK_HOLIDAYS: set[str] = _HK_HOLIDAYS_2025 | _HK_HOLIDAYS_2026

_US_HOLIDAYS_2025 = {
    "2025-01-01",
    "2025-01-20",
    "2025-02-17",
    "2025-04-18",
    "2025-05-26",
    "2025-06-19",
    "2025-07-04",
    "2025-09-01",
    "2025-11-27",
    "2025-12-25",
}
_US_HOLIDAYS_2026 = {
    "2026-01-01",
    "2026-01-19",
    "2026-02-16",
    "2026-04-03",
    "2026-05-25",
    "2026-06-19",
    "2026-07-03",
    "2026-09-07",
    "2026-11-26",
    "2026-12-25",
}
_US_HOLIDAYS: set[str] = _US_HOLIDAYS_2025 | _US_HOLIDAYS_2026


# ---------------------------------------------------------------------------
# Calendar class
# ---------------------------------------------------------------------------


class TradingCalendar:
    """Per-market trading calendar with timezone and holiday awareness."""

    def __init__(
        self,
        tz_name: str,
        holidays: set[str],
        session: Session,
    ):
        self.tz_name = tz_name
        self._holidays = holidays
        self.session = session

    # ---- public API ----

    @property
    def timezone(self):
        from zoneinfo import ZoneInfo

        return ZoneInfo(self.tz_name)

    def is_holiday(self, d: _dt.date | None = None) -> bool:
        d = d or _dt.date.today()
        return d.isoformat() in self._holidays

    def is_trading_day(self, d: _dt.date | None = None) -> bool:
        d = d or _dt.date.today()
        if d.weekday() >= 5:  # Saturday=5, Sunday=6
            return False
        return not self.is_holiday(d)

    def is_market_open(self, dt_utc: _dt.datetime | None = None) -> bool:
        """Check if the market is currently open (regular session)."""
        if dt_utc is None:
            dt_utc = utc_now()
        local = to_local(dt_utc, self.tz_name)
        if not self.is_trading_day(local.date()):
            return False
        t = local.time()
        open_t = _dt.time(self.session.open_hour, self.session.open_minute)
        close_t = _dt.time(self.session.close_hour, self.session.close_minute)
        return open_t <= t < close_t

    def next_open(self, from_utc: _dt.datetime | None = None) -> _dt.datetime:
        """Return the next market open time in UTC."""
        if from_utc is None:
            from_utc = utc_now()
        local = to_local(from_utc, self.tz_name)
        # start from today, advance if past close or not a trading day
        candidate = local.replace(
            hour=self.session.open_hour,
            minute=self.session.open_minute,
            second=0,
            microsecond=0,
        )
        for _ in range(10):  # max 10-day lookahead
            if self.is_trading_day(candidate.date()) and candidate > local:
                return to_utc(candidate, self.tz_name)
            candidate += _dt.timedelta(days=1)
        return to_utc(candidate, self.tz_name)  # fallback

    def market_time(self, dt_utc: _dt.datetime | None = None) -> _dt.datetime:
        """Return current time in the market's local timezone."""
        if dt_utc is None:
            dt_utc = utc_now()
        return to_local(dt_utc, self.tz_name)


# ---------------------------------------------------------------------------
# Pre-built calendars
# ---------------------------------------------------------------------------

_CN_CALENDAR = TradingCalendar(
    tz_name="Asia/Shanghai",
    holidays=_CN_HOLIDAYS,
    session=Session(
        open_hour=9,
        open_minute=30,
        close_hour=15,
        close_minute=0,
        pre_open_hour=9,
        pre_open_minute=15,
        post_close_hour=15,
        post_close_minute=30,
    ),
)

_HK_CALENDAR = TradingCalendar(
    tz_name="Asia/Hong_Kong",
    holidays=_HK_HOLIDAYS,
    session=Session(
        open_hour=9,
        open_minute=30,
        close_hour=16,
        close_minute=0,
        pre_open_hour=9,
        pre_open_minute=0,
        post_close_hour=16,
        post_close_minute=10,
    ),
)

_US_EASTERN_CALENDAR = TradingCalendar(
    tz_name="America/New_York",
    holidays=_US_HOLIDAYS,
    session=Session(
        open_hour=9,
        open_minute=30,
        close_hour=16,
        close_minute=0,
        pre_open_hour=4,
        pre_open_minute=0,
        post_close_hour=20,
        post_close_minute=0,
    ),
)


def get_calendar(market: str) -> TradingCalendar:
    """Return a pre-built calendar by market name."""
    key = market.lower().strip()
    if key in ("cn", "a-share", "ashare", "a股", "sse", "szse"):
        return _CN_CALENDAR
    if key in ("hk", "hong-kong", "港股", "hkex"):
        return _HK_CALENDAR
    if key in ("us", "america", "美股", "nyse", "nasdaq"):
        return _US_EASTERN_CALENDAR
    raise ValueError(f"Unknown market for calendar: {market!r}")
