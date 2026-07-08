from __future__ import annotations

import abc
import enum
import itertools
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import cast

_log = logging.getLogger("quanttrader.broker")


@dataclass
class Account:
    cash: float
    equity: float


@dataclass
class Position:
    symbol: str
    qty: float
    avg_price: float


class OrderSide(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, enum.Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, enum.Enum):
    PENDING = "pending"  # accepted, waiting for a (limit) fill
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"  # e.g. no price, no cash, T+1 block


_ORDER_SEQ = itertools.count(1)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def norm_side(side) -> str:
    """Normalize a side (enum or string) to 'buy'/'sell'."""
    if isinstance(side, OrderSide):
        return side.value
    return str(side).lower()


def norm_type(order_type) -> str:
    """Normalize an order type (enum or string) to 'market'/'limit'."""
    if isinstance(order_type, OrderType):
        return order_type.value
    return str(order_type).lower()


@dataclass
class Order:
    """A single order and its lifecycle state."""

    symbol: str
    side: str  # "buy" | "sell"
    type: str = "market"  # "market" | "limit"
    qty: float | None = None  # share quantity (sell, or buy-by-qty)
    notional: float | None = None  # dollar amount (buy-by-notional)
    limit_price: float | None = None
    id: str = ""
    status: str = "pending"
    created_at: str = field(default_factory=_now_iso)
    filled_at: str = ""
    filled_qty: float = 0.0
    filled_price: float = 0.0
    fees: float = 0.0
    note: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = f"ord-{next(_ORDER_SEQ)}-{int(time.time() * 1000) % 100000}"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "side": self.side,
            "type": self.type,
            "qty": self.qty,
            "notional": self.notional,
            "limit_price": self.limit_price,
            "status": self.status,
            "created_at": self.created_at,
            "filled_at": self.filled_at,
            "filled_qty": round(self.filled_qty, 6),
            "filled_price": round(self.filled_price, 6),
            "fees": round(self.fees, 4),
            "note": self.note,
        }


class Broker(abc.ABC):
    """Execution interface. Swap PaperBroker <-> AlpacaBroker without changing
    the trading loop."""

    is_live: bool = False  # True when a fill moves *real* money

    @abc.abstractmethod
    def get_account(self) -> Account: ...

    @abc.abstractmethod
    def get_position(self, symbol: str) -> Position | None: ...

    @abc.abstractmethod
    def last_price(self, symbol: str) -> float: ...

    @abc.abstractmethod
    def buy(self, symbol: str, notional: float) -> None:
        """Buy approximately ``notional`` dollars of ``symbol``."""

    @abc.abstractmethod
    def sell_all(self, symbol: str) -> None:
        """Liquidate the entire position in ``symbol``."""

    # ---- Order management (default impls; override for richer behaviour) ----
    def submit_order(
        self,
        symbol: str,
        side: str,
        qty: float | None = None,
        notional: float | None = None,
        order_type: str = "market",
        limit_price: float | None = None,
        note: str = "",
    ) -> Order:
        """Submit an order. Default maps onto buy()/sell_all() (market only)."""
        side = norm_side(side)
        order = Order(
            symbol=symbol,
            side=side,
            type=norm_type(order_type),
            qty=qty,
            notional=notional,
            limit_price=limit_price,
            note=note,
        )
        if side == OrderSide.BUY.value:
            amount = notional
            if amount is None and qty is not None and qty > 0:
                # Convert qty → notional using last known price
                price = self.last_price(symbol)
                if price and price > 0:
                    amount = qty * price
            self.buy(symbol, amount or 0.0)
        else:
            self.sell_all(symbol)
        order.status = OrderStatus.FILLED.value
        order.filled_at = _now_iso()
        return order

    def sell(self, symbol: str, qty: float) -> None:
        """Partial sell. Default falls back to liquidating the whole position."""
        self.sell_all(symbol)

    def list_orders(self, status: str | None = None, limit: int = 100) -> list[Order]:
        orders = list(getattr(self, "_orders", []))
        if status:
            orders = [o for o in orders if o.status == status]
        return orders[-limit:][::-1]

    def get_order(self, order_id: str) -> Order | None:
        orders: list[Order] = list(getattr(self, "_orders", []))
        for o in orders:
            if o.id == order_id:
                return o
        return None

    def cancel_order(self, order_id: str) -> bool:
        order = self.get_order(order_id)
        if order is not None and order.status == OrderStatus.PENDING.value:
            order.status = OrderStatus.CANCELED.value
            return True
        return False


