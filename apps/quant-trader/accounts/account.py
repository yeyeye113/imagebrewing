from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..broker.base import Broker, Position

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AccountStatus(str, enum.Enum):
    ACTIVE = "active"  # normal trading
    PAUSED = "paused"  # suspended (manual or risk trigger)
    LIQUIDATING = "liquidating"  # force-closing all positions
    CLOSED = "closed"  # permanently shut down


class AccountRole(str, enum.Enum):
    """Account role determines default behaviour and risk appetite."""

    MAIN = "main"  # primary live account
    SATELLITE = "satellite"  # secondary / strategy-dedicated
    PAPER = "paper"  # simulation only
    SCALPER = "scalper"  # high-frequency / short-horizon
    HEDGER = "hedger"  # hedge / arbitrage


# ---------------------------------------------------------------------------
# Per-account config (loaded from YAML)
# ---------------------------------------------------------------------------


@dataclass
class AccountConfig:
    """Immutable configuration for a single account (from config.yaml).

    Example YAML fragment::

        accounts:
          - id: main
            broker: cn_paper
            role: main
            cash: 500_000
            strategy: sma_cross
            risk:
              stop_loss: 0.05
              max_drawdown: 0.15
            symbols: [000001, 600519]
            enabled: true
    """

    id: str = ""
    broker: str = "paper"
    role: str = AccountRole.PAPER.value
    cash: float = 100_000.0
    strategy: dict[str, Any] = field(default_factory=lambda: {"name": "sma_cross"})
    risk: dict[str, float] = field(
        default_factory=lambda: {
            "stop_loss": 0.05,
            "take_profit": 0.0,
            "trailing_stop": 0.0,
            "max_drawdown": 0.20,
            "risk_per_trade": 0.01,
        }
    )
    sizing: dict[str, float] = field(default_factory=dict)
    symbols: list[str] = field(default_factory=list)
    broker_kwargs: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    notes: str = ""


# ---------------------------------------------------------------------------
# Runtime state — mutable, tracked per account
# ---------------------------------------------------------------------------


@dataclass
class AccountState:
    """Live runtime state of one trading account.  Mutable — updated by the
    monitor and the trading loop.

    Maintains its own equity curve, drawdown tracking, and P&L stats so that
    each account can be evaluated independently.
    """

    cash: float = 0.0
    equity: float = 0.0
    peak_equity: float = 0.0
    positions: dict[str, Position] = field(default_factory=dict)
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    max_drawdown_pct: float = 0.0
    last_updated: str = ""

    # -- derived ---------------------------------------------------------------
    @property
    def drawdown_pct(self) -> float:
        """Current drawdown from peak equity (0.05 = 5%)."""
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, (self.peak_equity - self.equity) / self.peak_equity)

    @property
    def win_rate(self) -> float:
        total = self.winning_trades + self.losing_trades
        return self.winning_trades / total if total > 0 else 0.0

    @property
    def position_count(self) -> int:
        return sum(1 for p in self.positions.values() if p.qty > 0)

    @property
    def exposure(self) -> float:
        """Total market value of positions."""
        return sum(p.qty * p.avg_price for p in self.positions.values() if p.qty > 0)

    @property
    def exposure_pct(self) -> float:
        """Exposure as fraction of equity."""
        return self.exposure / self.equity if self.equity > 0 else 0.0

    def snapshot(self) -> dict[str, Any]:
        """Return a serialisable snapshot for monitoring / logging."""
        return {
            "cash": round(self.cash, 2),
            "equity": round(self.equity, 2),
            "peak_equity": round(self.peak_equity, 2),
            "drawdown_pct": round(self.drawdown_pct * 100, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct * 100, 2),
            "positions": self.position_count,
            "exposure": round(self.exposure, 2),
            "exposure_pct": round(self.exposure_pct * 100, 2),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(self.win_rate * 100, 1),
            "total_pnl": round(self.total_pnl, 2),
            "last_updated": self.last_updated,
        }


