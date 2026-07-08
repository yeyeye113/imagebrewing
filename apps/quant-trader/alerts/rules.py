"""告警规则引擎 — 事件分类 + 自定义阈值规则。

核心概念:
    AlertLevel  — INFO / WARN / CRITICAL
    AlertRule   — 一条自定义阈值规则
    RuleEngine  — 注册规则 + 判定事件是否触发
"""

from __future__ import annotations

import enum
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


class AlertLevel(str, enum.Enum):
    INFO = "INFO"
    WARN = "WARN"
    CRITICAL = "CRITICAL"


# ── 事件类型到默认级别的映射 ────────────────────────────────────

DEFAULT_EVENT_LEVELS: dict[str, AlertLevel] = {
    # 交易
    "trade": AlertLevel.INFO,
    "trade_buy": AlertLevel.INFO,
    "trade_sell": AlertLevel.INFO,
    # 风控
    "risk_stop_loss": AlertLevel.CRITICAL,
    "risk_take_profit": AlertLevel.WARN,
    "risk_trailing_stop": AlertLevel.WARN,
    "risk_circuit_breaker": AlertLevel.CRITICAL,
    "risk": AlertLevel.CRITICAL,
    # 系统
    "system_crash": AlertLevel.CRITICAL,
    "system_restart": AlertLevel.WARN,
    "system_cooldown": AlertLevel.CRITICAL,
    "system": AlertLevel.WARN,
    # 市场
    "market_open": AlertLevel.INFO,
    "market_close": AlertLevel.INFO,
    # 每日
    "daily_summary": AlertLevel.INFO,
    # 扫描
    "scanner_update": AlertLevel.INFO,
}


def default_level(event_type: str) -> AlertLevel:
    """返回事件类型的默认告警级别，未知类型返回 INFO。"""
    return DEFAULT_EVENT_LEVELS.get(event_type, AlertLevel.INFO)


# ── 自定义阈值规则 ──────────────────────────────────────────────


@dataclass
class AlertRule:
    """一条自定义阈值告警规则。

    Attributes:
        name:       规则唯一名称
        event_type: 监听的事件类型
        level:      触发时的告警级别
        condition:  判定函数，接收 (event_data: dict) -> bool
        message:    触发时的消息模板（支持 {{var}} 变量）
        cooldown_minutes: 同规则去重冷却（分钟），0 表示不去重
        enabled:    是否启用
    """

    name: str
    event_type: str
    level: AlertLevel = AlertLevel.WARN
    condition: Callable[[dict[str, Any]], bool] = field(default=lambda _: True)
    message: str = "规则 {{name}} 触发"
    cooldown_minutes: int = 30
    enabled: bool = True


# ── 内置规则 ─────────────────────────────────────────────────────


def _builtin_rules() -> list[AlertRule]:
    """系统内置的阈值告警规则。"""
    return [
        AlertRule(
            name="low_confidence_trade",
            event_type="trade",
            level=AlertLevel.WARN,
            condition=lambda d: float(d.get("confidence", 1.0)) < 0.5,
            message="低置信度交易: {{symbol}} 置信度 {{confidence}} < 50%",
            cooldown_minutes=30,
        ),
        AlertRule(
            name="large_loss",
            event_type="trade_sell",
            level=AlertLevel.WARN,
            condition=lambda d: float(d.get("pnl_pct", 0)) < -0.05,
            message="大额亏损: {{symbol}} 亏损 {{pnl_pct}} 超过 5%",
            cooldown_minutes=60,
        ),
        AlertRule(
            name="consecutive_losses",
            event_type="trade_sell",
            level=AlertLevel.WARN,
            condition=lambda d: int(d.get("consecutive_losses", 0)) >= 3,
            message="连续亏损 {{consecutive_losses}} 次，建议暂停交易",
            cooldown_minutes=120,
        ),
        AlertRule(
            name="high_drawdown_warning",
            event_type="daily_summary",
            level=AlertLevel.WARN,
            condition=lambda d: float(d.get("max_drawdown_today", 0)) > 0.10,
            message="日内回撤 {{max_drawdown_today}} 超过 10% 预警",
            cooldown_minutes=60,
        ),
    ]


# ── 规则引擎 ────────────────────────────────────────────────────


class RuleEngine:
    """管理并评估所有告警规则。"""

    def __init__(self) -> None:
        self.rules: list[AlertRule] = _builtin_rules()

    def add(self, rule: AlertRule) -> None:
        """添加自定义规则（同名覆盖）。"""
        self.rules = [r for r in self.rules if r.name != rule.name]
        self.rules.append(rule)

    def remove(self, name: str) -> bool:
        """移除规则，返回是否成功。"""
        before = len(self.rules)
        self.rules = [r for r in self.rules if r.name != name]
        return len(self.rules) < before

    def evaluate(self, event_type: str, data: dict[str, Any]) -> list[AlertRule]:
        """评估事件，返回所有匹配且触发的规则列表。"""
        triggered: list[AlertRule] = []
        for rule in self.rules:
            if not rule.enabled:
                continue
            if rule.event_type != event_type and rule.event_type != "*":
                continue
            try:
                if rule.condition(data):
                    triggered.append(rule)
            except Exception:
                continue
        return triggered

    def list_rules(self) -> list[dict[str, Any]]:
        """返回所有规则摘要。"""
        return [
            {
                "name": r.name,
                "event_type": r.event_type,
                "level": r.level.value,
                "cooldown_minutes": r.cooldown_minutes,
                "enabled": r.enabled,
                "message": r.message,
            }
            for r in self.rules
        ]
