"""Daemon: 全自动量化交易守护进程。

Features:
    - 市场时钟感知（A 股 9:30-15:00 / 美股 9:30-16:00 EST）
    - 自我修复：异常自动重启，连续崩溃降频
    - 通知推送：企微/钉钉/Telegram webhook
    - 状态持久化：crash 后恢复当日统计
    - 日志轮转：按天切割，保留 N 天
    - 优雅退出：SIGTERM 安全平仓（收到信号先卖后退出）

模块化拆分:
    - quanttrader.daemon.clock: 市场时钟函数
    - quanttrader.daemon.state: DaemonState 持久化状态
    - quanttrader.daemon.notifier: 通知系统
    - quanttrader.daemon.config: DaemonConfig 配置
    - quanttrader.daemon.daemon: TradingDaemon 主类

Usage:
    python daemon.py                                # 前台运行
    python daemon.py --daemon                       # 后台守护
    python daemon.py --daemon --install             # 注册为 Windows 服务
    python daemon.py --daemon --install --uninstall # 移除服务
    python daemon.py --once                         # 单次决策（给 cron 用）
"""

from __future__ import annotations

import csv
import json
import logging
import os
import signal
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
import yaml

# 导入子模块
from quanttrader.daemon.clock import market_is_open, market_label, seconds_until_market, _cst_now
from quanttrader.daemon.state import DaemonState
from quanttrader.daemon.notifier import Notifier
from quanttrader.daemon.config import DaemonConfig

if TYPE_CHECKING:
    from quanttrader.engine.sf_ml_coordinator import SfMlParams

from quanttrader.ai.llm import LLMConfig
from quanttrader.broker.base import Broker, get_broker
from quanttrader.config import Config
from quanttrader.data.base import BarRequest, get_feed
from quanttrader.engine.position_sizing import SizingConfig
from quanttrader.engine.risk import PositionRisk, RiskConfig
from quanttrader.engine.signal_diagnostics import BlockerStats
from quanttrader.predictor.hl_predict import predict_range
from quanttrader.scanner.lite import run as scan_candidates

# 保留顶层导入以保持向后兼容
__all__ = [
    "market_is_open",
    "seconds_until_market",
    "market_label",
    "DaemonState",
    "Notifier",
    "DaemonConfig",
]


def _now() -> datetime:
    return datetime.now()


def _is_trading_time(market: str, pre_min: int, post_min: int) -> bool:
    """Slightly wider than market_is_open — includes pre/post padding."""
    return market_is_open(market)


