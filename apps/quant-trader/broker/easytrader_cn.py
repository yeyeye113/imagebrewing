from __future__ import annotations

from .base import Account, Broker, Position


class EasytraderBroker(Broker):
    """A-share live broker via `easytrader` (automates a brokerage client).

    SKELETON — wire this to your environment before real use.

    easytrader drives the desktop trading client (银河/华泰/同花顺 etc.) or a
    connected server. It is unofficial: behaviour depends on your broker and
    client version, and it can break on UI updates. Test with tiny size first.

    Setup (see https://github.com/shidenggui/easytrader):
        pip install easytrader
        # prepare account.json with your credentials, configure the client

    This adapter maps the generic Broker interface onto easytrader so the rest
    of quant-trader (engine, strategies, API) never changes.
    """

    def __init__(self, broker_type: str = "ht", config_path: str = "account.json", price_source: str = "akshare"):
        try:
            import easytrader
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "easytrader is not installed. `pip install easytrader`. "
                "Note: it automates a real brokerage client and is unofficial — "
                "use at your own risk and test with minimal size."
            ) from exc

        import easytrader

        self._user = easytrader.use(broker_type)
        self._user.prepare(config_path)
        self._price_source = price_source

    # ------------------------------------------------------------------ data
    def last_price(self, symbol: str) -> float:
        from ..data.akshare_cn import normalize_cn_symbol
        from ..data.base import BarRequest, get_feed

        df = get_feed(self._price_source).history(
            BarRequest(symbol=normalize_cn_symbol(symbol), start="2024-01-01", end="2100-01-01")
        )
        return float(df["close"].iloc[-1])

    # --------------------------------------------------------------- account
    def get_account(self) -> Account:
        bal = self._user.balance
        # easytrader returns broker-specific dicts; adapt the keys you need.
        cash = float(bal[0].get("可用金额", bal[0].get("资金余额", 0.0))) if bal else 0.0
        equity = float(bal[0].get("总资产", cash)) if bal else cash
        return Account(cash=cash, equity=equity)

    def get_position(self, symbol: str) -> Position | None:
        from ..data.akshare_cn import normalize_cn_symbol

        code = normalize_cn_symbol(symbol)
        for p in self._user.position or []:
            if str(p.get("证券代码", "")).endswith(code):
                qty = float(p.get("股票余额", p.get("参考持股", 0)))
                avg = float(p.get("成本价", p.get("参考成本价", 0)))
                return Position(symbol, qty, avg)
        return None

    # ------------------------------------------------------------- execution
    def buy(self, symbol: str, notional: float) -> None:
        from ..data.akshare_cn import normalize_cn_symbol

        code = normalize_cn_symbol(symbol)
        price = self.last_price(symbol)
        # A-share whole-lot: round notional down to 100-share lots.
        lots = int((notional / price) // 100)
        if lots <= 0:
            return
        self._user.buy(code, price=price, amount=lots * 100)

    def sell_all(self, symbol: str) -> None:
        from ..data.akshare_cn import normalize_cn_symbol

        pos = self.get_position(symbol)
        if not pos or pos.qty <= 0:
            return
        code = normalize_cn_symbol(symbol)
        self._user.sell(code, price=self.last_price(symbol), amount=int(pos.qty))
