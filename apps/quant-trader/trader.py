"""AutoTrader: LLM-powered live trading engine with risk guardrails.

Usage:
    # Paper trading (safe, no real money):
    python -m quanttrader.trader --config config.yaml

    # Real money (explicit opt-in):
    python -m quanttrader.trader --config config.yaml --allow-live

Environment:
    DEEPSEEK_API_KEY   — your DeepSeek API key
    QT_ALLOW_LIVE=1    — required gate for real-money orders
"""

from __future__ import annotations

import csv
import json
import os
import signal
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, fields
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from .ai.llm import LLMConfig, ask_llm
from .broker.base import auto_buy_enabled, get_broker
from .config import Config
from .data.base import BarRequest, get_feed
from .engine import DailyLimits, DecisionRecord, TradeEntry
from .engine.position_sizing import SizingConfig, compute_entry_notional
from .engine.risk import PositionRisk, RiskConfig

# ── The engine ────────────────────────────────────────────────────────────


class AutoTrader:
    """Combines LLM brain + risk rules + broker execution into one loop."""

    def __init__(
        self,
        config: Config,
        llm_config: LLMConfig | None = None,
        daily_limits: DailyLimits | None = None,
        journal_dir: str = "",
        allow_live: bool = False,
        news_handler: Callable[[str], str] | None = None,
    ):
        self.cfg = config
        self.symbol = config.symbol
        self.poll_seconds = int(config.broker.get("poll_seconds", 60))

        # LLM brain
        self.llm = llm_config or LLMConfig(provider="deepseek")
        self.llm_calls: list[DecisionRecord] = []

        # Risk + sizing
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
                allow_live=allow_live,
            )
        self.allow_live = allow_live
        self.is_live = getattr(self.broker, "is_live", False)

        # Guardrails
        self.limits = daily_limits or DailyLimits()
        self.start_equity = config.cash
        self.peak_equity = config.cash
        self.day_equity_start = config.cash
        self.consecutive_losses = 0
        self.trade_count_today = 0
        self.halted_until = 0.0  # Unix timestamp, 0 = not halted
        self.halt_reason = ""
        self.halt_history: list[dict] = []

        # Journal
        self.journal_dir = Path(journal_dir) if journal_dir else Path(".")
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        self.trades: list[TradeEntry] = []
        self.trade_log_path = self.journal_dir / f"trades_{self.symbol}.csv"
        self.decision_log_path = self.journal_dir / f"decisions_{self.symbol}.csv"
        self._init_logs()

        # State
        self.pos_risk: PositionRisk | None = None
        self.open_fill: dict = {}
        self.news_handler = news_handler
        self._running = False
        self._current_date: str = ""  # 交易日切换检测 (空 = 尚未进入首个 tick)

    # ── Journal I/O ──────────────────────────────────────────────────

    def _init_logs(self) -> None:
        """Initialize CSV log files with headers if they don't exist."""
        for path, fields_list in [
            (self.trade_log_path, fields(TradeEntry)),
            (self.decision_log_path, fields(DecisionRecord)),
        ]:
            if not path.exists():
                with open(path, "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow([fd.name for fd in fields_list])

    def _append_csv(self, path: Path, row: dict) -> None:
        """Append a row dict to a CSV file."""
        fields_names = [fd.name for fd in (fields(TradeEntry) if "pnl" in row else fields(DecisionRecord))]
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([row.get(name, "") for name in fields_names])

    def _record_decision(self, rec: DecisionRecord) -> None:
        self.llm_calls.append(rec)
        self._append_csv(self.decision_log_path, asdict(rec))

    def _record_trade(self, t: TradeEntry) -> None:
        self.trades.append(t)
        self._append_csv(self.trade_log_path, asdict(t))
        if t.pnl <= 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

    # ── Market data ──────────────────────────────────────────────────

    def _fetch_prices(self) -> pd.DataFrame:
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

    # ── LLM decision ─────────────────────────────────────────────────

    def _ask_ai(self, prices: pd.DataFrame) -> dict:
        news_text = ""
        if self.news_handler:
            try:
                news_text = self.news_handler(self.symbol)
            except Exception:
                pass
        return ask_llm(prices, self.llm, news_text)

    # ── Circuit breakers ─────────────────────────────────────────────

    def _check_circuits(self, equity: float) -> str | None:
        """Return a halt reason if any circuit fires, or None."""
        now = time.time()
        if now < self.halted_until:
            return self.halt_reason

        # Day loss limit
        day_pnl = equity / self.day_equity_start - 1.0
        if day_pnl <= -self.limits.max_loss:
            self._halt(
                "daily_loss_limit", f"日亏损 {day_pnl * 100:.1f}% 触发熔断 ({self.limits.max_loss * 100:.0f}% 上限)"
            )
            return self.halt_reason

        # Day gain limit — consider it a good day, stop
        if day_pnl >= self.limits.max_gain:
            self._halt(
                "daily_gain_limit", f"日盈利 {day_pnl * 100:.1f}% 触发止盈 ({self.limits.max_gain * 100:.0f}% 上限)"
            )
            return self.halt_reason

        # Consecutive losses
        if self.consecutive_losses >= self.limits.max_consecutive_losses:
            self._halt("consecutive_losses", f"连续 {self.consecutive_losses} 笔亏损触发熔断")
            return self.halt_reason

        # Max trades today
        if self.trade_count_today >= self.limits.max_trades_per_day:
            self._halt("max_trades", f"今日已达 {self.limits.max_trades_per_day} 笔交易上限")
            return self.halt_reason

        return None

    def _halt(self, reason: str, msg: str) -> None:
        self.halted_until = time.time() + self.limits.cooldown_minutes * 60
        self.halt_reason = reason
        h = {"ts": datetime.now(UTC).isoformat(), "reason": reason, "msg": msg}
        self.halt_history.append(h)
        self._log(f"🔴 熔断: {msg}", level="CRITICAL")

    # ── Logging ───────────────────────────────────────────────────────

    @staticmethod
    def _log(msg: str, level: str = "INFO") -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        emoji = {"INFO": "📋", "BUY": "🟢", "SELL": "🔴", "HOLD": "⏸️", "WARN": "⚠️", "CRITICAL": "🚨"}.get(level, "📋")
        print(f"{emoji} [{ts}] {msg}", flush=True)

    # ── Main loop ─────────────────────────────────────────────────────

    def run(self) -> None:
        self._running = True
        mode = "LIVE" if self.is_live else "PAPER"
        self._log(
            f"AutoTrader 启动 · {self.symbol} · {mode} · "
            f"{self.llm.resolve().provider}/{self.llm.model} · "
            f"轮询 {self.poll_seconds}s",
            level="INFO",
        )
        self._log(
            f"风控: 止损={self.risk.stop_loss * 100:.0f}% "
            f"移动止盈={self.risk.trailing_stop * 100:.0f}% "
            f"组合熔断={self.risk.max_drawdown * 100:.0f}% "
            f"日上限=±{self.limits.max_loss * 100:.0f}%/+{self.limits.max_gain * 100:.0f}%",
            level="INFO",
        )

        def _handle_shutdown(sig, frame):
            self._log("收到停止信号, 安全退出...", level="WARN")
            self._running = False

        signal.signal(signal.SIGINT, _handle_shutdown)
        signal.signal(signal.SIGTERM, _handle_shutdown)

        while self._running:
            try:
                self._tick()
            except Exception as e:
                self._log(f"循环异常: {e}", level="WARN")
                time.sleep(self.poll_seconds)

    def _tick(self) -> None:
        # 0) Daily reset — new trading day resets counters
        import datetime as _dt

        _today = _dt.date.today().isoformat()
        if self._current_date != _today:
            self._current_date = _today
            self.day_equity_start = self.broker.get_account().equity
            self.trade_count_today = 0
            self.consecutive_losses = 0

        # 1) Fetch data
        prices = self._fetch_prices()
        price = float(prices["close"].iloc[-1])

        # Push price to broker
        if hasattr(self.broker, "set_price"):
            self.broker.set_price(self.symbol, price)

        # 2) Account state
        acct = self.broker.get_account()
        pos = self.broker.get_position(self.symbol)
        equity = acct.equity
        self.peak_equity = max(self.peak_equity, equity)

        # Sync position risk tracker
        if pos is not None and pos.qty > 0 and self.pos_risk is None:
            self.pos_risk = PositionRisk(float(pos.avg_price))
        if pos is None or pos.qty == 0:
            self.pos_risk = None

        # 3) Check circuit breakers first
        halt = self._check_circuits(equity)
        if halt:
            self._log(f"暂停中 [{halt}], 剩余 {max(0, self.halted_until - time.time()):.0f}s", level="INFO")
            time.sleep(self.poll_seconds)
            return

        # 4) Risk-driven exits (stops/trailing) — always first priority
        if self.pos_risk is not None and pos is not None and pos.qty > 0:
            self.pos_risk.update(price)
            reason = self.pos_risk.hit_stop(price, self.risk)
            if reason:
                self.broker.sell_all(self.symbol)
                self._close_trade(pos, price, reason, 0.0, "")
                self.pos_risk = None
                self.trade_count_today += 1
                self._log(f"止损退出 @ ${price:,.2f} 理由={reason}", level="SELL")
                time.sleep(self.poll_seconds)
                return

        # 5) Portfolio drawdown circuit
        if self.risk.max_drawdown and equity <= self.peak_equity * (1 - self.risk.max_drawdown):
            if pos is not None and pos.qty > 0:
                self.broker.sell_all(self.symbol)
                self._close_trade(pos, price, "max_drawdown_halt", 0.0, "")
                self.pos_risk = None
                self.trade_count_today += 1
            self._halt("max_drawdown", f"组合回撤触发熔断 ({self.risk.max_drawdown * 100:.0f}%)")
            self._log("组合熔断退出", level="CRITICAL")
            time.sleep(self.poll_seconds)
            return

        # 6) LLM decision
        decision = self._ask_ai(prices)
        sig = int(decision["signal"])
        confidence = float(decision.get("confidence", 0.0))
        llm_reason = str(decision.get("reason", ""))
        label = {1: "BUY", 0: "HOLD", -1: "SELL"}.get(sig, str(sig))

        # Confidence gate — keyword fallback (0.0) must not trigger trades
        MIN_CONFIDENCE = 0.5
        if confidence < MIN_CONFIDENCE and sig != 0:
            self._log(f"AI信号 {label} 置信度 {confidence:.0%} < {MIN_CONFIDENCE:.0%}, 视为HOLD", level="HOLD")
            sig = 0
            label = "HOLD"

        action = "hold"
        # 7) Execute based on LLM signal
        if sig == 1 and (pos is None or pos.qty == 0) and not auto_buy_enabled():
            # 自动代买已关闭 — 仅记录信号, 不开仓 (设 QT_AUTO_TRADE=1 可恢复)
            action = "AUTO_BUY_DISABLED"
            self._log(
                f"自动代买已关闭, 跳过买入 @ ${price:,.2f} conf={confidence:.0%} (设 QT_AUTO_TRADE=1 可恢复)",
                level="HOLD",
            )
        elif sig == 1 and (pos is None or pos.qty == 0):
            # BUY signal — size position according to risk rules
            pos_val = (pos.qty * price) if pos else 0.0
            vol = None
            if self.sizing.target_volatility > 0:
                from .engine.position_sizing import annualized_vol

                vol = annualized_vol(prices["close"], self.sizing.vol_lookback)
            notional = compute_entry_notional(
                equity,
                acct.cash,
                pos_val,
                self.cfg.order_size,
                self.sizing,
                self.risk,
                volatility=vol,
            )
            if notional > 0:
                self.broker.buy(self.symbol, notional)
                self.open_fill = {"price": price, "notional": notional, "ts": datetime.now(_dt.UTC).isoformat()}
                self.pos_risk = PositionRisk(price) if self.risk.enabled() else None
                action = "BUY"
                self._log(f"AI买入 @ ${price:,.2f} ${notional:,.0f} conf={confidence:.0%}", level="BUY")
            else:
                action = "SKIP_BUY:0size"
                self._log("AI信号买入但仓位计算为0 (已达上限)", level="HOLD")

        elif sig == -1 and pos is not None and pos.qty > 0:
            # SELL signal — only explicit sell, not HOLD
            self.broker.sell_all(self.symbol)
            self._close_trade(pos, price, "signal", confidence, llm_reason)
            self.pos_risk = None
            self.trade_count_today += 1
            action = "SELL"
            self._log(f"AI卖出 @ ${price:,.2f} conf={confidence:.0%}", level="SELL")

        elif sig == 0:
            self._log(f"HOLD @ ${price:,.2f} conf={confidence:.0%} {llm_reason[:80]}", level="HOLD")

        # Record the decision
        self._record_decision(
            DecisionRecord(
                ts=datetime.now(_dt.UTC).isoformat(),
                symbol=self.symbol,
                price=price,
                signal=sig,
                label=label,
                confidence=confidence,
                reason=llm_reason[:200],
                equity=equity,
                position=pos.qty if pos else 0,
                action=action,
            )
        )

        # Status line
        day_pnl = (equity / self.day_equity_start - 1) * 100
        self._log(
            f"权益 ${equity:,.2f} | 日 {day_pnl:+.2f}% | 持仓 {pos.qty if pos else 0} "
            f"| 累计 {len(self.trades)}笔 | 连亏 {self.consecutive_losses}",
            level="INFO",
        )

        time.sleep(self.poll_seconds)

    def _close_trade(self, pos, exit_price: float, reason: str, confidence: float, llm_reason: str) -> None:
        """Record a completed round-trip trade."""
        of = self.open_fill
        if not of:
            return
        entry_price = of["price"]
        qty = pos.qty
        notional = of["notional"]
        # Apply slippage to both entry and exit
        slip = self.cfg.slippage
        actual_entry = entry_price * (1 + slip)  # buy at worse price
        actual_exit = exit_price * (1 - slip)  # sell at worse price
        pnl = (actual_exit - actual_entry) * qty
        fees = notional * self.cfg.commission * 2  # rough both sides
        pnl -= fees
        pnl_pct = pnl / notional if notional else 0
        self._record_trade(
            TradeEntry(
                symbol=self.symbol,
                entered_at=of["ts"],
                exited_at=datetime.now(UTC).isoformat(),
                entry_price=entry_price,
                exit_price=exit_price,
                qty=qty,
                notional=notional,
                pnl=pnl,
                pnl_pct=pnl_pct,
                exit_reason=reason,
                llm_confidence=confidence,
                llm_reason=llm_reason[:120],
                total_fees=fees,
            )
        )
        self.open_fill = {}


# ── CLI entry ────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="AutoTrader: LLM-powered live trading engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m quanttrader.trader                                   # paper trade AAPL with defaults
  python -m quanttrader.trader --config config.yaml              # paper trade from config
  python -m quanttrader.trader --config config.yaml --allow-live # REAL money

Env:
  DEEPSEEK_API_KEY / OPENAI_API_KEY     LLM provider key
  QT_ALLOW_LIVE=1                       gate for real-money orders
  QT_JOURNAL_DIR                        where to save trade logs (default: .)
""",
    )
    parser.add_argument("--config", "-c", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--symbol", help="Override symbol")
    parser.add_argument(
        "--provider", default="deepseek", choices=["deepseek", "gpt", "openai"], help="LLM provider (default: deepseek)"
    )
    parser.add_argument("--model", default="", help="LLM model override")
    parser.add_argument("--allow-live", action="store_true", help="Enable REAL-MONEY orders (requires QT_ALLOW_LIVE=1)")
    parser.add_argument("--poll", type=int, default=0, help="Poll interval in seconds (override config)")
    parser.add_argument("--dry-run", action="store_true", help="Run signals without placing orders")
    parser.add_argument("--once", action="store_true", help="Fire one decision then exit (for cron/AI polling)")

    args = parser.parse_args(argv)

    # Config
    cfg = Config.load(args.config if Path(args.config).exists() else None)
    if args.symbol:
        cfg.symbol = args.symbol
    if args.poll:
        cfg.broker["poll_seconds"] = args.poll

    # LLM
    llm = LLMConfig(provider=args.provider, model=args.model)
    llm.resolve()
    if not llm.api_key:
        print(f"[ERROR] No API key for {llm.provider}. Set DEEPSEEK_API_KEY or OPENAI_API_KEY.", file=sys.stderr)
        return 1

    # Daily limits from config or defaults
    limits = DailyLimits()
    if "daily_limits" in cfg.broker:
        limits = DailyLimits.from_config(cfg.broker["daily_limits"])

    # Journal
    journal_dir = os.environ.get("QT_JOURNAL_DIR", "")

    trader = AutoTrader(
        config=cfg,
        llm_config=llm,
        daily_limits=limits,
        journal_dir=journal_dir or ".",
        allow_live=args.allow_live,
    )

    if args.dry_run:
        trader._log("⚠️ 试运行模式 — 不执行真实下单", level="WARN")

    if args.once:
        # One-shot: fetch, decide, act — same risk controls as continuous loop
        from .engine.position_sizing import annualized_vol, compute_entry_notional

        prices = trader._fetch_prices()
        price = float(prices["close"].iloc[-1])
        decision = trader._ask_ai(prices)
        sig = int(decision["signal"])
        confidence = float(decision.get("confidence", 0.0))
        llm_reason = str(decision.get("reason", ""))
        label = {1: "BUY", 0: "HOLD", -1: "SELL"}.get(sig, str(sig))

        # Confidence gate
        MIN_CONFIDENCE = 0.5
        if confidence < MIN_CONFIDENCE and sig != 0:
            trader._log(f"信号 {label} 置信度 {confidence:.0%} < {MIN_CONFIDENCE:.0%}, 视为HOLD", level="HOLD")
            sig = 0
            label = "HOLD"

        trader._log(f"单次决策: {label} conf={confidence:.0%} {llm_reason[:120]}", level=label)
        print(
            json.dumps(
                {
                    "symbol": cfg.symbol,
                    "price": price,
                    "signal": sig,
                    "label": label,
                    "confidence": confidence,
                    "reason": llm_reason,
                    "provider": decision.get("provider", ""),
                    "model": decision.get("model", ""),
                    "timestamp": datetime.now(UTC).isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        # Execute with proper position sizing
        if not args.dry_run and sig != 0:
            pos = trader.broker.get_position(cfg.symbol)
            acct = trader.broker.get_account()
            if sig == 1 and (pos is None or pos.qty == 0):
                pos_val = 0.0
                vol = None
                if trader.sizing.target_volatility > 0:
                    vol = annualized_vol(prices["close"], trader.sizing.vol_lookback)
                notional = compute_entry_notional(
                    acct.equity,
                    acct.cash,
                    pos_val,
                    cfg.order_size,
                    trader.sizing,
                    trader.risk,
                    volatility=vol,
                )
                if notional > 0 and not auto_buy_enabled():
                    trader._log("自动代买已关闭, 跳过买入 (设 QT_AUTO_TRADE=1 可恢复)", level="HOLD")
                elif notional > 0:
                    trader.broker.buy(cfg.symbol, notional)
                    trader.open_fill = {
                        "price": price,
                        "notional": notional,
                        "ts": datetime.now(UTC).isoformat(),
                    }
                    trader._log(f"执行买入 ${notional:,.0f}", level="BUY")
                else:
                    trader._log("仓位计算为0，跳过买入", level="HOLD")
            elif sig == -1 and pos is not None and pos.qty > 0:
                trader.broker.sell_all(cfg.symbol)
                trader._close_trade(pos, price, "signal_once", confidence, llm_reason)
                trader._log("执行卖出", level="SELL")
        return 0

    # Continuous loop
    trader.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
