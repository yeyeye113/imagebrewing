"""运行模式守卫 — 管理 research/paper/shadow_live/live_guarded/live 模式。

规则:
  research:   只生成信号和报告，不调用 broker 下单
  paper:      只允许 broker.name = paper 或 cn_paper
  shadow_live: 使用真实行情，不下单，记录"如果下单会怎样"
  live_guarded: 可接真实 broker，但策略必须在 allowlist 中
  live:       暂不开放全自动，启动时必须有 unlock 文件

Usage:
    guard = ModeGuard(mode="paper", broker_name="paper")
    guard.validate()  # 抛异常如果模式和 broker 不匹配
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ModeConfig:
    """运行模式配置。"""
    name: str
    can_trade: bool          # 是否允许调用 broker
    broker_allowed: list[str]  # 允许的 broker 名称
    requires_allowlist: bool   # 策略必须在 allowlist 中
    max_position_pct: float   # 最大单笔仓位
    max_total_exposure: float  # 最大总暴露
    min_paper_days: int       # 进入该模式前至少 paper 跑的天数
    requires_unlock: bool     # 是否需要 unlock 文件


# 各模式的配置
MODE_CONFIGS: dict[str, ModeConfig] = {
    "research": ModeConfig(
        name="research",
        can_trade=False,
        broker_allowed=[],
        requires_allowlist=False,
        max_position_pct=0.0,
        max_total_exposure=0.0,
        min_paper_days=0,
        requires_unlock=False,
    ),
    "paper": ModeConfig(
        name="paper",
        can_trade=True,
        broker_allowed=["paper", "cn_paper", "cn"],
        requires_allowlist=False,
        max_position_pct=0.20,
        max_total_exposure=0.50,
        min_paper_days=0,
        requires_unlock=False,
    ),
    "shadow_live": ModeConfig(
        name="shadow_live",
        can_trade=True,  # 下的是模拟单
        broker_allowed=["paper", "cn_paper", "cn"],
        requires_allowlist=True,
        max_position_pct=0.15,
        max_total_exposure=0.40,
        min_paper_days=20,
        requires_unlock=False,
    ),
    "live_guarded": ModeConfig(
        name="live_guarded",
        can_trade=True,
        broker_allowed=["alpaca", "easytrader", "qmt", "xtquant"],
        requires_allowlist=True,
        max_position_pct=0.10,
        max_total_exposure=0.30,
        min_paper_days=30,
        requires_unlock=False,
    ),
    "live": ModeConfig(
        name="live",
        can_trade=True,
        broker_allowed=["alpaca", "easytrader", "qmt", "xtquant", "paper", "cn_paper"],
        requires_allowlist=True,
        max_position_pct=0.10,
        max_total_exposure=0.30,
        min_paper_days=60,
        requires_unlock=True,
    ),
}


class ModeGuard:
    """运行模式守卫。

    负责:
    1. 验证模式和 broker 的兼容性
    2. 验证 unlock 文件 (live 模式)
    3. 根据模式限制仓位和暴露
    4. 策略 allowlist 管理
    """

    def __init__(
        self,
        mode: str = "paper",
        broker_name: str = "paper",
        unlock_dir: str | Path = ".",
        allowlist: list[str] | None = None,
    ):
        if mode not in MODE_CONFIGS:
            raise ValueError(
                f"未知模式: {mode!r}. 可选: {', '.join(sorted(MODE_CONFIGS))}"
            )
        self.mode = mode
        self.broker_name = broker_name
        self.unlock_dir = Path(unlock_dir)
        self.config = MODE_CONFIGS[mode]
        self.allowlist = allowlist or []

    def validate(self) -> None:
        """验证当前配置是否合法。

        Raises:
            RuntimeError: 如果配置不合法
        """
        # 1. Broker 兼容性
        if self.config.can_trade and self.broker_name:
            if self.broker_name not in self.config.broker_allowed:
                raise RuntimeError(
                    f"模式 {self.mode} 不允许使用 broker={self.broker_name!r}. "
                    f"允许的 broker: {self.config.broker_allowed}"
                )

        # 2. Live 模式需要 unlock 文件
        if self.config.requires_unlock:
            unlock_file = self.unlock_dir / ".live_unlock"
            if not unlock_file.exists():
                raise RuntimeError(
                    f"live 模式需要解锁文件 {unlock_file}。"
                    f"请确认你了解实盘风险后创建该文件。"
                )

        # 3. allowlist 检查
        if self.config.requires_allowlist and not self.allowlist:
            raise RuntimeError(
                f"模式 {self.mode} 要求策略在 allowlist 中，但 allowlist 为空"
            )

    def is_trading_allowed(self) -> bool:
        """是否允许调用 broker 下单。"""
        return self.config.can_trade

    def is_strategy_allowed(self, strategy_name: str) -> bool:
        """检查策略是否在 allowlist 中。"""
        if not self.config.requires_allowlist:
            return True
        return strategy_name in self.allowlist

    def get_max_position_pct(self) -> float:
        """获取当前模式允许的最大单笔仓位。"""
        return self.config.max_position_pct

    def get_max_total_exposure(self) -> float:
        """获取当前模式允许的最大总暴露。"""
        return self.config.max_total_exposure

    def get_mode_info(self) -> dict[str, Any]:
        """获取当前模式信息。"""
        return {
            "mode": self.mode,
            "can_trade": self.config.can_trade,
            "broker_allowed": self.config.broker_allowed,
            "requires_allowlist": self.config.requires_allowlist,
            "max_position_pct": self.config.max_position_pct,
            "max_total_exposure": self.config.max_total_exposure,
            "min_paper_days": self.config.min_paper_days,
            "requires_unlock": self.config.requires_unlock,
            "broker_name": self.broker_name,
        }

    def format_status(self) -> str:
        """格式化当前模式状态。"""
        info = self.get_mode_info()
        lines = [
            f"[ModeGuard] 运行模式: {info['mode']}",
            f"  允许交易: {'是' if info['can_trade'] else '否 (仅生成信号)'}",
            f"  Broker: {info['broker_name']}",
            f"  最大单笔仓位: {info['max_position_pct']:.0%}",
            f"  最大总暴露: {info['max_total_exposure']:.0%}",
        ]
        if info["requires_allowlist"]:
            lines.append(f"  策略白名单: {len(self.allowlist)} 个")
        if info["requires_unlock"]:
            unlock_file = self.unlock_dir / ".live_unlock"
            lines.append(f"  Unlock 文件: {'存在' if unlock_file.exists() else '不存在'}")
        return "\n".join(lines)
