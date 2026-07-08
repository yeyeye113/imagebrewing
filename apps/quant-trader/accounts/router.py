from __future__ import annotations

"""Trade router — dispatch orders to the correct account(s).

Provides a unified entry point that:
  1. Resolves which account(s) should execute an order (by ID, strategy,
     symbol assignment, or explicit routing rules).
  2. Runs per-account risk checks before execution.
  3. Executes via the underlying broker.
  4. Returns a ``RouteResult`` with execution details.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..broker.base import Order, OrderStatus, norm_side, norm_type
from .account import AccountStatus
from .manager import AccountManager

logger = logging.getLogger(__name__)


@dataclass
class RouteResult:
    """Result of routing an order through the multi-account system."""

    account_id: str
    order: Order | None = None
    routed: bool = False
    rejected: bool = False
    reject_reason: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "routed": self.routed,
            "rejected": self.rejected,
            "reject_reason": self.reject_reason,
            "order": self.order.to_dict() if self.order else None,
            "timestamp": self.timestamp,
        }


class AccountRouter:
    """Unified trading router over all registered accounts.

    Usage::

        router = AccountRouter(manager)
        result = router.route("main", symbol="600519", side="buy", notional=50_000)
    """

    def __init__(self, manager: AccountManager):
        self._mgr = manager
        self._route_log: list[RouteResult] = []

    # --------------------------------------------------------- main entry
    def route(
        self,
        account_id: str,
        *,
        symbol: str,
        side: str,
        qty: float | None = None,
        notional: float | None = None,
        order_type: str = "market",
        limit_price: float | None = None,
        note: str = "",
    ) -> RouteResult:
        """Route an order to a specific account.

        Steps:
          1. Resolve account.
          2. Check account is tradeable (active status).
          3. Run risk check.
          4. Submit order via broker.
          5. Return ``RouteResult``.
        """
        profile = self._mgr.get(account_id)
        if profile is None:
            result = RouteResult(
                account_id=account_id, rejected=True, reject_reason=f"account {account_id!r} not found"
            )
            self._route_log.append(result)
            return result

        if profile.status != AccountStatus.ACTIVE:
            result = RouteResult(
                account_id=account_id, rejected=True, reject_reason=f"account status is {profile.status.value}"
            )
            self._route_log.append(result)
            return result

        # Per-account risk gate
        risk_violation = profile.check_risk()
        if risk_violation:
            profile.pause(reason=risk_violation)
            result = RouteResult(account_id=account_id, rejected=True, reject_reason=f"risk: {risk_violation}")
            self._route_log.append(result)
            logger.warning("order rejected for %s: %s", account_id, risk_violation)
            return result

        # Symbol check (optional: if account has a symbol allowlist)
        if profile.config.symbols:
            allowed = set(profile.config.symbols)
            if symbol not in allowed:
                result = RouteResult(
                    account_id=account_id, rejected=True, reject_reason=f"symbol {symbol!r} not in account allowlist"
                )
                self._route_log.append(result)
                return result

        # Execute via broker
        side = norm_side(side)
        note_tag = f"[acct:{account_id}]"
        full_note = f"{note_tag} {note}".strip()

        try:
            order = profile.broker.submit_order(
                symbol=symbol,
                side=side,
                qty=qty,
                notional=notional,
                order_type=order_type,
                limit_price=limit_price,
                note=full_note,
            )
        except Exception as exc:
            order = Order(
                symbol=symbol,
                side=side,
                type=norm_type(order_type),
                qty=qty,
                notional=notional,
                limit_price=limit_price,
                status=OrderStatus.REJECTED.value,
                note=f"{full_note} | broker_error: {exc}",
            )

        result = RouteResult(
            account_id=account_id,
            order=order,
            routed=order.status != OrderStatus.REJECTED.value,
            rejected=order.status == OrderStatus.REJECTED.value,
            reject_reason=order.note if order.status == OrderStatus.REJECTED.value else "",
        )
        self._route_log.append(result)

        logger.info(
            "routed %s %s %s to %s → %s",
            side,
            symbol,
            f"${notional}" if notional else f"qty={qty}",
            account_id,
            order.status,
        )
        return result

    # --------------------------------------------------- convenience
    def buy(self, account_id: str, symbol: str, notional: float, **kw) -> RouteResult:
        return self.route(account_id, symbol=symbol, side="buy", notional=notional, **kw)

    def sell(self, account_id: str, symbol: str, qty: float, **kw) -> RouteResult:
        return self.route(account_id, symbol=symbol, side="sell", qty=qty, **kw)

    def sell_all(self, account_id: str, symbol: str, **kw) -> RouteResult:
        """Liquidate entire position in *symbol* on *account_id*."""
        profile = self._mgr.get(account_id)
        if profile is None:
            return RouteResult(account_id=account_id, rejected=True, reject_reason=f"account {account_id!r} not found")
        pos = profile.broker.get_position(symbol)
        if not pos or pos.qty <= 0:
            return RouteResult(account_id=account_id, rejected=True, reject_reason=f"no position in {symbol!r}")
        return self.route(account_id, symbol=symbol, side="sell", qty=pos.qty, **kw)

    # --------------------------------------------------- multi-account
    def route_to_all(
        self,
        *,
        symbol: str,
        side: str,
        notional: float | None = None,
        qty: float | None = None,
        roles: list[str] | None = None,
        **kw,
    ) -> list[RouteResult]:
        """Broadcast an order to all active accounts (optionally filtered by
        role).  Useful for portfolio-wide rebalancing or risk exits.

        If *notional* is given, it is split equally across target accounts.
        """
        targets = [p for p in self._mgr.list_accounts() if p.status == AccountStatus.ACTIVE]
        if roles:
            role_set = set(roles)
            targets = [p for p in targets if p.role in role_set]

        if not targets:
            return []

        per_notional = (notional / len(targets)) if notional else None

        results: list[RouteResult] = []
        for profile in targets:
            # Skip accounts that don't have this symbol in their allowlist
            if profile.config.symbols and symbol not in profile.config.symbols:
                continue
            r = self.route(
                profile.id,
                symbol=symbol,
                side=side,
                qty=qty,
                notional=per_notional,
                **kw,
            )
            results.append(r)
        return results

    def liquidate_account(self, account_id: str) -> list[RouteResult]:
        """Close all positions on an account (emergency / risk exit)."""
        profile = self._mgr.get(account_id)
        if profile is None:
            return [RouteResult(account_id=account_id, rejected=True, reject_reason="account not found")]
        results: list[RouteResult] = []
        # Sync positions from broker
        profile.sync_state()
        for symbol, pos in profile.state.positions.items():
            if pos.qty > 0:
                results.append(self.sell_all(account_id, symbol))
        if results:
            profile.status = AccountStatus.LIQUIDATING
            logger.info("liquidating account %s (%d positions)", account_id, len(results))
        return results

    # --------------------------------------------------- log
    def get_route_log(self, limit: int = 100) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self._route_log[-limit:][::-1]]