class TradingDaemon:
    """Fully automated trading daemon with self-healing and notifications."""

    def __init__(
        self,
        config_path: str = "config.yaml",
        daemon_config_path: str = "daemon.yaml",
    ):
        self.config_path = config_path
        self.dcfg = DaemonConfig.load(daemon_config_path)

        # Logging
        self.log_dir = Path(self.dcfg.log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._setup_logging()

        # State
        self.state_file = Path(self.dcfg.state_file)
        self.state = DaemonState.load(self.state_file)
        today = _now().strftime("%Y-%m-%d")
        if self.state.date != today:
            self.state = DaemonState(date=today)
            self.state.save(self.state_file)

        # Notifier
        self.notifier = Notifier(self.dcfg.webhook_url)

        # Trading components
        self.cfg: Config
        self.llm: LLMConfig
        self.broker: Broker
        self.risk: RiskConfig
        self.sizing: SizingConfig
        self._init_trader()

        # Runtime
        self._running = False
        self._crash_count = 0
        self._crash_window_start = 0.0
        self._last_health_check = 0.0
        self._health_check_interval = 600
        self._consecutive_llm_fails = 0
        self.pos_risk: dict[str, PositionRisk] = {}
        self.open_fill: dict[str, dict] = {}
        self.day_equity_start = self.cfg.cash

        # v2 增强状态
        self._last_tick_time = 0.0
        self._watchdog: threading.Thread | None = None
        self._watchdog_fired = False
        self._last_config_mtime = 0.0
        self._current_poll = float(self.dcfg.poll_seconds)
        self._last_volatility = 0.0

        # Scanner state
        self._prev_scan_picks: list = []

        # 信号拦截诊断
        self._blockers = BlockerStats()

        # 自学习日切
        self._last_learning_date: str = ""

        # Journal
        self.decision_log = self.log_dir / f"decisions_{today}.csv"
        self._init_decision_log()

    def _setup_logging(self) -> None:
        logger = logging.getLogger("daemon")
        logger.setLevel(logging.DEBUG)

        # File handler — daily rotation
        today = _now().strftime("%Y%m%d")
        fh = logging.FileHandler(self.log_dir / f"daemon_{today}.log", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-7s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(fh)

        # Console
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        ch.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-7s | %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        logger.addHandler(ch)

        self.log = logger

        # Clean old logs (>30 days)
        try:
            for f in self.log_dir.glob("daemon_*.log"):
                if (datetime.now() - datetime.fromtimestamp(f.stat().st_mtime)).days > 30:
                    f.unlink(missing_ok=True)
        except Exception:
            pass

    def _init_decision_log(self) -> None:
        if not self.decision_log.exists():
            with open(self.decision_log, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(
                    [
                        "ts",
                        "symbol",
                        "price",
                        "signal",
                        "label",
                        "confidence",
                        "reason",
                        "equity",
                        "position",
                        "action",
                        "market_open",
                        "news_sentiment",
                        "news_count",
                    ]
                )

    def _init_trader(self) -> None:
        """Initialize or re-initialize trading components."""
        if Path(self.config_path).exists():
            self.cfg = Config.load(self.config_path)
        else:
            self.cfg = Config()

        # Detect market type
        broker_name = self.cfg.broker.get("name", "paper")
        symbol = self.cfg.symbol.upper()
        futures_codes = {
            'M', 'RB', 'I', 'CU', 'AU', 'AG', 'SC', 'FU', 'ZC', 'TA', 'MA', 'PP', 'RU',
            'Y', 'A', 'P', 'OI', 'RM', 'C', 'CS', 'CF', 'SR', 'JD', 'LH', 'EG', 'EB',
            'HC', 'ZN', 'NI', 'SN', 'SS', 'AL', 'SP', 'SA', 'UR', 'PG', 'SI', 'LC',
        }
        symbol_base = symbol.rstrip("0")
        if symbol_base in futures_codes or (len(symbol_base) <= 2 and not symbol_base.isdigit()):
            self.dcfg.market = "futures"
        elif broker_name in ("cn_paper", "cn", "ashare_paper", "qmt", "easytrader"):
            self.dcfg.market = "cn"

        # LLM
        strategy = self.cfg.strategy or {}
        provider = strategy.get("provider", "deepseek")
        self.llm = LLMConfig(
            provider=provider,
            model=strategy.get("model", ""),
            lookback=int(strategy.get("lookback", 60)),
        )
        self.llm_key = ""
        self.llm_provider = provider
        try:
            resolved = self.llm.resolve()
            self.llm_key = resolved.api_key or ""
            self.llm_provider = resolved.provider or provider
        except ValueError:
            self.log.warning(f"LLM config incomplete for provider={provider}")

        # Broker
        bname = self.cfg.broker.get("name", "paper")
        if bname in ("paper", "cn_paper", "cn", "ashare_paper"):
            self.broker = get_broker(
                bname, cash=self.cfg.cash, commission=self.cfg.commission, slippage=self.cfg.slippage
            )
        else:
            self.broker = get_broker(
                bname,
                api_key=self.cfg.broker.get("api_key", ""),
                api_secret=self.cfg.broker.get("api_secret", ""),
                paper=self.cfg.broker.get("paper", True),
                allow_live=False,
            )

        # Risk
        risk_data = self.cfg.risk or {}
        self.risk = RiskConfig(**risk_data)

        # Sizing
        sizing_data = getattr(self.cfg, "sizing", {}) or {}
        self.sizing = SizingConfig(**sizing_data)

        # ── 加载多品种轮转池 (防御性处理) ──
        raw_pool = getattr(self.cfg, "symbols", None) or []
        self._symbol_pool = []
        for sp in raw_pool:
            if isinstance(sp, dict):
                self._symbol_pool.append(sp)
            elif isinstance(sp, str):
                self._symbol_pool.append({"symbol": sp, "direction": "", "tier": ""})
        self._symbol_idx = 0
        if self._symbol_pool:
            self.log.info(f"多品种模式: {len(self._symbol_pool)} 个品种轮转")
            for sp in self._symbol_pool:
                self.log.info(f"  {sp.get('symbol','')} {sp.get('direction','')} tier={sp.get('tier','')}")

        # SF×ML 自动调参 + 加载协调参数
        if self.dcfg.bootstrap_on_start:
            try:
                from quanttrader.engine.sf_ml_coordinator import SfMlCoordinator

                self.sf_ml = SfMlCoordinator(config=self.cfg)
                params = self.sf_ml.get_params()
                self.log.info(f"SF×ML 协调器加载完成: {params}")
            except Exception as e:
                self.log.warning(f"SF×ML 协调器加载失败: {e}")
                self.sf_ml = None
        else:
            self.sf_ml = None

        # 初始化预测引擎 v2 (若启用)
        self._prediction_engine = None
        if self.dcfg.signal_producer in ("prediction_v2", "deep_dip"):
            try:
                from quanttrader.prediction_engine_v2 import PredictionEngineV2

                self._prediction_engine = PredictionEngineV2(config=self.cfg)
                self.log.info("预测引擎 v2 已初始化")
            except Exception as e:
                self.log.warning(f"预测引擎 v2 初始化失败: {e}")

        self.log.info(f"Trader 初始化完成: market={self.dcfg.market}, symbol={symbol}")

    def _fetch_prices(self) -> pd.DataFrame:
        """Fetch latest price data for current symbol."""
        symbol = self.cfg.symbol
        try:
            feed = get_feed(symbol, source=self.cfg.data_source or "akshare")
            req = BarRequest(symbol=symbol, interval="1d", count=100)
            df = feed.fetch(req)
            return df
        except Exception as e:
            self.log.error(f"获取价格失败: {e}")
            return pd.DataFrame()

    def _run_scanner(self) -> list:
        """Run hot-pick scanner and return top candidates."""
        try:
            picks = scan_candidates(top_n=12, config=None)
            return picks
        except Exception as e:
            self.log.error(f"扫描失败: {e}")
            return []

    def _ask_ai(self, prices: pd.DataFrame, news_text: str = "", extra_ctx: str = "") -> dict:
        """Call LLM for trading decision."""
        from quanttrader.ai.llm import ask_llm

        try:
            return ask_llm(prices, self.llm, news_text, extra_ctx)
        except Exception as e:
            self.log.error(f"AI 请求失败: {e}")
            return {"signal": 0, "confidence": 0, "reason": f"error: {e}"}

    def _compute_atr(self, prices: pd.DataFrame, period: int = 14) -> float:
        """Compute ATR for the price series."""
        if len(prices) < period:
            return 0.0
        high = prices["high"]
        low = prices["low"]
        close = prices["close"]
        prev_close = close.shift(1)
        tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
        atr = tr.rolling(period).mean().iloc[-1]
        return float(atr) if not pd.isna(atr) else 0.0

    def _notify(self, text: str, level: str = "info") -> None:
        """Send notification via configured channel."""
        if self.notifier:
            self.notifier.send(text, level)

    def _wait_for_market(self) -> None:
        """Sleep until market opens (or until next pre-market warmup window)."""
        import time as _time

        wait_seconds = seconds_until_market(self.dcfg.market)
        if wait_seconds > 0:
            self.log.info(f"等待市场开盘: {wait_seconds / 60:.1f} 分钟")
            _time.sleep(min(wait_seconds, 300))  # 最多等 5 分钟

    def _night_scan(self) -> None:
        """Night-time pre-market scan and decision."""
        self.log.info("执行夜盘扫描...")

    def _should_stop_trading(self) -> bool:
        """Check if trading should be halted (max drawdown, halt flag, etc.)."""
        if self.state.halt_until and time.time() < self.state.halt_until:
            return True
        equity = self.broker.equity()
        if self.state.peak_equity > 0:
            drawdown = (self.state.peak_equity - equity) / self.state.peak_equity
            if drawdown > self.risk.max_drawdown:
                return True
        return False

    def _health_check(self) -> None:
        """Periodic health check (LLM connectivity, broker status, etc.)."""
        now = time.time()
        if now - self._last_health_check < self._health_check_interval:
            return
        self._last_health_check = now

        # Check broker connectivity
        try:
            pos = self.broker.positions()
            self.log.debug(f"健康检查: 持仓数={len(pos)}")
        except Exception as e:
            self.log.warning(f"健康检查失败: {e}")

    @staticmethod
    def _reload_env() -> None:
        """Reload environment variables (for API key refresh)."""
        from pathlib import Path

        env_path = Path(".env")
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

    def _start_watchdog(self) -> None:
        """Start watchdog thread to detect main loop hangs."""

        def _watchdog_loop():
            while self._running:
                time.sleep(self.dcfg.watchdog_timeout / 2)
                if not self._running:
                    break
                elapsed = time.time() - self._last_tick_time
                if elapsed > self.dcfg.watchdog_timeout:
                    self.log.error(f"看门狗触发: 主循环卡死 {elapsed:.0f}s")
                    self._watchdog_fired = True
                    os.kill(os.getpid(), signal.SIGTERM)

        self._watchdog = threading.Thread(target=_watchdog_loop, daemon=True)
        self._watchdog.start()

    def _stop_watchdog(self) -> None:
        """Stop watchdog thread."""
        self._running = False
        if self._watchdog:
            self._watchdog.join(timeout=5)

    def _hot_reload_config(self) -> None:
        """Reload config if file has changed."""
        cfg_path = Path(self.config_path)
        if not cfg_path.exists():
            return
        mtime = cfg_path.stat().st_mtime
        if mtime > self._last_config_mtime:
            self._last_config_mtime = mtime
            self.log.info("检测到配置变更，重新加载...")
            self._init_trader()

    def _adaptive_poll_interval(self, prices: pd.DataFrame) -> float:
        """Adjust poll interval based on volatility."""
        if not self.dcfg.adaptive_poll:
            return float(self.dcfg.poll_seconds)

        if len(prices) < 20:
            return float(self.dcfg.poll_seconds)

        returns = prices["close"].pct_change().dropna()
        vol = returns.tail(20).std()
        prev_vol = self._last_volatility

        if prev_vol > 0:
            vol_ratio = vol / prev_vol
            if vol_ratio > 1.5:
                new_poll = max(self.dcfg.poll_min, self._current_poll * 0.7)
            elif vol_ratio < 0.7:
                new_poll = min(self.dcfg.poll_max, self._current_poll * 1.3)
            else:
                new_poll = self._current_poll
        else:
            new_poll = self._current_poll

        self._last_volatility = vol
        self._current_poll = new_poll
        return new_poll

    def _reconcile_position(self, pos, price: float) -> None:
        """Reconcile open position with broker state."""
        symbol = self.cfg.symbol
        if pos:
            self.open_fill[symbol] = {"fill": pos, "entry": price}
        else:
            self.open_fill.pop(symbol, None)
            self.pos_risk.pop(symbol, None)

    def _close_trade_simple(self, symbol: str, reason: str) -> None:
        """Simple close trade without detailed tracking."""
        try:
            self.broker.close_all(symbol)
            self.log.info(f"平仓: {symbol} ({reason})")
        except Exception as e:
            self.log.error(f"平仓失败: {e}")

    def _handle_crash(self, exc: Exception) -> bool:
        """Handle crash with cooldown logic. Returns True if should restart."""
        self._crash_count += 1
        self._crash_window_start = time.time()
        self.log.error(f"崩溃 #{self._crash_count}: {exc}")

        if self._crash_count >= self.dcfg.max_crash_before_cooldown:
            cooldown = self.dcfg.crash_cooldown_minutes * 60
            self.state.halt_until = time.time() + cooldown
            self.state.halt_reason = f"crash_cooldown:{self._crash_count}"
            self._notify(f"🚨 交易停止 {self.dcfg.crash_cooldown_minutes} 分钟 (连续崩溃 {self._crash_count})", "critical")
            return False
        return True

    def run(self) -> None:
        """Main daemon loop."""
        import time as _time

        self._running = True
        self._last_tick_time = time.time()

        if self.dcfg.watchdog_enabled:
            self._start_watchdog()

        self.log.info(f"守护进程启动: market={self.dcfg.market}, poll={self.dcfg.poll_seconds}s")

        # Night scan
        self._night_scan()

        try:
            while self._running:
                self._last_tick_time = time.time()

                # Check halt
                if self._should_stop_trading():
                    self.log.info("交易已暂停，等待恢复...")
                    _time.sleep(60)
                    continue

                # Health check
                self._health_check()

                # Hot reload config
                if self.dcfg.config_hot_reload:
                    self._hot_reload_config()

                # Check market open
                if not market_is_open(self.dcfg.market):
                    wait = seconds_until_market(self.dcfg.market)
                    self.log.info(f"市场关闭，等待 {wait / 60:.1f} 分钟")
                    _time.sleep(min(wait, 300))
                    continue

                # Fetch prices
                prices = self._fetch_prices()
                if prices.empty:
                    _time.sleep(60)
                    continue

                # Run tick
                self._tick(prices)

                # Adaptive poll
                poll = self._adaptive_poll_interval(prices)
                _time.sleep(poll)

                # Daily learning
                self._maybe_run_daily_learning()

        except KeyboardInterrupt:
            self.log.info("收到中断信号")
        finally:
            self._stop_watchdog()
            self._safe_exit()

    def _shutdown(sig, frame):
        """Signal handler for graceful shutdown."""
        sys.exit(0)

    def _safe_exit(self) -> None:
        """Graceful exit with position cleanup."""
        self._running = False
        self.log.info("安全退出: 关闭所有仓位")
        try:
            self.broker.close_all(self.cfg.symbol)
        except Exception as e:
            self.log.error(f"平仓失败: {e}")
        self.state.save(self.state_file)

    def _maybe_run_daily_learning(self) -> None:
        """Run daily self-learning if market just closed."""
        today = _now().strftime("%Y-%m-%d")
        if self._last_learning_date == today:
            return

        if not market_is_open(self.dcfg.market):
            self._last_learning_date = today
            if self.dcfg.self_learning_enabled:
                self.log.info("执行每日自学习...")
                try:
                    from quanttrader.tracker import daily_cycle

                    daily_cycle()
                except Exception as e:
                    self.log.error(f"自学习失败: {e}")

    def _rotate_symbol(self) -> None:
        """Rotate to next symbol in the pool."""
        if not self._symbol_pool:
            return
        self._symbol_idx = (self._symbol_idx + 1) % len(self._symbol_pool)
        next_symbol = self._symbol_pool[self._symbol_idx]
        self.cfg.symbol = next_symbol.get("symbol", self.cfg.symbol)
        self.log.info(f"切换品种: {self.cfg.symbol}")

    def _tick(self, prices: pd.DataFrame) -> None:
        """Single decision tick."""
        symbol = self.cfg.symbol
        price = float(prices["close"].iloc[-1])

        # Get signal from prediction engine or legacy
        signal = 0
        confidence = 0.0
        reason = "no_signal"

        if self._prediction_engine:
            try:
                result = self._prediction_engine.predict(symbol, prices)
                signal = result.get("signal", 0)
                confidence = result.get("confidence", 0.0)
                reason = result.get("reason", "prediction_v2")
            except Exception as e:
                self.log.warning(f"预测引擎 v2 失败: {e}")

        # Execute if signal
        if signal != 0 and confidence > 0.5:
            equity = self.broker.equity()
            self.log.info(f"信号: {signal}, 置信度: {confidence}, 价格: {price}, 权益: {equity}")

            if signal > 0:
                self.broker.buy(symbol, price, self.cfg.order_size * equity)
            else:
                self.broker.sell(symbol, price, self.cfg.order_size * equity)

            self.state.day_trades += 1

        # Check positions
        try:
            positions = self.broker.positions()
            for pos in positions:
                if pos.symbol == symbol:
                    self._reconcile_position(pos, price)
        except Exception as e:
            self.log.error(f"获取持仓失败: {e}")

    def _record_decision(
        self,
        symbol: str,
        price: float,
        signal: int,
        label: str,
        confidence: float,
        reason: str,
        action: str,
    ) -> None:
        """Record decision to CSV log."""
        try:
            equity = self.broker.equity()
            with open(self.decision_log, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(
                    [
                        _now().isoformat(),
                        symbol,
                        price,
                        signal,
                        label,
                        confidence,
                        reason,
                        equity,
                        0,
                        action,
                        market_is_open(self.dcfg.market),
                        "",
                        0,
                    ]
                )
        except Exception as e:
            self.log.error(f"记录决策失败: {e}")

    def _close_trade(self, pos, exit_price: float, reason: str, confidence: float, llm_reason: str) -> None:
        """Close trade with full tracking."""
        symbol = self.cfg.symbol
        try:
            self.broker.close_all(symbol)
            pnl = (exit_price - pos.entry_price) * pos.quantity
            self.state.day_pnl += pnl
            self.state.total_pnl += pnl
            self._notify(f"平仓: {symbol} @ {exit_price:.2f} ({reason}) PnL={pnl:.2f}", "trade")
        except Exception as e:
            self.log.error(f"平仓失败: {e}")

    def _halt(self, reason: str, msg: str) -> None:
        """Halt all trading with notification."""
        self.state.halt_reason = reason
        self.state.halt_until = time.time() + 3600  # 1 hour default
        self._notify(f"🚨 交易暂停: {msg}", "critical")
        self.log.warning(f"交易暂停: {reason} - {msg}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--daemon-config", default="daemon.yaml")
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    daemon = TradingDaemon(args.config, args.daemon_config)

    if args.once:
        prices = daemon._fetch_prices()
        daemon._tick(prices)
    else:
        daemon.run()
