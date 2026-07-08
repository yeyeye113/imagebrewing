from __future__ import annotations

"""Account manager — registry, lifecycle, and cross-account operations.

Central point for registering / unregistering accounts, loading account
configs from YAML, syncing states, transferring funds, and querying
aggregate portfolio stats.
"""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from ..broker.base import (
    Broker,
    get_broker,
)
from .account import (
    AccountConfig,
    AccountProfile,
    AccountState,
    AccountStatus,
)

logger = logging.getLogger(__name__)


class AccountManager:
    """Manage a set of ``AccountProfile`` instances.

    Typically one per process.  The daemon creates it once; the API serves
    its data; the router dispatches orders through it.
    """

    def __init__(self) -> None:
        self._accounts: dict[str, AccountProfile] = {}
        self._transfer_log: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ CRUD
    def register(self, config: AccountConfig, broker: Broker | None = None) -> AccountProfile:
        """Create and register a new account.

        If *broker* is ``None``, one is instantiated from ``config.broker``
        via the standard ``get_broker()`` factory.
        """
        if config.id in self._accounts:
            raise ValueError(f"Account {config.id!r} already registered")

        if broker is None:
            broker = get_broker(config.broker, **config.broker_kwargs)

        profile = AccountProfile(config, broker)
        self._accounts[config.id] = profile
        logger.info(
            "registered account %s (broker=%s, role=%s, cash=%.0f)", config.id, config.broker, config.role, config.cash
        )
        return profile

    def unregister(self, account_id: str, *, force: bool = False) -> None:
        """Remove an account.  Refuses if the account still has positions,
        unless ``force=True``."""
        profile = self.get(account_id)
        if profile is None:
            raise KeyError(f"Account {account_id!r} not found")
        if not force and profile.state.position_count > 0:
            raise RuntimeError(
                f"Account {account_id!r} still has {profile.state.position_count} "
                f"open position(s). Close them first, or pass force=True."
            )
        profile.close()
        del self._accounts[account_id]
        logger.info("unregistered account %s", account_id)

    def get(self, account_id: str) -> AccountProfile | None:
        return self._accounts.get(account_id)

    def list_accounts(self, *, include_closed: bool = False) -> list[AccountProfile]:
        accts = list(self._accounts.values())
        if not include_closed:
            accts = [a for a in accts if a.status != AccountStatus.CLOSED]
        return accts

    def count(self) -> int:
        return len(self._accounts)

    # --------------------------------------------------------- bulk load/save
    def load_from_config(self, config_path: str) -> int:
        """Load accounts from a YAML config file.

        Expected structure::

            accounts:
              - id: main
                broker: cn_paper
                role: main
                cash: 500_000
                strategy: {name: sma_cross, fast: 20, slow: 50}
                risk: {stop_loss: 0.05, max_drawdown: 0.15}
                symbols: [000001, 600519]
                broker_kwargs: {}
                enabled: true
              - id: alpaca_sim
                broker: alpaca
                role: satellite
                ...

        Returns the number of accounts registered.
        """
        p = Path(config_path)
        if not p.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        accounts_cfg = data.get("accounts", [])
        if not accounts_cfg:
            logger.warning("no 'accounts' section found in %s", config_path)
            return 0

        known_fields = {f for f in AccountConfig.__dataclass_fields__}
        count = 0
        for entry in accounts_cfg:
            filtered = {k: v for k, v in entry.items() if k in known_fields}
            cfg = AccountConfig(**filtered)
            if not cfg.id:
                logger.warning("skipping account entry with no 'id'")
                continue
            if cfg.id in self._accounts:
                logger.info("account %s already registered, skipping", cfg.id)
                continue
            self.register(cfg)
            count += 1

        logger.info("loaded %d account(s) from %s", count, config_path)
        return count

    # -------------------------------------------------------- state sync
    def sync_all(self) -> dict[str, AccountState]:
        """Sync every active account's state from its broker.  Returns a
        dict of ``{account_id: AccountState}``."""
        results: dict[str, AccountState] = {}
        for aid, profile in self._accounts.items():
            if profile.status == AccountStatus.CLOSED:
                continue
            results[aid] = profile.sync_state()
        return results

    # ---------------------------------------------------- cross-account fund
    def transfer(self, from_id: str, to_id: str, amount: float, *, note: str = "") -> dict[str, Any]:
        """Transfer funds between two accounts.

        Only works between paper/simulated accounts (both brokers must have
        ``is_live == False``).  For live accounts, this logs the request but
        does *not* move real money — the user must do that manually.

        Returns a transfer receipt dict.
        """
        if amount <= 0:
            raise ValueError("transfer amount must be positive")
        src = self.get(from_id)
        dst = self.get(to_id)
        if src is None:
            raise KeyError(f"Source account {from_id!r} not found")
        if dst is None:
            raise KeyError(f"Destination account {to_id!r} not found")
        if from_id == to_id:
            raise ValueError("cannot transfer to the same account")

        receipt: dict[str, Any] = {
            "from": from_id,
            "to": to_id,
            "amount": amount,
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
            "note": note,
            "executed": False,
        }

        # Simulated: move cash directly
        if not src.is_live and not dst.is_live:
            # 非实盘分支必为 PaperBroker 系, 才有可直改的 cash 属性 (鸭子类型)
            src_broker: Any = src.broker
            dst_broker: Any = dst.broker
            if src_broker.cash < amount:
                raise ValueError(f"insufficient cash in {from_id}: {src_broker.cash:.2f} < {amount:.2f}")
            src_broker.cash -= amount
            dst_broker.cash += amount
            receipt["executed"] = True
            logger.info("transfer %.2f from %s to %s (simulated)", amount, from_id, to_id)
        else:
            # Live: just log the instruction, don't move money.
            logger.warning(
                "cross-account transfer involving live account(s) — NOT executed automatically. Manual action required."
            )
            receipt["executed"] = False
            receipt["warning"] = "manual transfer required for live accounts"

        self._transfer_log.append(receipt)
        return receipt

    def get_transfer_log(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._transfer_log[-limit:][::-1]

    # ---------------------------------------------------- aggregate stats
    def portfolio_summary(self) -> dict[str, Any]:
        """Aggregate stats across all active accounts."""
        total_equity = 0.0
        total_cash = 0.0
        total_pnl = 0.0
        total_trades = 0
        by_role: dict[str, float] = {}
        by_status: dict[str, int] = {}

        for profile in self._accounts.values():
            if profile.status == AccountStatus.CLOSED:
                continue
            s = profile.state
            total_equity += s.equity
            total_cash += s.cash
            total_pnl += s.total_pnl
            total_trades += s.total_trades
            by_role[profile.role] = by_role.get(profile.role, 0) + s.equity
            by_status[profile.status.value] = by_status.get(profile.status.value, 0) + 1

        return {
            "account_count": len([a for a in self._accounts.values() if a.status != AccountStatus.CLOSED]),
            "total_equity": round(total_equity, 2),
            "total_cash": round(total_cash, 2),
            "total_pnl": round(total_pnl, 2),
            "total_trades": total_trades,
            "by_role": by_role,
            "by_status": by_status,
        }

    def snapshot_all(self) -> list[dict[str, Any]]:
        """Return serialisable snapshots of all accounts (for API / dashboard)."""
        return [p.to_dict() for p in self._accounts.values() if p.status != AccountStatus.CLOSED]
