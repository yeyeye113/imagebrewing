"""Daemon module - 交易守护进程模块化拆分。

子模块:
- state: DaemonState 持久化状态
- notifier: 通知系统 (WeChat/DingTalk/Telegram)
- clock: 市场时钟函数
- config: DaemonConfig 配置
- daemon: TradingDaemon 主类
"""

from .state import DaemonState
from .notifier import Notifier
from .clock import market_is_open, seconds_until_market, market_label
from .config import DaemonConfig
from .daemon import TradingDaemon

__all__ = [
    "DaemonState",
    "Notifier",
    "market_is_open",
    "seconds_until_market",
    "market_label",
    "DaemonConfig",
    "TradingDaemon",
]
