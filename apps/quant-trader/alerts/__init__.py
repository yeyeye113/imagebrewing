"""告警系统 — 多渠道推送 + 规则引擎 + 去重 + 历史记录。

Quick start:
    from quanttrader.alerts import AlertManager, AlertLevel

    mgr = AlertManager.from_yaml("config.yaml")
    mgr.send("交易信号", "买入 600519 @ 1800", level=AlertLevel.INFO, event_type="trade")

Supported channels:
    - 企业微信机器人 (webhook)
    - 钉钉机器人 (webhook)
    - Telegram Bot
    - SMTP 邮件
    - Server酱 (微信推送)
    - Bark (iOS 推送)
"""

from quanttrader.alerts.manager import AlertManager
from quanttrader.alerts.rules import AlertLevel, AlertRule, RuleEngine
from quanttrader.alerts.templates import render, render_named

__all__ = ["AlertLevel", "AlertManager", "AlertRule", "RuleEngine", "render", "render_named"]
