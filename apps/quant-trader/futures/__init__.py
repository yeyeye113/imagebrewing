"""期货辅助交易提示系统 — futures trading assistant.

提供：
  - 国内期货主力合约行情（akshare 实时）
  - 期货专用风控（杠杆/保证金/爆仓/逐日盯市）
  - 合约到期提醒
  - 期货扫描器（波动率/持仓量/资金流向）
  - LLM 期货决策辅助（多空双向+夜盘感知）
  - 与 daemon 集成的盯市循环

用法:
  python -m quanttrader.futures                   # CLI 扫描
  python -m quanttrader.futures --serve           # 看板
  python -m quanttrader.futures --watch  # 盯市守护
"""

from __future__ import annotations

__version__ = "0.1.0"

from .advisor import FuturesAdvisor, advise_futures
from .contracts import (
    DOMINANT_CONTRACTS,
    FUTURES_CONTRACTS,
    MARKET_HOURS,
    NightSession,
    contract_info,
    contract_months,
    dominant_contract,
    is_trading_now,
    margin_required,
    next_expiry,
    seconds_to_next_session,
    session_label,
    trading_session,
)
from .scanner_v2 import scan_futures
from .strategy import futures_llm_decision

__all__ = [
    "DOMINANT_CONTRACTS",
    "FUTURES_CONTRACTS",
    "MARKET_HOURS",
    "FuturesAdvisor",
    "NightSession",
    "advise_futures",
    "contract_info",
    "contract_months",
    "dominant_contract",
    "futures_llm_decision",
    "is_trading_now",
    "margin_required",
    "next_expiry",
    "scan_futures",
    "seconds_to_next_session",
    "session_label",
    "trading_session",
]
