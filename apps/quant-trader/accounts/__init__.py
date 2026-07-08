from __future__ import annotations

"""Multi-account management module.

Provides account registration, isolation (capital/positions/risk per account),
unified trading interface, cross-account fund transfer, per-account risk,
per-account strategy binding, monitoring, and per-account logging.
"""

from .account import (
    AccountConfig,
    AccountProfile,
    AccountRole,
    AccountState,
    AccountStatus,
)
from .manager import AccountManager
from .monitor import AccountMonitor, AlertLevel, MonitorEvent
from .router import AccountRouter, RouteResult

__all__ = [
    "AccountConfig",
    "AccountManager",
    "AccountMonitor",
    "AccountProfile",
    "AccountRole",
    "AccountRouter",
    "AccountState",
    "AccountStatus",
    "AlertLevel",
    "MonitorEvent",
    "RouteResult",
]
