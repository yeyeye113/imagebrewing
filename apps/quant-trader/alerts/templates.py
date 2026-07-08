"""告警模板 — 内置模板 + 变量替换 + 自定义模板注册。

每个模板是一段 Jinja-style 的字符串，用 {{var}} 做变量占位。
内置模板覆盖交易信号、风控、系统异常、每日总结四大类。
"""

from __future__ import annotations

import re
from typing import Any

# ── 内置模板 ──────────────────────────────────────────────────────

_TEMPLATES: dict[str, str] = {
    # 交易信号
    "trade_buy": (
        "🟢 买入信号\n"
        "标的: {{symbol}}\n"
        "价格: {{price}}\n"
        "金额: {{notional}}\n"
        "置信度: {{confidence}}\n"
        "策略: {{strategy}}\n"
        "时间: {{timestamp}}"
    ),
    "trade_sell": (
        "🔴 卖出信号\n"
        "标的: {{symbol}}\n"
        "价格: {{price}}\n"
        "置信度: {{confidence}}\n"
        "持仓天数: {{hold_days}}\n"
        "盈亏: {{pnl}}\n"
        "时间: {{timestamp}}"
    ),
    # 风控
    "risk_stop_loss": (
        "🔴 止损触发\n"
        "标的: {{symbol}}\n"
        "入场: {{entry_price}} → 当前: {{current_price}}\n"
        "跌幅: {{loss_pct}}\n"
        "时间: {{timestamp}}"
    ),
    "risk_circuit_breaker": (
        "🚨 组合熔断\n"
        "回撤: {{drawdown_pct}} (阈值: {{threshold_pct}})\n"
        "峰值: {{peak_equity}} → 当前: {{current_equity}}\n"
        "时间: {{timestamp}}"
    ),
    "risk_trailing_stop": (
        "🟡 移动止损触发\n"
        "标的: {{symbol}}\n"
        "峰值: {{peak_price}} → 当前: {{current_price}}\n"
        "回落: {{drop_pct}}\n"
        "时间: {{timestamp}}"
    ),
    # 系统异常
    "system_crash": ("🚨 系统崩溃\n错误: {{error}}\n崩溃次数: {{crash_count}}\n状态: {{status}}\n时间: {{timestamp}}"),
    "system_restart": ("🔄 系统重启\n原因: {{reason}}\n停机时长: {{downtime}}\n时间: {{timestamp}}"),
    "system_cooldown": (
        "⛔ 连续崩溃冷却\n崩溃次数: {{crash_count}}\n冷却时长: {{cooldown_minutes}} 分钟\n时间: {{timestamp}}"
    ),
    # 每日总结
    "daily_summary": (
        "📊 每日交易总结\n"
        "━━━━━━━━━━━━━━\n"
        "日期: {{date}}\n"
        "标的: {{symbol}}\n"
        "交易笔数: {{day_trades}}\n"
        "盈亏: {{day_pnl}}\n"
        "累计盈亏: {{total_pnl}}\n"
        "命中率: {{win_rate}}\n"
        "持仓: {{position}}\n"
        "━━━━━━━━━━━━━━"
    ),
    # 市场
    "market_open": ("🔔 {{market}}开盘\n标的: {{symbol}}\n策略: {{strategy}}\n时间: {{timestamp}}"),
    "market_close": ("⏹️ {{market}}收盘\n标的: {{symbol}}\n今日交易: {{day_trades}} 笔\n时间: {{timestamp}}"),
    # 扫描
    "scanner_update": ("🔍 选股扫描更新\n候选: {{candidates}}\n变化: {{changes}}\n时间: {{timestamp}}"),
}


# ── 变量替换 ──────────────────────────────────────────────────────

_VAR_RE = re.compile(r"\{\{(\w+)\}\}")


def render(template: str, variables: dict[str, Any]) -> str:
    """将 {{var}} 占位符替换为 variables 中的值。

    未找到的变量保留原始占位符。
    """

    def _replace(m: re.Match) -> str:
        key = m.group(1)
        return str(variables.get(key, m.group(0)))

    return _VAR_RE.sub(_replace, template)


def render_named(name: str, variables: dict[str, Any]) -> str:
    """用内置模板名渲染。"""
    tpl = _TEMPLATES.get(name)
    if tpl is None:
        raise KeyError(f"未知模板: {name!r}。可用: {list(_TEMPLATES)}")
    return render(tpl, variables)


# ── 自定义模板 ────────────────────────────────────────────────────


def register(name: str, template: str) -> None:
    """注册自定义模板，覆盖同名内置模板。"""
    _TEMPLATES[name] = template


def list_templates() -> list[str]:
    """返回所有可用模板名。"""
    return list(_TEMPLATES.keys())


def get_template(name: str) -> str:
    """返回原始模板字符串（未渲染）。"""
    tpl = _TEMPLATES.get(name)
    if tpl is None:
        raise KeyError(f"未知模板: {name!r}")
    return tpl
