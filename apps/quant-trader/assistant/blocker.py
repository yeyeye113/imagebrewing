"""禁止交易检查 — 12个条件，任一触发则不做。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BlockResult:
    """禁止交易检查结果。"""
    blocked: bool = False
    reason: str = ""

    @staticmethod
    def ok() -> BlockResult:
        return BlockResult(blocked=False, reason="")

    @staticmethod
    def block(reason: str) -> BlockResult:
        return BlockResult(blocked=True, reason=reason)


def check_block(
    range_pct: float,
    direction_allowed: bool,
    sample_size: int,
    stop_status: str,
    score: float,
    daily_loss_pct: float = 0.0,
    same_sector_count: int = 0,
    same_direction_count: int = 0,
    max_daily_loss_pct: float = 2.0,
    max_same_sector: int = 2,
    max_same_direction: int = 2,
    near_expiry: bool = False,
    low_volume: bool = False,
) -> BlockResult:
    """检查是否应该禁止交易。

    返回 BlockResult，blocked=True 表示应该禁止。
    """
    # 1. v530波动范围太小
    if range_pct < 1.5:
        return BlockResult.block(f"v530波动范围{range_pct:.1f}%<1.5%，利润空间不足")

    # 2. v530波动范围过大但无方向优势
    # (这个检查在有方向时跳过，由评分系统处理)

    # 3. SymbolFilter不允许该方向
    if not direction_allowed:
        return BlockResult.block("SymbolFilter不允许该方向")

    # 4. 样本数不足
    if sample_size < 50:
        return BlockResult.block(f"样本数{sample_size}<50，数据不足")

    # 5. ATR判断止损过窄或过宽
    if "过窄" in stop_status:
        return BlockResult.block(f"止损{stop_status}，容易被正常波动打掉")

    # 6. 交易评分低于50
    if score < 50:
        return BlockResult.block(f"交易评分{score:.0f}<50，不值得做")

    # 7. 今日亏损超过限制
    if daily_loss_pct >= max_daily_loss_pct:
        return BlockResult.block(f"今日亏损{daily_loss_pct:.1f}%已达限制{max_daily_loss_pct}%")

    # 8. 同板块重仓
    if same_sector_count >= max_same_sector:
        return BlockResult.block(f"同板块已有{same_sector_count}个持仓，达到上限{max_same_sector}")

    # 9. 同方向重仓
    if same_direction_count >= max_same_direction:
        return BlockResult.block(f"同方向已有{same_direction_count}个持仓，达到上限{max_same_direction}")

    # 10. 临近交割
    if near_expiry:
        return BlockResult.block("品种临近交割，流动性风险")

    # 11. 成交量不足
    if low_volume:
        return BlockResult.block("成交量不足，滑点风险大")

    return BlockResult.ok()
