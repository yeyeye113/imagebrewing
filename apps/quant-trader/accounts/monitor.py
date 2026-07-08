from __future__ import annotations

"""Account monitor — health checks, alerting, and logging.

Runs periodic checks on every registered account:
  - Equity / drawdown alerts
  - Position concentration warnings
  - Stale-state detection (broker sync failures)
  - Per-account structured logging to ``logs/accounts/{id}.log``
"""

import enum
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .account import AccountProfile, AccountStatus
from .manager import AccountManager

logger = logging.getLogger(__name__)

# Default log directory
_LOG_DIR = Path(os.environ.get("QT_ACCOUNT_LOG_DIR", "logs/accounts"))


class AlertLevel(str, enum.Enum):
    INFO = "info"
    WARN = "warn"
    CRITICAL = "critical"


@dataclass
class MonitorEvent:
    """One monitoring event / alert."""

    account_id: str
    level: AlertLevel
    category: str  # "drawdown" | "exposure" | "stale" | "risk" | "pnl"
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "level": self.level.value,
            "category": self.category,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp,
        }


class AccountMonitor:
    """Periodic monitor that checks all accounts and emits alerts.

    Usage::

        monitor = AccountMonitor(manager)
        events = monitor.check_all()   # call from daemon heartbeat
        for e in events:
            print(e.message)
    """

    def __init__(
        self,
        manager: AccountManager,
        *,
        log_dir: str | Path | None = None,
        drawdown_warn: float = 0.10,  # 10% drawdown → warn
        drawdown_crit: float = 0.20,  # 20% drawdown → critical
        exposure_warn: float = 0.80,  # 80% exposure → warn
        stale_seconds: int = 300,  # no sync for 5 min → stale
    ):
        self._mgr = manager
        self._log_dir = Path(log_dir) if log_dir else _LOG_DIR
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self.drawdown_warn = drawdown_warn
        self.drawdown_crit = drawdown_crit
        self.exposure_warn = exposure_warn
        self.stale_seconds = stale_seconds
        self._events: list[MonitorEvent] = []
        self._loggers: dict[str, logging.Logger] = {}

    # ---------------------------------------------------------------- check
    def check_all(self) -> list[MonitorEvent]:
        """Run all checks on every active account.  Returns any new events."""
        new_events: list[MonitorEvent] = []
        for profile in self._mgr.list_accounts():
            if profile.status == AccountStatus.CLOSED:
                continue
            new_events.extend(self._check_account(profile))
        self._events.extend(new_events)

        # Write to per-account logs
        for ev in new_events:
            self._write_log(ev)

        return new_events

    def _check_account(self, profile: AccountProfile) -> list[MonitorEvent]:
        events: list[MonitorEvent] = []
        s = profile.state
        aid = profile.id

        # 1. Drawdown check
        dd = s.drawdown_pct
        if dd >= self.drawdown_crit:
            events.append(
                MonitorEvent(
                    account_id=aid,
                    level=AlertLevel.CRITICAL,
                    category="drawdown",
                    message=f"drawdown {dd:.1%} >= {self.drawdown_crit:.1%} (critical)",
                    details={"drawdown_pct": dd, "peak_equity": s.peak_equity, "equity": s.equity},
                )
            )
        elif dd >= self.drawdown_warn:
            events.append(
                MonitorEvent(
                    account_id=aid,
                    level=AlertLevel.WARN,
                    category="drawdown",
                    message=f"drawdown {dd:.1%} >= {self.drawdown_warn:.1%} (warning)",
                    details={"drawdown_pct": dd, "peak_equity": s.peak_equity, "equity": s.equity},
                )
            )

        # 2. Exposure check
        exp_pct = s.exposure_pct
        if exp_pct >= self.exposure_warn:
            events.append(
                MonitorEvent(
                    account_id=aid,
                    level=AlertLevel.WARN,
                    category="exposure",
                    message=f"exposure {exp_pct:.1%} >= {self.exposure_warn:.1%}",
                    details={"exposure_pct": exp_pct, "exposure": s.exposure, "equity": s.equity},
                )
            )

        # 3. Stale state detection
        if s.last_updated:
            try:
                last = datetime.fromisoformat(s.last_updated)
                age = (datetime.now(UTC) - last).total_seconds()
                if age > self.stale_seconds:
                    events.append(
                        MonitorEvent(
                            account_id=aid,
                            level=AlertLevel.WARN,
                            category="stale",
                            message=f"state not updated for {int(age)}s (>{self.stale_seconds}s)",
                            details={"age_seconds": age},
                        )
                    )
            except (ValueError, TypeError):
                pass

        # 4. Account paused by risk
        if profile.status == AccountStatus.PAUSED:
            events.append(
                MonitorEvent(
                    account_id=aid,
                    level=AlertLevel.CRITICAL,
                    category="risk",
                    message="account is PAUSED (risk trigger or manual)",
                    details={},
                )
            )

        # 5. Live account warning (informational)
        if profile.is_live:
            events.append(
                MonitorEvent(
                    account_id=aid,
                    level=AlertLevel.INFO,
                    category="info",
                    message="live broker attached — real money at risk",
                    details={"broker": profile.broker_name},
                )
            )

        return events

    # --------------------------------------------------------------- log
    def _get_account_logger(self, account_id: str) -> logging.Logger:
        if account_id in self._loggers:
            return self._loggers[account_id]
        acct_logger = logging.getLogger(f"quanttrader.accounts.{account_id}.monitor")
        acct_logger.setLevel(logging.DEBUG)
        log_path = self._log_dir / f"{account_id}.log"
        if not any(
            isinstance(h, logging.FileHandler) and h.baseFilename == str(log_path) for h in acct_logger.handlers
        ):
            fh = logging.FileHandler(str(log_path), encoding="utf-8")
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(
                logging.Formatter(
                    "%(asctime)s | %(levelname)-8s | %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            acct_logger.addHandler(fh)
        self._loggers[account_id] = acct_logger
        return acct_logger

    def _write_log(self, event: MonitorEvent) -> None:
        acct_logger = self._get_account_logger(event.account_id)
        level_map = {
            AlertLevel.INFO: logging.INFO,
            AlertLevel.WARN: logging.WARNING,
            AlertLevel.CRITICAL: logging.CRITICAL,
        }
        lvl = level_map.get(event.level, logging.INFO)
        acct_logger.log(
            lvl, "[%s] %s | %s", event.category, event.message, json.dumps(event.details, ensure_ascii=False)
        )

    # --------------------------------------------------------------- query
    def get_events(
        self, *, account_id: str | None = None, level: AlertLevel | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        events = self._events
        if account_id:
            events = [e for e in events if e.account_id == account_id]
        if level:
            events = [e for e in events if e.level == level]
        return [e.to_dict() for e in events[-limit:][::-1]]

    def get_health(self) -> dict[str, Any]:
        """One-shot health summary of all accounts."""
        health: dict[str, Any] = {}
        for profile in self._mgr.list_accounts():
            s = profile.state
            health[profile.id] = {
                "status": profile.status.value,
                "broker": profile.broker_name,
                "role": profile.role,
                "equity": round(s.equity, 2),
                "drawdown_pct": round(s.drawdown_pct * 100, 2),
                "exposure_pct": round(s.exposure_pct * 100, 2),
                "positions": s.position_count,
                "win_rate": round(s.win_rate * 100, 1),
                "is_live": profile.is_live,
            }
        return health
