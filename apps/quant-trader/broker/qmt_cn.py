from __future__ import annotations

from .base import Account, Broker, Position


class QmtBroker(Broker):
    """A-share live broker via QMT / miniQMT (`xtquant`).

    SKELETON — requires a broker-provided QMT terminal and quant permissions.

    QMT (迅投) is the most common *official* route for programmatic A-share
    trading. You need:
      * a brokerage account with QMT/miniQMT quant trading enabled,
      * the QMT client running and logged in,
      * the `xtquant` Python package shipped with the terminal.

    Fill in `account_id` and `mini_qmt_path`, then implement the TODOs using the
    `xtquant.xttrader` API. The generic Broker interface keeps the rest of the
    app unchanged when you swap this in.
    """

    def __init__(self, account_id: str, mini_qmt_path: str, price_source: str = "akshare"):
        try:
            from xtquant import xttrader
            from xtquant.xttype import StockAccount
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "xtquant not found. It ships with the QMT/miniQMT terminal from "
                "your broker. Ensure the QMT client is installed, running, and "
                "its python path is importable."
            ) from exc

        from xtquant import xttrader
        from xtquant.xttype import StockAccount

        self._account = StockAccount(account_id)
        self._trader = xttrader.XtQuantTrader(mini_qmt_path, session_id=hash(account_id) % 1_000_000)
        self._trader.start()
        self._trader.connect()
        self._trader.subscribe(self._account)
        self._price_source = price_source

    def last_price(self, symbol: str) -> float:
        # TODO: prefer xtquant.xtdata real-time quote; fall back to data feed.
        from ..data.akshare_cn import normalize_cn_symbol
        from ..data.base import BarRequest, get_feed

        df = get_feed(self._price_source).history(
            BarRequest(symbol=normalize_cn_symbol(symbol), start="2024-01-01", end="2100-01-01")
        )
        return float(df["close"].iloc[-1])

    def get_account(self) -> Account:
        asset = self._trader.query_stock_asset(self._account)
        return Account(cash=float(asset.cash), equity=float(asset.total_asset))

    def get_position(self, symbol: str) -> Position | None:
        from ..data.akshare_cn import normalize_cn_symbol

        code = normalize_cn_symbol(symbol)
        for p in self._trader.query_stock_positions(self._account) or []:
            if str(p.stock_code).startswith(code):
                return Position(symbol, float(p.volume), float(p.avg_price))
        return None

    def buy(self, symbol: str, notional: float) -> None:
        from xtquant import xtconstant

        from ..data.akshare_cn import normalize_cn_symbol

        price = self.last_price(symbol)
        lots = int((notional / price) // 100)
        if lots <= 0:
            return
        self._trader.order_stock(
            self._account,
            normalize_cn_symbol(symbol),
            xtconstant.STOCK_BUY,
            lots * 100,
            xtconstant.FIX_PRICE,
            price,
        )

    def sell_all(self, symbol: str) -> None:
        from xtquant import xtconstant

        from ..data.akshare_cn import normalize_cn_symbol

        pos = self.get_position(symbol)
        if not pos or pos.qty <= 0:
            return
        self._trader.order_stock(
            self._account,
            normalize_cn_symbol(symbol),
            xtconstant.STOCK_SELL,
            int(pos.qty),
            xtconstant.FIX_PRICE,
            self.last_price(symbol),
        )
