"""Shared trading engine — used by both daemon and trader modules.

Avoids duplicating the core tick logic: data fetch → LLM decision →
risk checks → execution → journal. Both the interactive AutoTrader
and the headless TradingDaemon inherit from this.
"""

from __future__ import annotations

import csv
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields
from pathlib import Path

import pandas as pd

from ..ai.llm import LLMConfig, ask_llm
from ..broker.base import get_broker
from ..config import Config
from ..data.base import BarRequest, get_feed
from .position_sizing import SizingConfig
from .risk import RiskConfig

# ── Journal dataclasses ──────────────────────────────────────────────────


@dataclass
class TradeEntry:
    """One complete round-trip trade."""

    symbol: str
    entered_at: str
    exited_at: str
    entry_price: float
    exit_price: float
    qty: float
    notional: float
    pnl: float
    pnl_pct: float
    exit_reason: str
    llm_confidence: float
    llm_reason: str
    total_fees: float


@dataclass
class DecisionRecord:
    """Log every LLM decision."""

    ts: str
    symbol: str
    price: float
    signal: int
    label: str
    confidence: float
    reason: str
    equity: float
    position: float
    action: str
    market_open: bool = True


@dataclass
class DailyLimits:
    """Circuit breaker for a single trading session."""

    max_loss: float = 0.03
    max_gain: float = 0.10
    max_consecutive_losses: int = 3
    cooldown_minutes: int = 30
    max_trades_per_day: int = 20

    @classmethod
    def from_config(cls, cfg: dict | None) -> DailyLimits:
        if cfg is None:
            return cls()
        fnames = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in cfg.items() if k in fnames})


# ── Engine ───────────────────────────────────────────────────────────────


class TradingEngine:
    """Core trading logic: data → LLM → risk → broker → journal.

    Stateless per tick — all mutable state is on the caller (daemon / trader).
    """

    def __init__(
        self,
        config: Config,
        llm_config: LLMConfig | None = None,
        limits: DailyLimits | None = None,
        journal_dir: str = "",
        news_handler: Callable[[str], str] | None = None,
    ):
        self.cfg = config
        self.symbol = config.symbol
        self.llm = llm_config or LLMConfig(provider="deepseek")
        self.limits = limits or DailyLimits()
        self.risk = RiskConfig(**config.risk)
        self.sizing = SizingConfig(**config.sizing)

        # Broker
        bname = config.broker.get("name", "paper")
        if bname in ("paper", "cn_paper", "cn", "ashare_paper"):
            self.broker = get_broker(bname, cash=config.cash, commission=config.commission, slippage=config.slippage)
        else:
            self.broker = get_broker(
                bname,
                api_key=config.broker.get("api_key", ""),
                api_secret=config.broker.get("api_secret", ""),
                paper=config.broker.get("paper", True),
                allow_live=False,
            )
        self.news_handler = news_handler

        # Journal paths
        self.journal_dir = Path(journal_dir) if journal_dir else Path(".")
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        self.decision_log_path = self.journal_dir / f"decisions_{self.symbol}.csv"
        self.trade_log_path = self.journal_dir / f"trades_{self.symbol}.csv"
        self._init_logs()

    def _init_logs(self) -> None:
        for path, field_defs in [
            (self.trade_log_path, fields(TradeEntry)),
            (self.decision_log_path, fields(DecisionRecord)),
        ]:
            if not path.exists():
                with open(path, "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow([fd.name for fd in field_defs])

    def _append_csv(self, path: Path, row: dict) -> None:
        field_defs = fields(TradeEntry) if "pnl" in row else fields(DecisionRecord)
        names = [fd.name for fd in field_defs]
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([row.get(name, "") for name in names])

    # ── Data ──────────────────────────────────────────────────────────

    def fetch_prices(self) -> pd.DataFrame:
        req = BarRequest(symbol=self.symbol, start=self.cfg.start, end=self.cfg.end, interval=self.cfg.interval)
        feed_kwargs = {}
        if self.cfg.data_source in ("csv", "file"):
            feed_kwargs["path"] = self.cfg.data_path
        try:
            return get_feed(self.cfg.data_source, **feed_kwargs).history(req)
        except Exception:
            if self.cfg.data_source != "synthetic":
                return get_feed("synthetic").history(req)
            raise

    def decide(self, prices: pd.DataFrame, news_text: str = "") -> dict:
        return ask_llm(prices, self.llm.resolve(), news_text)

    def log_decision(self, decision: DecisionRecord) -> None:
        self._append_csv(self.decision_log_path, asdict(decision))

    def log_trade(self, trade: TradeEntry) -> None:
        self._append_csv(self.trade_log_path, asdict(trade))