# ---------------------------------------------------------------------------
# Profile — the live object that wires config + broker + state together
# ---------------------------------------------------------------------------


class AccountProfile:
    """One registered trading account.

    Wraps a ``Broker`` instance with per-account config, state, risk, strategy
    binding, and a dedicated logger.
    """

    def __init__(self, config: AccountConfig, broker: Broker):
        self.id = config.id
        self.config = config
        self.broker = broker
        self.status = AccountStatus.ACTIVE if config.enabled else AccountStatus.PAUSED
        self.state = AccountState(cash=config.cash, equity=config.cash, peak_equity=config.cash)
        self.created_at = datetime.now(UTC).isoformat(timespec="seconds")
        self._log = logging.getLogger(f"quanttrader.accounts.{self.id}")

    # -- convenience -----------------------------------------------------------
    @property
    def role(self) -> str:
        return self.config.role

    @property
    def strategy_name(self) -> str:
        return str(self.config.strategy.get("name", "unknown"))

    @property
    def is_tradeable(self) -> bool:
        return self.status == AccountStatus.ACTIVE

    @property
    def broker_name(self) -> str:
        return self.config.broker

    @property
    def is_live(self) -> bool:
        return self.broker.is_live

    # -- state sync ------------------------------------------------------------
    def sync_state(self) -> AccountState:
        """Pull latest cash/equity/positions from the broker and update
        internal state.  Returns the updated state.
        """
        try:
            acct = self.broker.get_account()
            self.state.cash = acct.cash
            self.state.equity = acct.equity
            if acct.equity > self.state.peak_equity:
                self.state.peak_equity = acct.equity
            dd = self.state.drawdown_pct
            if dd > self.state.max_drawdown_pct:
                self.state.max_drawdown_pct = dd
            self.state.last_updated = datetime.now(UTC).isoformat(timespec="seconds")
        except Exception as exc:
            self._log.warning("sync_state failed for %s: %s", self.id, exc)
        return self.state

    def record_trade(self, pnl: float) -> None:
        """Record a completed trade P&L (called by the trading loop)."""
        self.state.total_trades += 1
        self.state.total_pnl += pnl
        if pnl >= 0:
            self.state.winning_trades += 1
        else:
            self.state.losing_trades += 1

    # -- risk check (called before each order) ---------------------------------
    def check_risk(self) -> str | None:
        """Return a reason string if risk limits are breached, else None.

        Checks:
          1. Max drawdown → auto-pause account
          2. Configured risk thresholds
        """
        risk_cfg = self.config.risk
        max_dd = risk_cfg.get("max_drawdown", 0.0)
        if max_dd and self.state.drawdown_pct >= max_dd:
            return f"max_drawdown_hit ({self.state.drawdown_pct:.1%} >= {max_dd:.1%})"

        stop_loss = risk_cfg.get("stop_loss", 0.0)
        # Per-trade stop loss is enforced at position level, not here.
        # This check is for account-level aggregate loss.
        return None

    def pause(self, reason: str = "") -> None:
        self.status = AccountStatus.PAUSED
        self._log.info("account PAUSED: %s", reason or "manual")

    def resume(self) -> None:
        if self.status == AccountStatus.PAUSED:
            self.status = AccountStatus.ACTIVE
            self._log.info("account RESUMED")

    def close(self) -> None:
        self.status = AccountStatus.CLOSED
        self._log.info("account CLOSED")

    # -- serialisation ---------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "broker": self.broker_name,
            "role": self.role,
            "status": self.status.value,
            "strategy": self.strategy_name,
            "is_live": self.is_live,
            "symbols": self.config.symbols,
            "risk": self.config.risk,
            "created_at": self.created_at,
            "state": self.state.snapshot(),
        }

    def __repr__(self) -> str:
        return (
            f"AccountProfile(id={self.id!r}, broker={self.broker_name!r}, "
            f"role={self.role!r}, status={self.status.value!r})"
        )
