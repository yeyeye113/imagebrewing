"""行业映射 + 板块共振检测。

Iteration 5: IndustryMap — 代码→行业映射
Iteration 6: SectorDetector — 同板块≥3只同向时触发
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("quanttrader.scanner.sectors")


# ══════════════════════════════════════════════════════════════════
# 行业映射 — 基于代码前缀 + 常见板块
# ══════════════════════════════════════════════════════════════════

# 代码前缀→行业大类 (Sina API 无行业字段时的 fallback)
_CODE_PREFIX_SECTOR: dict[str, str] = {
    # 科技
    "002": "科技", "300": "科技", "688": "科技",
    # 金融
    "600": "金融", "601": "金融", "603": "金融",
    # 消费
    "000": "消费", "001": "消费",
    # 医药
    "003": "医药", "301": "医药",
    # 新能源
    "302": "新能源", "303": "新能源",
}

# 股票代码→板块细分 (常见热门板块)
_CODE_SECTOR_DETAIL: dict[str, str] = {
    # 半导体/芯片
    "sz002156": "半导体", "sz002185": "半导体", "sz002475": "消费电子",
    "sh688981": "半导体", "sz300346": "半导体", "sz300782": "半导体",
    "sh688012": "半导体", "sz002371": "半导体", "sz300661": "半导体",
    # 新能源
    "sz300750": "新能源", "sh601012": "新能源", "sz002594": "新能源",
    "sz300274": "新能源", "sh600438": "新能源", "sz002459": "新能源",
    # 医药
    "sh603259": "医药", "sz300760": "医药", "sh600276": "医药",
    "sz000538": "医药", "sh600196": "医药", "sz300347": "医药",
    # 白酒/消费
    "sh600519": "白酒", "sz000858": "白酒", "sh600809": "白酒",
    "sz000568": "白酒", "sh603369": "白酒",
    # 银行/券商
    "sh601398": "银行", "sh601288": "银行", "sh601939": "银行",
    "sh600036": "银行", "sh601166": "银行",
    "sh601688": "券商", "sh601211": "券商", "sz000776": "券商",
    # 房地产
    "sh600048": "房地产", "sz000002": "房地产", "sz001979": "房地产",
    # 军工
    "sh600893": "军工", "sz000768": "军工", "sh600150": "军工",
    # 人工智能
    "sz002230": "AI", "sz300474": "AI", "sz000977": "AI",
    "sz300124": "AI", "sh688111": "AI",
}


@dataclass
class IndustryMap:
    """代码→行业映射。

    优先级: Sina API industry字段 > _CODE_SECTOR_DETAIL > _CODE_PREFIX_SECTOR > "未知"
    """

    # 外部补充映射 (可从config加载)
    extra_mappings: dict[str, str] = field(default_factory=dict)

    def get_sector(self, code: str, api_industry: str = "") -> str:
        """获取股票行业。

        Args:
            code: 股票代码 (如 'sz002156')
            api_industry: API返回的行业字段 (可能为空)
        """
        # 1. API字段优先
        if api_industry and api_industry.strip():
            return api_industry.strip()

        # 2. 外部补充
        if code in self.extra_mappings:
            return self.extra_mappings[code]

        # 3. 细分板块
        if code in _CODE_SECTOR_DETAIL:
            return _CODE_SECTOR_DETAIL[code]

        # 4. 代码前缀推断（明确剥离市场前缀，避免 lstrip 误删字符集）
        pure_code = code
        for _mkt in ("sh", "sz", "bj"):
            if pure_code.startswith(_mkt):
                pure_code = pure_code[len(_mkt):]
                break
        for prefix, sector in _CODE_PREFIX_SECTOR.items():
            if pure_code.startswith(prefix):
                return sector

        return "未知"

    def get_sector_group(self, code: str) -> str:
        """获取行业大类 (粗分组)。"""
        sector = self.get_sector(code)
        # 细分→大类映射
        _DETAIL_TO_GROUP = {
            "半导体": "科技", "消费电子": "科技", "AI": "科技",
            "新能源": "新能源", "光伏": "新能源", "锂电": "新能源",
            "医药": "医药", "生物": "医药", "中药": "医药",
            "白酒": "消费", "食品": "消费", "零售": "消费",
            "银行": "金融", "券商": "金融", "保险": "金融",
            "房地产": "周期", "钢铁": "周期", "有色": "周期",
            "军工": "军工",
        }
        return _DETAIL_TO_GROUP.get(sector, sector)


# ══════════════════════════════════════════════════════════════════
# 板块共振检测
# ══════════════════════════════════════════════════════════════════


@dataclass
class SectorResonance:
    """板块共振结果。"""
    sector: str
    count: int  # 同板块数量
    direction: str  # "up" / "down" / "mixed"
    avg_chg: float  # 平均涨跌幅
    strength: float  # 共振强度 0-1
    stocks: list[str] = field(default_factory=list)  # 同板块股票代码


class SectorDetector:
    """板块共振检测器。

    当同板块≥threshold只股票同向时，判定为板块共振。
    共振板块的股票加分 (跟风逻辑)。
    """

    def __init__(self, threshold: int = 3):
        """
        Args:
            threshold: 最少同板块股票数触发共振
        """
        self.threshold = threshold
        self.industry_map = IndustryMap()

    def detect(
        self,
        stocks: list[dict[str, Any]],
    ) -> dict[str, SectorResonance]:
        """检测板块共振。

        Args:
            stocks: [{"code": "sz002156", "chg_pct": 5.0, ...}, ...]

        Returns:
            {sector_name: SectorResonance}
        """
        # 按板块分组
        sector_stocks: dict[str, list[dict[str, Any]]] = {}
        for s in stocks:
            code = s.get("code", "")
            api_ind = s.get("industry", "")
            sector = self.industry_map.get_sector(code, api_ind)
            if sector not in sector_stocks:
                sector_stocks[sector] = []
            sector_stocks[sector].append(s)

        resonances: dict[str, SectorResonance] = {}
        for sector, group in sector_stocks.items():
            if len(group) < self.threshold:
                continue

            # 统计方向
            up = [s for s in group if s.get("chg_pct", 0) > 1.0]
            down = [s for s in group if s.get("chg_pct", 0) < -1.0]
            avg_chg = sum(s.get("chg_pct", 0) for s in group) / len(group)

            if len(up) >= self.threshold:
                direction = "up"
                strength = min(len(up) / max(len(group), 1), 1.0)
            elif len(down) >= self.threshold:
                direction = "down"
                strength = min(len(down) / max(len(group), 1), 1.0)
            else:
                direction = "mixed"
                strength = 0.0

            resonances[sector] = SectorResonance(
                sector=sector,
                count=len(group),
                direction=direction,
                avg_chg=round(avg_chg, 2),
                strength=round(strength, 2),
                stocks=[s["code"] for s in group],
            )

        return resonances

    def get_bonus(self, code: str, resonances: dict[str, SectorResonance]) -> float:
        """获取板块共振加分 (0-5)。

        共振板块的上涨股加分，下跌股减分。
        """
        sector = self.industry_map.get_sector(code)
        res = resonances.get(sector)
        if not res or res.direction == "mixed":
            return 0.0

        # 找到该股票在共振中的涨跌
        if res.direction == "up":
            return round(res.strength * 3, 1)  # 最多+3
        else:
            return round(-res.strength * 3, 1)  # 最多-3