# ── 自动代买闸门 ────────────────────────────────────────────────────────────
# 需求(2026-07): 量化系统目前只做扫描/分析/预测/建议, 不需要自动代买。
# 默认关闭一切「自动开仓买入」, 但放行卖出(风控平仓保护)/查询/回测/分析。
# 恢复自动买入: 设环境变量 QT_AUTO_TRADE=1 (或 true/yes/on)。

_AUTO_TRADE_TRUTHY = {"1", "true", "yes", "on", "y"}


def auto_buy_enabled() -> bool:
    """是否允许自动开仓买入。

    默认 False —— 关闭「自动代买」。仅当环境变量 ``QT_AUTO_TRADE`` 取值为
    {1,true,yes,on,y} 之一时才允许自动/半自动买入下单。卖出(风控平仓)、
    查询、回测、分析不受此开关影响。
    """
    return os.environ.get("QT_AUTO_TRADE", "").strip().lower() in _AUTO_TRADE_TRUTHY


class NoAutoBuyBroker:
    """Broker 包装器 —— 关闭「自动代买」时的统一兜底守卫。

    透传除开仓买入外的一切能力(卖出/查询/撤单/行情推送), 仅把 ``buy`` 与
    ``submit_order(side=buy)`` 变为拒绝(no-op / REJECTED)。因此无论上游
    (trader/daemon/events/cli/api)如何调用, 都无法真实或模拟开仓买入。
    回测走 Portfolio 不经过 broker, 不受影响。设 QT_AUTO_TRADE=1 后
    get_broker 不再包装, 自动买入即恢复。
    """

    __slots__ = ("_inner",)
    _inner: Broker

    def __init__(self, inner: Broker):
        object.__setattr__(self, "_inner", inner)

    def buy(self, symbol: str, notional: float) -> None:
        _log.warning(
            "自动代买已关闭, 跳过买入 %s (notional=%.2f); 设 QT_AUTO_TRADE=1 可恢复",
            symbol,
            notional,
        )

    def submit_order(
        self,
        symbol: str,
        side: str,
        qty: float | None = None,
        notional: float | None = None,
        order_type: str = "market",
        limit_price: float | None = None,
        note: str = "",
    ) -> Order:
        if norm_side(side) == OrderSide.BUY.value:
            _log.warning("自动代买已关闭, 拒绝买入订单 %s; 设 QT_AUTO_TRADE=1 可恢复", symbol)
            order = Order(
                symbol=symbol,
                side=OrderSide.BUY.value,
                type=norm_type(order_type),
                qty=qty,
                notional=notional,
                limit_price=limit_price,
                note=(f"{note} | " if note else "") + "auto_buy_disabled",
            )
            order.status = OrderStatus.REJECTED.value
            return order
        return self._inner.submit_order(
            symbol,
            side,
            qty=qty,
            notional=notional,
            order_type=order_type,
            limit_price=limit_price,
            note=note,
        )

    def __getattr__(self, name: str):
        # buy / submit_order 已在本类显式覆盖; 其余(sell_all/get_account/
        # get_position/last_price/set_price/list_orders/is_live...)全部透传。
        return getattr(self._inner, name)

    def __repr__(self) -> str:
        return f"NoAutoBuyBroker({self._inner!r})"


def _create_broker(name: str, **kwargs) -> Broker:
    if name == "paper":
        from .paper import PaperBroker

        return PaperBroker(**kwargs)
    if name in ("cn_paper", "cn", "ashare_paper"):
        from .cn_paper import CnPaperBroker

        return CnPaperBroker(**kwargs)
    if name == "alpaca":
        from .alpaca import AlpacaBroker

        return AlpacaBroker(**kwargs)
    if name in ("easytrader", "et"):
        from .easytrader_cn import EasytraderBroker

        return EasytraderBroker(**kwargs)
    if name in ("qmt", "minixt", "xtquant"):
        from .qmt_cn import QmtBroker

        return QmtBroker(**kwargs)
    raise ValueError(f"Unknown broker: {name!r}")


def get_broker(name: str, **kwargs) -> Broker:
    name = (name or "paper").lower()
    broker = _create_broker(name, **kwargs)
    # 自动代买闸门: 默认包装拦截开仓买入, 除非显式开启 QT_AUTO_TRADE。
    if not auto_buy_enabled():
        # NoAutoBuyBroker 通过 __getattr__ 透传实现 Broker 协议 (刻意的鸭子类型代理)
        broker = cast(Broker, NoAutoBuyBroker(broker))
    return broker
