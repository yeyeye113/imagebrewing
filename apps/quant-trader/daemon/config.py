"""DaemonConfig 配置模块。"""

from dataclasses import MISSING as _MISSING
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml


@dataclass
class DaemonConfig:
    """Full daemon configuration loaded from daemon.yaml."""

    market: str = "cn"  # cn | us
    poll_seconds: int = 120
    auto_restart: bool = True
    max_crash_before_cooldown: int = 5
    crash_cooldown_minutes: int = 30
    log_dir: str = "logs"
    state_file: str = "daemon_state.json"
    webhook_url: str = ""
    webhook_events: list[str] = field(default_factory=lambda: ["trade", "critical", "daily_summary"])
    pre_market_minutes: int = 5  # warm up N min before market
    post_market_minutes: int = 5  # cool down N min after market
    telegram_chat_id: str = ""
    # ── v2 增强 ──
    watchdog_enabled: bool = True  # 看门狗：主循环卡死自动重启
    watchdog_timeout: int = 300  # 看门狗超时（秒）
    adaptive_poll: bool = True  # 自适应轮询：波动大时加速
    poll_min: int = 30  # 自适应轮询下限（秒）
    poll_max: int = 300  # 自适应轮询上限（秒）
    fallback_providers: list[str] = field(default_factory=list)  # LLM 备用源
    config_hot_reload: bool = True  # 配置热加载
    # 信号诊断 / LLM 否决 / 自学习
    llm_veto_enabled: bool = True  # False: paper 调试时跳过 LLM 强烈反对 → HOLD
    llm_veto_confidence: float = 0.85  # 仅当 LLM 置信度超过此值且反向才否决
    llm_sf_priority_tiers: list[str] = field(
        default_factory=lambda: ["tier1", "tier2"]
    )  # 这些 tier 的 SF 白名单信号免疫 LLM 否决
    signal_diagnostics: bool = True
    diagnostics_log_every: int = 10  # 每 N 个 tick 输出拦截统计摘要
    signal_producer: str = ""  # 空=legacy SymbolFilter; deep_dip | prediction_v2
    auto_tune_on_start: bool = True  # 启动时运行 tracker.auto_tune 更新 strategy_params
    ml_mode: str = ""  # 覆盖 sf_ml.ml_mode; 空=读 strategy_params 自动值
    self_learning_enabled: bool = True  # 每日收盘后跑 tracker.daily_cycle
    bootstrap_on_start: bool = True  # tracker 样本不足时冷启动回填
    ml_retrain_enabled: bool = True  # daily_cycle 内触发 v15 重训

    @classmethod
    def load(cls, path: str = "daemon.yaml") -> "DaemonConfig":
        p = Path(path)
        if p.exists():
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            kwargs: dict[str, Any] = {}
            for f in fields(cls):
                default: Any = f.default
                if default is _MISSING:
                    # field 要么有 default 要么有 default_factory; 双缺省回退 None
                    factory = f.default_factory
                    default = factory() if callable(factory) else None
                kwargs[f.name] = data.get(f.name, default)
            return cls(**kwargs)
        return cls()
