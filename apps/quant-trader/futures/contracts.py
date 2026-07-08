"""期货合约规格 — 国内 6 大交易所主力品种 + 保证金 + 交易时间。

数据来源: 各交易所官网 + akshare 实时补充。
主力合约按持仓量最大自动判定。
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum

# ══════════════════════════════════════════════════════════════════
# 期货交易时段 (北京时间 CST)
# ══════════════════════════════════════════════════════════════════


class NightSession(Enum):
    NONE = 0  # 无夜盘
    TILL_2300 = 1  # 夜盘到 23:00（农产品/部分化工）
    TILL_0100 = 2  # 夜盘到 01:00（金属/能源）
    TILL_0230 = 3  # 夜盘到 02:30（黄金白银/原油/铜）


@dataclass
class MarketHours:
    """一个交易品种的完整交易时段 (CST)。"""

    name: str
    morning_open: tuple = (9, 0)  # 早市开盘
    morning_close: tuple = (11, 30)
    afternoon_open: tuple = (13, 30)  # 午市开盘
    afternoon_close: tuple = (15, 0)
    night_open: tuple | None = None  # 夜盘开盘（次日，跨日）
    night_close: tuple | None = None

    def is_trading(self, at: dt.datetime | None = None) -> bool:
        """检查当前是否在交易时段内。"""
        now = at or dt.datetime.now()
        t = now.hour * 60 + now.minute
        wd = now.weekday()
        if wd >= 5:
            return False

        # Check regular hours
        mo = self.morning_open[0] * 60 + self.morning_open[1]
        mc = self.morning_close[0] * 60 + self.morning_close[1]
        ao = self.afternoon_open[0] * 60 + self.afternoon_open[1]
        ac = self.afternoon_close[0] * 60 + self.afternoon_close[1]

        in_day = (mo <= t < mc) or (ao <= t < ac)

        # Night session: if we have one, check whether current time falls in it
        if self.night_open and self.night_close:
            no = self.night_open[0] * 60 + self.night_open[1]
            nc = self.night_close[0] * 60 + self.night_close[1]
            if no > nc:  # crosses midnight (e.g. 21:00-02:30)
                if t >= no:
                    # Evening: today must be a weekday (Mon-Fri)
                    if 0 <= wd <= 4:
                        return True
                elif t < nc:
                    # Early morning: belongs to yesterday's night session
                    # Friday night → Saturday morning (wd=5): valid
                    # Saturday night → Sunday morning (wd=6): no session
                    # Sunday night → Monday morning (wd=0): no session
                    if wd == 5 or (1 <= wd <= 4):
                        return True
            else:
                if no <= t < nc:
                    return True
            return bool(in_day)
        return bool(in_day)

    def next_open_seconds(self, at: dt.datetime | None = None) -> float:
        """距离下一次开盘的秒数。"""
        now = at or dt.datetime.now()
        if self.is_trading(now):
            return 0.0

        wd = now.weekday()
        next_open: dt.datetime | None = None

        # Try today's morning/afternoon/night
        candidates = []
        if now.hour * 60 + now.minute < self.morning_open[0] * 60 + self.morning_open[1]:
            candidates.append(now.replace(hour=self.morning_open[0], minute=self.morning_open[1], second=0))
        if now.hour * 60 + now.minute < self.afternoon_open[0] * 60 + self.afternoon_open[1]:
            candidates.append(now.replace(hour=self.afternoon_open[0], minute=self.afternoon_open[1], second=0))
        if self.night_open:
            no_min = self.night_open[0] * 60 + self.night_open[1]
            if now.hour * 60 + now.minute < no_min or no_min < self.afternoon_close[0] * 60 + self.afternoon_close[1]:
                candidates.append(now.replace(hour=self.night_open[0], minute=self.night_open[1], second=0))

        candidates.sort()
        for c in candidates:
            if c > now and c.weekday() < 5:
                return (c - now).total_seconds()

        # Next weekday morning
        days = 1
        while (wd + days) % 7 >= 5:
            days += 1
        target = now + dt.timedelta(days=days)
        target = target.replace(hour=self.morning_open[0], minute=self.morning_open[1], second=0)
        return (target - now).total_seconds()

    @property
    def label(self) -> str:
        parts = [
            f"早{self.morning_open[0]:02d}:{self.morning_open[1]:02d}-{self.morning_close[0]:02d}:{self.morning_close[1]:02d}",
            f"午{self.afternoon_open[0]:02d}:{self.afternoon_open[1]:02d}-{self.afternoon_close[0]:02d}:{self.afternoon_close[1]:02d}",
        ]
        if self.night_open and self.night_close:
            parts.append(
                f"夜{self.night_open[0]:02d}:{self.night_open[1]:02d}-{self.night_close[0]:02d}:{self.night_close[1]:02d}"
            )
        return f"{self.name} " + " / ".join(parts)


# ── 品种交易时间表 ──────────────────────────────────────────────

MARKET_HOURS: dict[str, MarketHours] = {
    # 金融期货 (CFFEX) — 无夜盘
    "IF": MarketHours("沪深300股指", night_open=None, night_close=None),
    "IC": MarketHours("中证500股指", night_open=None, night_close=None),
    "IH": MarketHours("上证50股指", night_open=None, night_close=None),
    "IM": MarketHours("中证1000股指", night_open=None, night_close=None),
    "TS": MarketHours("2年期国债", night_open=None, night_close=None),
    "TF": MarketHours("5年期国债", night_open=None, night_close=None),
    "T": MarketHours("10年期国债", night_open=None, night_close=None),
    "TL": MarketHours("30年期国债", night_open=None, night_close=None),
    # 贵金属 (SHFE) — 夜盘到 02:30
    "AU": MarketHours("黄金", night_open=(21, 0), night_close=(2, 30)),
    "AG": MarketHours("白银", night_open=(21, 0), night_close=(2, 30)),
    # 有色金属 (SHFE) — 夜盘到 01:00
    "CU": MarketHours("铜", night_open=(21, 0), night_close=(1, 0)),
    "AL": MarketHours("铝", night_open=(21, 0), night_close=(1, 0)),
    "ZN": MarketHours("锌", night_open=(21, 0), night_close=(1, 0)),
    "PB": MarketHours("铅", night_open=(21, 0), night_close=(1, 0)),
    "NI": MarketHours("镍", night_open=(21, 0), night_close=(1, 0)),
    "SN": MarketHours("锡", night_open=(21, 0), night_close=(1, 0)),
    "SS": MarketHours("不锈钢", night_open=(21, 0), night_close=(1, 0)),
    # 黑色金属 (SHFE) — 夜盘到 23:00
    "RB": MarketHours("螺纹钢", night_open=(21, 0), night_close=(23, 0)),
    "HC": MarketHours("热卷", night_open=(21, 0), night_close=(23, 0)),
    "I": MarketHours("铁矿石", night_open=(21, 0), night_close=(23, 0)),  # DCE
    # 能源化工 (SHFE/INE) — 夜盘到 23:00 或 02:30
    "SC": MarketHours("原油", night_open=(21, 0), night_close=(2, 30)),
    "FU": MarketHours("燃料油", night_open=(21, 0), night_close=(23, 0)),
    "BU": MarketHours("沥青", night_open=(21, 0), night_close=(23, 0)),
    "RU": MarketHours("橡胶", night_open=(21, 0), night_close=(23, 0)),
    "SP": MarketHours("纸浆", night_open=(21, 0), night_close=(23, 0)),
    "PG": MarketHours("LPG", night_open=(21, 0), night_close=(23, 0)),  # DCE
    # 化工 (DCE/CZCE) — 夜盘到 23:00
    "TA": MarketHours("PTA", night_open=(21, 0), night_close=(23, 0)),
    "MA": MarketHours("甲醇", night_open=(21, 0), night_close=(23, 0)),
    "EG": MarketHours("乙二醇", night_open=(21, 0), night_close=(23, 0)),
    "EB": MarketHours("苯乙烯", night_open=(21, 0), night_close=(23, 0)),
    "PP": MarketHours("聚丙烯", night_open=(21, 0), night_close=(23, 0)),
    "L": MarketHours("塑料", night_open=(21, 0), night_close=(23, 0)),
    "V": MarketHours("PVC", night_open=(21, 0), night_close=(23, 0)),
    "SA": MarketHours("纯碱", night_open=(21, 0), night_close=(23, 0)),
    "UR": MarketHours("尿素", night_open=(21, 0), night_close=(23, 0)),
    # 农产品 (DCE/CZCE) — 部分有夜盘
    "A": MarketHours("豆一", night_open=(21, 0), night_close=(23, 0)),
    "B": MarketHours("豆二", night_open=(21, 0), night_close=(23, 0)),
    "M": MarketHours("豆粕", night_open=(21, 0), night_close=(23, 0)),
    "Y": MarketHours("豆油", night_open=(21, 0), night_close=(23, 0)),
    "P": MarketHours("棕榈油", night_open=(21, 0), night_close=(23, 0)),
    "OI": MarketHours("菜油", night_open=(21, 0), night_close=(23, 0)),
    "RM": MarketHours("菜粕", night_open=(21, 0), night_close=(23, 0)),
    "C": MarketHours("玉米", night_open=(21, 0), night_close=(23, 0)),
    "CS": MarketHours("淀粉", night_open=(21, 0), night_close=(23, 0)),
    "JD": MarketHours("鸡蛋", night_open=None, night_close=None),
    "LH": MarketHours("生猪", night_open=None, night_close=None),
    "AP": MarketHours("苹果", night_open=None, night_close=None),
    "CJ": MarketHours("红枣", night_open=None, night_close=None),
    "CF": MarketHours("棉花", night_open=(21, 0), night_close=(23, 0)),
    "SR": MarketHours("白糖", night_open=(21, 0), night_close=(23, 0)),
    # 广期所
    "SI": MarketHours("工业硅", night_open=None, night_close=None),
    "LC": MarketHours("碳酸锂", night_open=None, night_close=None),
}

# ══════════════════════════════════════════════════════════════════
# 合约规格表
# ══════════════════════════════════════════════════════════════════


@dataclass
class ContractSpec:
    """单品种期货合约参数。"""

    code: str  # 品种代码（大写，如 RB, SC, IF）
    name: str  # 中文名
    exchange: str  # 交易所: SHFE/DCE/CZCE/CFFEX/INE/GFEX
    contract_size: int  # 每手数量（吨/克/点）
    tick_size: float  # 最小变动价位
    tick_value: float  # 每跳动一下的盈亏（元）
    margin_rate: float  # 交易所保证金比例（典型值）
    multiplier: int = 1  # 合约乘数（股指为每点价值）
    lot_size: int = 1  # 最小交易单位（手）

    def calc_margin(self, price: float, lots: int = 1) -> float:
        """按当前价计算保证金。"""
        if self.multiplier != 1:
            return price * self.multiplier * self.margin_rate * lots
        return price * self.contract_size * self.margin_rate * lots

    @property
    def tick_value_per_lot(self) -> float:
        """每跳一下（1 tick）的盈亏。"""
        return abs(self.tick_value)

    def display_price(self, price: float) -> str:
        """格式化价格显示。"""
        if self.multiplier != 1:
            return f"{price:.1f} 点"
        return f"¥{price:,.0f}/吨"


FUTURES_CONTRACTS: dict[str, ContractSpec] = {
    # ── 金融期货 (CFFEX) ──
    "IF": ContractSpec("IF", "沪深300股指", "CFFEX", 0, 0.2, 60, 0.12, 300),
    "IC": ContractSpec("IC", "中证500股指", "CFFEX", 0, 0.2, 40, 0.14, 200),
    "IH": ContractSpec("IH", "上证50股指", "CFFEX", 0, 0.2, 60, 0.12, 300),
    "IM": ContractSpec("IM", "中证1000股指", "CFFEX", 0, 0.2, 40, 0.15, 200),
    "TS": ContractSpec("TS", "2年期国债", "CFFEX", 0, 0.005, 100, 0.005, 20000),
    "TF": ContractSpec("TF", "5年期国债", "CFFEX", 0, 0.005, 50, 0.012, 10000),
    "T": ContractSpec("T", "10年期国债", "CFFEX", 0, 0.005, 50, 0.02, 10000),
    "TL": ContractSpec("TL", "30年期国债", "CFFEX", 0, 0.01, 100, 0.035, 10000),
    # ── 贵金属 (SHFE) ──
    "AU": ContractSpec("AU", "黄金", "SHFE", 1000, 0.02, 20, 0.08),
    "AG": ContractSpec("AG", "白银", "SHFE", 15, 1, 15, 0.10),
    # ── 有色金属 (SHFE) ──
    "CU": ContractSpec("CU", "铜", "SHFE", 5, 10, 50, 0.09),
    "AL": ContractSpec("AL", "铝", "SHFE", 5, 5, 25, 0.09),
    "ZN": ContractSpec("ZN", "锌", "SHFE", 5, 5, 25, 0.09),
    "PB": ContractSpec("PB", "铅", "SHFE", 5, 5, 25, 0.09),
    "NI": ContractSpec("NI", "镍", "SHFE", 1, 10, 10, 0.12),
    "SN": ContractSpec("SN", "锡", "SHFE", 1, 10, 10, 0.12),
    "SS": ContractSpec("SS", "不锈钢", "SHFE", 5, 5, 25, 0.09),
    # ── 黑色 (SHFE) ──
    "RB": ContractSpec("RB", "螺纹钢", "SHFE", 10, 1, 10, 0.08),
    "HC": ContractSpec("HC", "热卷", "SHFE", 10, 1, 10, 0.08),
    "I": ContractSpec("I", "铁矿石", "DCE", 100, 0.5, 50, 0.13),
    # ── 能源化工 ──
    "SC": ContractSpec("SC", "原油", "INE", 1000, 0.1, 100, 0.10),
    "FU": ContractSpec("FU", "燃料油", "SHFE", 10, 1, 10, 0.10),
    "BU": ContractSpec("BU", "沥青", "SHFE", 10, 2, 20, 0.10),
    "RU": ContractSpec("RU", "橡胶", "SHFE", 10, 5, 50, 0.09),
    "SP": ContractSpec("SP", "纸浆", "SHFE", 10, 2, 20, 0.08),
    "PG": ContractSpec("PG", "LPG", "DCE", 20, 1, 20, 0.09),
    "TA": ContractSpec("TA", "PTA", "CZCE", 5, 2, 10, 0.07),
    "MA": ContractSpec("MA", "甲醇", "CZCE", 10, 1, 10, 0.08),
    "EG": ContractSpec("EG", "乙二醇", "DCE", 10, 1, 10, 0.08),
    "EB": ContractSpec("EB", "苯乙烯", "DCE", 5, 1, 5, 0.09),
    "PP": ContractSpec("PP", "聚丙烯", "DCE", 5, 1, 5, 0.08),
    "L": ContractSpec("L", "塑料", "DCE", 5, 1, 5, 0.08),
    "V": ContractSpec("V", "PVC", "DCE", 5, 1, 5, 0.08),
    "SA": ContractSpec("SA", "纯碱", "CZCE", 20, 1, 20, 0.09),
    "UR": ContractSpec("UR", "尿素", "CZCE", 20, 1, 20, 0.08),
    # ── 油脂油料 ──
    "A": ContractSpec("A", "豆一", "DCE", 10, 1, 10, 0.08),
    "B": ContractSpec("B", "豆二", "DCE", 10, 1, 10, 0.08),
    "M": ContractSpec("M", "豆粕", "DCE", 10, 1, 10, 0.08),
    "Y": ContractSpec("Y", "豆油", "DCE", 10, 2, 20, 0.08),
    "P": ContractSpec("P", "棕榈油", "DCE", 10, 2, 20, 0.09),
    "OI": ContractSpec("OI", "菜油", "CZCE", 10, 1, 10, 0.08),
    "RM": ContractSpec("RM", "菜粕", "CZCE", 10, 1, 10, 0.08),
    # ── 农产品 ──
    "C": ContractSpec("C", "玉米", "DCE", 10, 1, 10, 0.08),
    "CS": ContractSpec("CS", "淀粉", "DCE", 10, 1, 10, 0.08),
    "JD": ContractSpec("JD", "鸡蛋", "DCE", 5, 1, 5, 0.09),
    "LH": ContractSpec("LH", "生猪", "DCE", 16, 5, 80, 0.12),
    "AP": ContractSpec("AP", "苹果", "CZCE", 10, 1, 10, 0.09),
    "CJ": ContractSpec("CJ", "红枣", "CZCE", 5, 5, 25, 0.09),
    "CF": ContractSpec("CF", "棉花", "CZCE", 5, 5, 25, 0.08),
    "SR": ContractSpec("SR", "白糖", "CZCE", 10, 1, 10, 0.08),
    # ── 广期所 ──
    "SI": ContractSpec("SI", "工业硅", "GFEX", 5, 5, 25, 0.09),
    "LC": ContractSpec("LC", "碳酸锂", "GFEX", 1, 50, 50, 0.12),
}

# ── 成交活跃度分组（用于扫描器优先级） ──
DOMINANT_CONTRACTS = [
    # Tier 1: 超级活跃
    "RB",
    "I",
    "SC",
    "M",
    "RM",
    "SA",
    "TA",
    "MA",
    "P",
    "Y",
    # Tier 2: 活跃
    "AG",
    "AU",
    "CU",
    "ZN",
    "FG",
    "HC",
    "EB",
    "EG",
    "PP",
    "L",
    "V",
    "SR",
    "CF",
    "OI",
    "A",
    "C",
    "FU",
    "RU",
    "SS",
    "LC",
    # Tier 3: 一般
    "AL",
    "PB",
    "NI",
    "SN",
    "BU",
    "SP",
    "PG",
    "UR",
    "B",
    "CS",
    "JD",
    "LH",
    "AP",
    "CJ",
    "SI",
    # Tier 4: 金融（大合约）
    "IF",
    "IC",
    "IH",
    "IM",
    "T",
    "TF",
]


def contract_info(code: str) -> ContractSpec | None:
    """获取合约规格信息。"""
    return FUTURES_CONTRACTS.get(code.upper())


def dominant_contract(code: str, date: dt.date | None = None) -> str:
    """获取品种当前主力合约代码 (e.g. RB → RB2501)。"""
    today = date or dt.date.today()
    spec = contract_info(code)
    if not spec:
        return code.upper() + "00"

    # 主力合约月份通常为 1/5/9 (或连续月份中持仓最大的那个)
    # akshare 提供主力合约函数，这里先用规则估算
    months = contract_months(code)
    ym = today.year % 100 * 100
    for m in reversed(months):
        candidate = today.year * 100 + m
        if candidate >= today.year * 100 + today.month:
            return f"{code.upper()}{candidate % 10000:02d}"

    # Fallback to next year's 01
    return f"{code.upper()}{(today.year + 1) % 100:02d}01"


def contract_months(code: str) -> list[int]:
    """返回该品种的挂牌合约月份。"""
    code = code.upper()
    if code in ("IF", "IC", "IH", "IM"):
        return [m for m in range(1, 13)]  # 当月+下月+后两个季月
    if code in ("TS", "TF", "T", "TL"):
        return [3, 6, 9, 12]
    # 大多数商品期货
    return [1, 5, 9]


def margin_required(code: str, price: float, lots: int = 1) -> float:
    """计算开仓所需保证金。"""
    spec = contract_info(code)
    if not spec:
        return 0.0
    return spec.calc_margin(price, lots)


def next_expiry(code: str, date: dt.date | None = None) -> dt.date:
    """估算主力合约的下一个到期日（最后交易日）。"""
    today = date or dt.date.today()
    dom = dominant_contract(code, today)
    # 提取月份
    try:
        m = int(dom[-2:])
        y = 2000 + int(dom[-4:-2]) if len(dom) >= 4 else today.year
    except (ValueError, IndexError):
        m = today.month + 1
        y = today.year
        if m > 12:  # 12月 → 次年1月
            m = 1
            y += 1

    # 期货通常在合约月份的第10个交易日到期（约第15天）
    return dt.date(y, m, 15)


# ── 交易时段汇总函数 ──


def trading_session(at: dt.datetime | None = None) -> str:
    """返回当前交易时段: morning / afternoon / night / closed。"""
    now = at or dt.datetime.now()
    t = now.hour * 60 + now.minute
    if 9 * 60 + 0 <= t < 11 * 60 + 30:
        return "morning"
    if 13 * 60 + 30 <= t < 15 * 60 + 0:
        return "afternoon"
    if t >= 21 * 60 or t < 2 * 60 + 30:
        return "night"
    return "closed"


def session_label() -> str:
    return {"morning": "🌅 早盘", "afternoon": "☀️ 午盘", "night": "🌙 夜盘", "closed": "⏸️ 休市"}.get(
        trading_session(), "⏸️"
    )


def is_trading_now(code: str | None = None) -> bool:
    """检查当前是否有品种在交易中。如果指定code，检查该品种的具体时段。"""
    if code:
        hours = MARKET_HOURS.get(code.upper())
        if hours:
            return hours.is_trading()
        return False

    # 全局：检查任意时段
    now = dt.datetime.now()
    wd = now.weekday()
    if wd >= 5:
        return False
    t = now.hour * 60 + now.minute
    if (9 * 60 <= t < 11 * 60 + 30) or (13 * 60 + 30 <= t < 15 * 60 + 0):
        return True
    if t >= 21 * 60 or t < 2 * 60 + 30:  # 夜盘
        if wd == 5 and t < 2 * 60 + 30:  # 周六凌晨=周五夜盘
            return True
        if wd < 5:
            return True
    return False


def seconds_to_next_session() -> float:
    """到下一个交易时段的秒数。0=正在交易。"""
    if is_trading_now():
        return 0.0
    now = dt.datetime.now()
    wd = now.weekday()
    t = now.hour * 60 + now.minute

    candidates = []
    if wd < 5:
        if t < 9 * 60:
            candidates.append(now.replace(hour=9, minute=0, second=0))
        if t < 13 * 60 + 30:
            candidates.append(now.replace(hour=13, minute=30, second=0))
        if t < 21 * 60:
            candidates.append(now.replace(hour=21, minute=0, second=0))
        # 夜盘（跨日）
        if t >= 21 * 60:
            next_day = now + dt.timedelta(days=1)
            if next_day.weekday() < 5:
                candidates.append(next_day.replace(hour=9, minute=0, second=0))
    # 周末 → 周一早盘
    days_to_mon = (7 - wd) % 7
    if days_to_mon == 0:
        days_to_mon = 1
    target = now + dt.timedelta(days=days_to_mon)
    candidates.append(target.replace(hour=9, minute=0, second=0))

    candidates.sort()
    for c in candidates:
        if c > now:
            return (c - now).total_seconds()
    return 86400.0
