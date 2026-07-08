"""管线常量与配置: 行业映射, 标的池, 策略定义, 速度档位."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pandas as pd

# ═══════════════════════════════════════════════════════════════════════
# 行业→五行板块映射 (与 news/parser.py SECTOR_KEYWORDS 完全对齐)
# ═══════════════════════════════════════════════════════════════════════

SECTOR_TO_WUXING: dict[str, str] = {
    "金融": "金", "银行": "金", "保险": "金", "证券": "金",
    "有色金属": "金", "钢铁": "金", "贵金属": "金", "黄金": "金",
    "机械": "金", "汽车": "金",
    "医药": "木", "医疗": "木", "中药": "木",
    "消费": "木", "白酒": "木", "食品": "木", "饮料": "木", "乳业": "木",
    "旅游": "木", "零售": "木", "养殖": "木", "农业": "木",
    "种业": "木", "教育": "木", "环保": "木", "造纸": "木",
    "科技/半导体": "火", "半导体": "火", "芯片": "火", "电子": "火",
    "计算机": "火", "软件": "火", "互联网": "火", "人工智能": "火",
    "军工": "火", "航天": "火", "通信": "火", "5G": "火",
    "传媒": "火", "游戏": "火",
    "新能源": "火", "光伏": "火", "电池": "火",
    "地产基建": "土", "房地产": "土", "建筑": "土", "基建": "土",
    "建材": "土", "水泥": "土", "煤炭": "土", "石油": "土",
    "化工": "土", "矿产": "土", "稀土": "土",
    "有色/资源": "金",
    "航运": "水", "港口": "水", "物流": "水", "电力": "水",
    "渔业": "水", "贸易": "水",
}

# ═══════════════════════════════════════════════════════════════════════
# 50 只易增长 A 股核心标的 (代码, 名称, 板块, 五行)
# ═══════════════════════════════════════════════════════════════════════

STOCK_50: list[tuple[str, str, str, str]] = [
    ("601318", "中国平安", "保险", "金"),
    ("600036", "招商银行", "银行", "金"),
    ("000001", "平安银行", "银行", "金"),
    ("601398", "工商银行", "银行", "金"),
    ("600030", "中信证券", "证券", "金"),
    ("601688", "华泰证券", "证券", "金"),
    ("300059", "东方财富", "证券", "金"),
    ("601166", "兴业银行", "银行", "金"),
    ("000725", "京东方A",  "电子", "火"),
    ("600519", "贵州茅台", "白酒", "木"),
    ("000858", "五粮液", "白酒", "木"),
    ("000568", "泸州老窖", "白酒", "木"),
    ("600887", "伊利股份", "乳业", "木"),
    ("600276", "恒瑞医药", "医药", "木"),
    ("300760", "迈瑞医疗", "医疗", "木"),
    ("300015", "爱尔眼科", "医疗", "木"),
    ("002714", "牧原股份", "养殖", "木"),
    ("601888", "中国中免", "零售", "木"),
    ("600809", "山西汾酒", "白酒", "木"),
    ("002304", "洋河股份", "白酒", "木"),
    ("000895", "双汇发展", "食品", "木"),
    ("300896", "爱美客", "医疗", "木"),
    ("002594", "比亚迪", "汽车", "火"),
    ("300750", "宁德时代", "电池", "火"),
    ("601012", "隆基绿能", "光伏", "火"),
    ("002230", "科大讯飞", "人工智能", "火"),
    ("688981", "中芯国际", "半导体", "火"),
    ("603019", "中科曙光", "计算机", "火"),
    ("002415", "海康威视", "人工智能", "火"),
    ("600570", "恒生电子", "软件", "火"),
    ("002371", "北方华创", "半导体", "火"),
    ("688111", "金山办公", "软件", "火"),
    ("300124", "汇川技术", "机械", "火"),
    ("300274", "阳光电源", "光伏", "火"),
    ("601138", "工业富联", "通信", "火"),
    ("000063", "中兴通讯", "通信", "火"),
    ("601857", "中国石油", "石油", "水"),
    ("601088", "中国神华", "煤炭", "土"),
    ("600900", "长江电力", "电力", "水"),
    ("600941", "中国移动", "通信", "水"),
    ("601899", "紫金矿业", "黄金", "金"),
    ("600547", "山东黄金", "黄金", "金"),
    ("600188", "兖矿能源", "煤炭", "土"),
    ("002460", "赣锋锂业", "有色金属", "金"),
    ("603799", "华友钴业", "有色金属", "金"),
    ("600585", "海螺水泥", "建材", "土"),
    ("000333", "美的集团", "机械", "土"),
    ("000651", "格力电器", "机械", "土"),
    ("002050", "三花智控", "机械", "金"),
    ("601100", "恒立液压", "机械", "金"),
]

# 期货标的列表
FUTURES_POOL: list[tuple[str, str, str, str]] = [
    ("IF", "沪深300",  "股指", "土"),
    ("IC", "中证500",  "股指", "土"),
    ("IH", "上证50",   "股指", "土"),
    ("IM", "中证1000", "股指", "土"),
    ("TL", "30年国债", "债券", "土"),
    ("RB", "螺纹钢", "黑色", "土"),("HC", "热卷","黑色", "土"),
    ("I",  "铁矿石", "黑色", "土"),("J",  "焦炭","黑色", "土"),
    ("JM", "焦煤",   "黑色", "土"),("FG", "玻璃","建材", "土"),
    ("SA", "纯碱",   "化工", "水"),
    ("CU", "沪铜", "有色", "金"),("AL", "沪铝", "有色", "金"),
    ("ZN", "沪锌", "有色", "金"),("NI", "沪镍", "有色", "金"),
    ("AU", "沪金", "贵金属", "金"),("AG", "沪银", "贵金属", "金"),
    ("SC", "原油",   "能源", "火"),("FU", "燃料油", "能源", "火"),
    ("LU", "低硫油", "能源", "火"),("PG", "液化气", "能源", "火"),
    ("MA", "甲醇", "化工", "水"),("TA", "PTA","化工", "水"),
    ("EG", "乙二醇", "化工", "水"),("BU", "沥青","化工", "水"),
    ("RU", "橡胶",   "化工", "水"),
    ("M",  "豆粕", "农产品", "木"),("RM", "菜粕", "农产品", "木"),
    ("Y",  "豆油", "农产品", "木"),("P",  "棕榈油", "农产品", "木"),
    ("OI", "菜油",   "农产品", "木"),("CF", "棉花","农产品", "木"),
    ("SR", "白糖",   "农产品", "木"),("JD", "鸡蛋","农产品", "木"),
    ("LH", "生猪",   "农产品", "木"),
]

# ── 策略 ───────────────────────────────────────────────────────────────
# (策略名, 参数 dict, 中文标签); 参数为 int/float 混合, 显式标注避免推断成 object
StrategySpec = tuple[str, dict[str, Any], str]

STRATEGIES: list[StrategySpec] = [
    ("sma_cross", {"fast": 20, "slow": 50}, "双均线"),
    ("rsi", {"period": 14, "oversold": 30, "overbought": 70}, "RSI"),
    ("bollinger", {"period": 20, "num_std": 2.0}, "布林带"),
    ("momentum", {"lookback": 90}, "动量"),
]

# 第一关: 单窗口共振 (减少重复计算)
RESONANCE_WINDOWS = [120]

INITIAL_STRATEGIES: list[StrategySpec] = [
    ("sma_cross", {"fast": 10, "slow": 40}, "双均线(中)"),
    ("sma_cross", {"fast": 20, "slow": 50}, "双均线(标)"),
    ("rsi", {"period": 14, "oversold": 30, "overbought": 70}, "RSI"),
    ("bollinger", {"period": 20, "num_std": 2.0}, "布林带"),
    ("momentum", {"lookback": 60, "trend_filter": 100}, "动量(中)"),
    ("momentum", {"lookback": 120, "trend_filter": 200}, "动量(长)"),
    ("rsi", {"period": 7, "oversold": 20, "overbought": 80}, "RSI(快)"),
]

RESONANCE_CORE_STRATEGIES = INITIAL_STRATEGIES[:5]

ROUND2_STRATEGIES: list[StrategySpec] = [
    ("sma_cross", {"fast": 5, "slow": 20}, "双均线(短)"),
    ("sma_cross", {"fast": 20, "slow": 50}, "双均线(中)"),
    ("rsi", {"period": 7, "oversold": 25, "overbought": 75}, "RSI(快)"),
    ("rsi", {"period": 14, "oversold": 30, "overbought": 70}, "RSI(标)"),
    ("bollinger", {"period": 20, "num_std": 2.0}, "布林带"),
    ("momentum", {"lookback": 20, "trend_filter": 50}, "动量(短)"),
    ("momentum", {"lookback": 60, "trend_filter": 120}, "动量(中)"),
]
ROUND2_CORE_STRATEGIES = ROUND2_STRATEGIES[:2]

TIME_WINDOWS = [("3d", 120, 3), ("5d", 120, 5), ("7d", 120, 7), ("30d", 250, 20)]
_LOADER_TIMEOUT_S = 8
_PRICE_CACHE: dict[str, tuple[float, pd.DataFrame]] = {}
_CACHE_TTL_S = 600
_CACHE_MAX_SIZE = 200

# 分段推送: stage, items(dict[]), meta
StageCallback = Callable[[str, list[dict], dict], None]

_STAGES_PENDING = "计算中…"


# ═══════════════════════════════════════════════════════════════════════
# PipelineProfile — 管线速度档位
# ═══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class PipelineProfile:
    """管线速度档位 — fast 优先首屏, balanced 更完整."""
    name: str = "balanced"
    pool_cap: int = 14
    loader_timeout: float = 5.0
    prefetch_max_wait: float = 20.0
    loader_workers: int = 12
    screen_workers: int = 10
    early_min_prices: int = 5
    early_min_results: int = 3
    force_no_news: bool = False
    force_no_wuxing: bool = False


PROFILE_FAST = PipelineProfile(
    name="fast",
    pool_cap=10,
    loader_timeout=4.0,
    prefetch_max_wait=14.0,
    loader_workers=14,
    early_min_prices=4,
    early_min_results=2,
    force_no_news=True,
    force_no_wuxing=True,
)
PROFILE_BALANCED = PipelineProfile(
    name="balanced",
    pool_cap=14,
    loader_timeout=5.0,
    prefetch_max_wait=22.0,
    early_min_prices=6,
    early_min_results=3,
)


PROFILE_PRECISE = PipelineProfile(
    name="precise",
    pool_cap=3,
    loader_timeout=6.0,
    prefetch_max_wait=25.0,
    loader_workers=10,
    early_min_prices=8,
    early_min_results=1,
    force_no_news=True,
    force_no_wuxing=True,
)

# research: 低门槛观察 11 层信号, 输出带 OOS 免责声明, 禁止当实盘依据
PROFILE_RESEARCH = PipelineProfile(
    name="research",
    pool_cap=10,
    loader_timeout=6.0,
    prefetch_max_wait=25.0,
    loader_workers=10,
    early_min_prices=8,
    early_min_results=1,
    force_no_news=True,
    force_no_wuxing=True,
)


def resolve_pipeline_profile(name: str | None = None) -> PipelineProfile:
    n = (name or "fast").strip().lower()
    if n in ("balanced", "full", "standard"):
        return PROFILE_BALANCED
    if n in ("precise", "high_precision", "v2"):
        return PROFILE_PRECISE
    if n in ("research", "explore", "study"):
        return PROFILE_RESEARCH
    return PROFILE_FAST
