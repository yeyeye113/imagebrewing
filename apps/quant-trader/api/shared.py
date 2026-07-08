"""Shared mutable state for API routes.

All runtime-editable config (broker, AI endpoints, prediction loggers)
lives here so route modules can import it without circular deps.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from ..broker.base import get_broker
from ..engine.live_risk import LiveRiskMonitor
from ..live_panel import LivePanelTracker
from ..prediction_log import DeviationTracker, PredictionLogger
from ..prediction_service import PredictionDeps
from ..screening_journal import ScreeningJournal
from ..strategy_journal import StrategyJournal


@dataclass
class AppState:
    """Mutable container for all shared runtime state."""

    # Broker
    broker_name: str = "paper"
    broker: Any = None  # lazy-init in create_app
    risk_monitor: Any = None

    # Runtime settings (POST /settings)
    state: dict = field(default_factory=lambda: {
        "cash": 100_000.0,
        "api_key": os.environ.get("QT_BROKER_KEY", ""),
        "api_secret": os.environ.get("QT_BROKER_SECRET", ""),
        "paper": True,
        "allow_live": False,
    })
    ai_cfg: dict = field(default_factory=lambda: {
        "endpoint": os.environ.get("QT_AI_ENDPOINT", ""),
        "api_key": os.environ.get("QT_AI_KEY", ""),
    })
    llm_cfg: dict = field(default_factory=lambda: {
        "provider": os.environ.get("QT_LLM_PROVIDER", "deepseek"),
        "api_key": os.environ.get("QT_LLM_KEY", ""),
        "model": os.environ.get("QT_LLM_MODEL", ""),
    })

    # Prediction loggers
    prediction_logger: Any = None
    deviation_tracker: Any = None
    screening_journal: Any = None
    live_panel: Any = None
    strategy_journal: Any = None
    pred_deps: Any = None

    # Auth
    api_token: str | None = None

    def init_loggers(self) -> None:
        pred_log_dir = os.environ.get("QT_PREDICTION_LOG_DIR", "")
        self.prediction_logger = PredictionLogger(pred_log_dir)
        self.deviation_tracker = DeviationTracker(self.prediction_logger)
        self.screening_journal = ScreeningJournal(pred_log_dir)
        self.live_panel = LivePanelTracker(pred_log_dir)
        self.strategy_journal = StrategyJournal(pred_log_dir)
        self.pred_deps = PredictionDeps(
            prediction_logger=self.prediction_logger,
            deviation_tracker=self.deviation_tracker,
            screening_journal=self.screening_journal,
            live_panel=self.live_panel,
            strategy_journal=self.strategy_journal,
        )

    def init_broker(self) -> None:
        self.broker_name = os.environ.get("QT_BROKER", "paper")
        self.broker = get_broker(self.broker_name, cash=100_000.0)
        self.risk_monitor = LiveRiskMonitor(self.broker)
        self.api_token = os.environ.get("QT_API_TOKEN")
