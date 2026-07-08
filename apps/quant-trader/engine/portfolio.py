"""Portfolio: multi-position cash + holdings ledger for the backtest engine.

Tracks cash, a dictionary of open positions (symbol → shares), and a chronological
fill log. Commission and slippage are applied at every fill.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Fill:
    timestamp: object
    symbol: str
    side: str  # "BUY" or "SELL"
    qty: float
    price: float
    cost: float  # commission + slippage paid


@dataclass
class Portfolio:
    """Tracks cash, multi-symbol positions, and trade history.

    All legacy attribute access paths (`.position`, `.fills`) are preserved so
    the backtester and advisor work without changes.
    """

    cash: float = 100_000.0
    commission: float = 0.0005
    slippage: float = 0.0005
    lot_size: int = 1  # 100 for A-share whole-lot trading
    positions: dict[str, float] = field(default_factory=dict)  # symbol → shares
    fills: list[Fill] = field(default_factory=list)

    # ── Legacy compat ──────────────────────────────────────────────────────
    @property
    def position(self) -> float:
        """Total shares held across all symbols (legacy single-symbol code)."""
        return sum(self.positions.values())

    @position.setter
    def position(self, value: float) -> None:
        """Mutations to .position affect the default (first) symbol."""
        self.positions["__default__"] = value

    def equity(self, prices: dict | float) -> float:
        """Total equity = cash + sum of each position * its price.

        When ``prices`` is a float, treat it as the single-symbol price for
        backwards compatibility.
        """
        if isinstance(prices, (int, float)):
            return self.cash + self.position * float(prices)
        mv = 0.0
        for sym, qty in self.positions.items():
            px = prices.get(sym, 0.0)
            mv += qty * px
        return self.cash + mv

    # ── Core ops ───────────────────────────────────────────────────────────
    def buy(self, timestamp, symbol: str, price: float, cash_to_use: float) -> None:
        if cash_to_use <= 0 or self.cash <= 0:
            return
        cash_to_use = min(cash_to_use, self.cash)
        exec_price = price * (1 + self.slippage)
        gross = cash_to_use / (1 + self.commission)
        qty = gross / exec_price
        if self.lot_size > 1:
            qty = (int(qty) // self.lot_size) * self.lot_size
        if qty <= 0:
            return
        notional = qty * exec_price
        commission_paid = notional * self.commission
        spend = notional + commission_paid
        self.cash -= spend
        self.positions[symbol] = self.positions.get(symbol, 0.0) + qty
        self.fills.append(Fill(timestamp, symbol, "BUY", qty, exec_price, commission_paid))

    def sell_all(self, timestamp, symbol: str, price: float) -> None:
        qty = self.positions.get(symbol, 0.0)
        if qty <= 0:
            return
        exec_price = price * (1 - self.slippage)
        gross = qty * exec_price
        cost = gross * self.commission
        self.cash += gross - cost
        self.fills.append(Fill(timestamp, symbol, "SELL", qty, exec_price, cost))
        self.positions.pop(symbol, None)

    def sell(self, timestamp, symbol: str, price: float, qty: float) -> None:
        held = self.positions.get(symbol, 0.0)
        if held <= 0:
            return
        qty = min(qty, held)
        if qty <= 0:
            return
        exec_price = price * (1 - self.slippage)
        gross = qty * exec_price
        cost = gross * self.commission
        self.cash += gross - cost
        self.fills.append(Fill(timestamp, symbol, "SELL", qty, exec_price, cost))
        remaining = held - qty
        if remaining > 1e-9:
            self.positions[symbol] = remaining
        else:
            self.positions.pop(symbol, None)

    # ── Multi-symbol lookup ────────────────────────────────────────────────
    def position_of(self, symbol: str) -> float:
        return self.positions.get(symbol, 0.0)

    def market_value(self, prices: dict[str, float]) -> float:
        return sum(qty * prices.get(sym, 0.0) for sym, qty in self.positions.items())

    def summary(self) -> dict:
        return {
            "cash": self.cash,
            "n_positions": len(self.positions),
            "positions": dict(self.positions),
            "n_fills": len(self.fills),
        }
