"""Lightweight A-share hot-pick scanner — thin wrapper around unified engine.

This module is kept for backward compatibility. All logic lives in engine.py.
"""

from __future__ import annotations

import logging
from typing import Any

from .common import ScanConfig, safe_float
from .engine import ScanResult
from .engine import run as _engine_run

logger = logging.getLogger("quanttrader.scanner.lite")

# 向后兼容别名
_safe_float = safe_float


def _fetch_top_100() -> list[dict[str, Any]]:
    """拉取新浪成交额 TOP100（short_term / 旧脚本兼容入口）。"""
    from .engine import fetch_spot_sina

    cfg = ScanConfig(top_n=100)
    rows = fetch_spot_sina(cfg)
    return rows[:100] if rows else []


def run(top_n: int = 12, config: ScanConfig | None = None) -> list[ScanResult]:
    """Scan top stocks — delegates to unified engine.

    Args:
        top_n: Number of candidates to return
        config: Optional config override
    """
    cfg = config or ScanConfig(top_n=top_n, mode="lite")
    cfg.top_n = top_n
    return _engine_run(cfg)


def diff_results(
    prev: list[ScanResult], curr: list[ScanResult]
) -> dict[str, list[ScanResult]]:
    """对比两次扫描结果，返回新增/移除/持续的标的."""
    prev_codes = {p.code for p in prev}
    curr_codes = {p.code for p in curr}
    new_codes = curr_codes - prev_codes
    gone_codes = prev_codes - curr_codes
    return {
        "new": [p for p in curr if p.code in new_codes],
        "gone": [p for p in prev if p.code in gone_codes],
        "staying": [p for p in curr if p.code in prev_codes],
    }
