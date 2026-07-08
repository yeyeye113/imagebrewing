"""市场时钟模块 - A股/美股/期货交易时间判断。"""

from datetime import UTC, datetime, timedelta, timezone

# A 股交易时间（北京时间）
ASHARE_OPEN = (9, 30)  # 9:30 CST
ASHARE_CLOSE = (15, 0)  # 15:00 CST
ASHARE_LUNCH = ((11, 30), (13, 0))  # 午休

# 美股交易时间（美东时间 EST，含夏令时简化）
US_OPEN = (9, 30)
US_CLOSE = (16, 0)


def _now() -> datetime:
    return datetime.now()


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _cst_now() -> datetime:
    """Current China Standard Time (UTC+8)."""
    return datetime.now(timezone(timedelta(hours=8)))


def _est_now() -> datetime:
    """Current US Eastern time (approximate — always UTC-5 for simplicity)."""
    return datetime.now(timezone(timedelta(hours=-5)))


def market_is_open(market: str) -> bool:
    """Check if the given market is open right now."""
    market = market.lower()
    if market in ("futures",):
        # 期货交易时间: 日盘 9:00-15:00 (含午休), 夜盘 21:00-23:00
        now = _cst_now()
        if now.weekday() >= 5:
            return False
        t = now.hour * 60 + now.minute
        # 日盘: 9:00-11:30, 13:30-15:00
        day1 = 9 * 60 <= t < 11 * 60 + 30
        day2 = 13 * 60 + 30 <= t < 15 * 60
        # 夜盘: 21:00-23:00
        night = 21 * 60 <= t < 23 * 60
        return day1 or day2 or night
    if market in ("cn", "a股", "ashare", "cn_paper", "akshare"):
        now = _cst_now()
        if now.weekday() >= 5:
            return False
        t = now.hour * 60 + now.minute
        open_t = ASHARE_OPEN[0] * 60 + ASHARE_OPEN[1]
        close_t = ASHARE_CLOSE[0] * 60 + ASHARE_CLOSE[1]
        lunch_start = ASHARE_LUNCH[0][0] * 60 + ASHARE_LUNCH[0][1]
        lunch_end = ASHARE_LUNCH[1][0] * 60 + ASHARE_LUNCH[1][1]
        if lunch_start <= t < lunch_end:
            return False
        return open_t <= t < close_t
    # US / default
    now = _est_now()
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    return (US_OPEN[0] * 60 + US_OPEN[1]) <= t < (US_CLOSE[0] * 60 + US_CLOSE[1])


def seconds_until_market(market: str) -> float:
    """Seconds until the next market open. Returns 0 if already open."""
    from datetime import timedelta

    market = market.lower()
    if market_is_open(market):
        return 0.0

    if market in ("cn", "a股", "ashare", "cn_paper", "akshare"):
        now = _cst_now()
        target = now.replace(hour=ASHARE_OPEN[0], minute=ASHARE_OPEN[1], second=0, microsecond=0)
        if now.weekday() >= 5 or now >= target:
            days = (7 - now.weekday()) % 7
            if days == 0:
                days = 1
            target = target + timedelta(days=days)
        return max(0, (target - now).total_seconds())
    # US
    now = _est_now()
    target = now.replace(hour=US_OPEN[0], minute=US_OPEN[1], second=0, microsecond=0)
    if now.weekday() >= 5 or now >= target:
        days = (7 - now.weekday()) % 7
        if days == 0:
            days = 1
        target = target + timedelta(days=days)
    return max(0, (target - now).total_seconds())


def market_label(market: str) -> str:
    m = market.lower()
    if m in ("cn", "a股", "ashare", "cn_paper", "akshare"):
        return "A股"
    if m in ("futures",):
        return "期货"
    return "美股"
