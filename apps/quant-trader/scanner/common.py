"""Scanner 公共常量、工具函数和配置类。

统一 lite.py 和 __init__.py 共享的过滤门控常量、数据获取工具。
新增 ScanConfig 支持运行时配置覆盖。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── 过滤门控常量 (默认值, 可被 ScanConfig 覆盖) ─────────────────────
_MIN_PRICE = 3.0
_MAX_PRICE = 200.0
_MIN_TURNOVER_PCT = 2.0
_MIN_AMOUNT_YI = 5.0  # 成交额 > 5亿

# 涨跌停阈值
_LIMIT_THRESHOLD = 9.8

# ST / 退市关键字
_ST_KEYWORDS = ("ST", "退")


@dataclass
class ScanConfig:
    """扫描器配置 — 所有可调参数集中在此。

    Usage:
        cfg = ScanConfig(min_amount_yi=3.0)  # 自定义
        run(config=cfg)
    """

    # ── 门控参数 ──
    min_price: float = _MIN_PRICE
    max_price: float = _MAX_PRICE
    min_turnover_pct: float = _MIN_TURNOVER_PCT
    min_amount_yi: float = _MIN_AMOUNT_YI
    limit_threshold: float = _LIMIT_THRESHOLD

    # ── 扫描参数 ──
    top_n: int = 12
    kline_days: int = 30
    kline_fetch_ratio: float = 3.0  # kline_fetch = top_n * ratio

    # ── 评分权重 (总和=100) ──
    w_amount: float = 30.0  # 成交额排名
    w_turnover: float = 25.0  # 换手率排名
    w_momentum: float = 20.0  # 动量绝对值
    w_direction: float = 15.0  # 方向分
    w_vol_ratio: float = 10.0  # 量比分

    # ── 排名加速参数 ──
    boost_top10: float = 8.0  # top 10% 额外加分
    boost_top25: float = 5.0
    boost_top50: float = 2.0

    # ── 玄学权重 (已下线，保留字段兼容旧配置) ──
    divination_weight: float = 0.0

    # ── 模式 ──
    mode: str = "lite"  # "lite" | "full" | "backtest"
    use_divination: bool = False

    # ── AI 增强 ──
    use_ai: bool = False  # 启用 LLM 批量研判
    ai_top_n: int = 5  # 对 top N 只运行 AI 分析
    ai_provider: str = "deepseek"  # LLM 提供商
    ai_api_key: str = ""  # 留空则自动从 env 读取
    ai_timeout: float = 25.0  # 单次 LLM 超时(秒)
    ai_concurrency: int = 3  # 并发调用数
    use_ai_score: bool = False  # AI 置信度是否叠加到最终 score
    ai_score_weight: float = 10.0  # AI 对 score 的最大影响幅度

    # ── ST/涨停过滤 ──
    st_keywords: tuple[str, ...] = field(default_factory=lambda: _ST_KEYWORDS)
    block_limit_up: bool = True  # 不追涨停
    block_limit_down: bool = True  # 不接跌停

    def __post_init__(self):
        # 验证权重总和
        total = self.w_amount + self.w_turnover + self.w_momentum + self.w_direction + self.w_vol_ratio
        if abs(total - 100) > 0.1:
            # 自动归一化
            scale = 100 / total
            self.w_amount *= scale
            self.w_turnover *= scale
            self.w_momentum *= scale
            self.w_direction *= scale
            self.w_vol_ratio *= scale


# ── 工具函数 ─────────────────────────────────────────────────────────


def safe_float(val: Any) -> float:
    """安全浮点转换，失败返回 0.0。"""
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def is_st_or_delisted(name: str) -> bool:
    """判断是否为 ST 或退市股。"""
    return any(kw in name for kw in _ST_KEYWORDS)


def is_limit_price(chg_pct: float) -> bool:
    """判断是否涨跌停。"""
    return abs(chg_pct) > _LIMIT_THRESHOLD
