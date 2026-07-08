"""Daemon: 全自动量化交易守护进程。

Features:
    - 市场时钟感知（A 股 9:30-15:00 / 美股 9:30-16:00 EST）
    - 自我修复：异常自动重启，连续崩溃降频
    - 通知推送：企微/钉钉/Telegram webhook
    - 状态持久化：crash 后恢复当日统计
    - 日志轮转：按天切割，保留 N 天
    - 优雅退出：SIGTERM 安全平仓（收到信号先卖后退出）

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
from dataclasses import MISSING as _MISSING
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
import yaml

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

# ═══════════════════════════════════════════════════════════════════════════
# 市场时钟
# ═══════════════════════════════════════════════════════════════════════════


def _now() -> datetime:
    return datetime.now()


def _now_utc() -> datetime:
    return datetime.now(UTC)


# A 股交易时间（北京时间）
ASHARE_OPEN = (9, 30)  # 9:30 CST
ASHARE_CLOSE = (15, 0)  # 15:00 CST
ASHARE_LUNCH = ((11, 30), (13, 0))  # 午休

# 美股交易时间（美东时间 EST，含夏令时简化）
US_OPEN = (9, 30)
US_CLOSE = (16, 0)


def _cst_now() -> datetime:
    """Current China Standard Time (UTC+8)."""
    from datetime import timedelta

    return datetime.now(timezone(timedelta(hours=8)))


def _est_now() -> datetime:
    """Current US Eastern time (approximate — always UTC-5 for simplicity)."""
    from datetime import timedelta

    return datetime.now(timezone(timedelta(hours=-5)))


def market_is_open(market: str) -> bool:
    """Check if the given market is open right now."""
    market = market.lower()
    if market in ("futures",):
        # 期货交易时间: 日盘 9:00-15:00 (含午休), 夜盘 21:00-23:00
        now = _cst_now()
        if now.weekday() >= 5:
            return False
        t = now.hour * 60 + now.minute
        # 日盘: 9:00-11:30, 13:30-15:00
        day1 = 9*60 <= t < 11*60+30
        day2 = 13*60+30 <= t < 15*60
        # 夜盘: 21:00-23:00
        night = 21*60 <= t < 23*60
        return day1 or day2 or night
    if market in ("cn", "a股", "ashare", "cn_paper", "akshare"):
        now = _cst_now()
        if now.weekday() >= 5:
            return False
        t = now.hour * 60 + now.minute
        open_t = ASHARE_OPEN[0] * 60 + ASHARE_OPEN[1]
        close_t = ASHARE_CLOSE[0] * 60 + ASHARE_CLOSE[1]
        lunch_start = ASHARE_LUNCH[0][0] * 60 + ASHARE_LUNCH[0][1]
        lunch_end = ASHARE_LUNCH[1][0] * 60 + ASHARE_LUNCH[1][1]
        if lunch_start <= t < lunch_end:
            return False
        return open_t <= t < close_t
    # US / default
    now = _est_now()
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    return (US_OPEN[0] * 60 + US_OPEN[1]) <= t < (US_CLOSE[0] * 60 + US_CLOSE[1])


def seconds_until_market(market: str) -> float:
    """Seconds until the next market open. Returns 0 if already open."""
    market = market.lower()
    if market_is_open(market):
        return 0.0

    if market in ("cn", "a股", "ashare", "cn_paper", "akshare"):
        now = _cst_now()
        target = now.replace(hour=ASHARE_OPEN[0], minute=ASHARE_OPEN[1], second=0, microsecond=0)
        if now.weekday() >= 5 or now >= target:
            days = (7 - now.weekday()) % 7
            if days == 0:
                days = 1
            target = target + timedelta(days=days)
        return max(0, (target - now).total_seconds())
    # US
    now = _est_now()
    target = now.replace(hour=US_OPEN[0], minute=US_OPEN[1], second=0, microsecond=0)
    if now.weekday() >= 5 or now >= target:
        days = (7 - now.weekday()) % 7
        if days == 0:
            days = 1
        target = target + timedelta(days=days)
    return max(0, (target - now).total_seconds())


def market_label(market: str) -> str:
    m = market.lower()
    if m in ("cn", "a股", "ashare", "cn_paper", "akshare"):
        return "A股"
    if m in ("futures",):
        return "期货"
    return "美股"


# ═══════════════════════════════════════════════════════════════════════════
# 持久化状态
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class DaemonState:
    """JSON-serializable state that survives daemon restarts."""

    date: str = ""  # "2026-06-18"
    day_trades: int = 0
    day_pnl: float = 0.0
    consecutive_losses: int = 0
    peak_equity: float = 0.0
    last_decision_at: str = ""
    halt_until: float = 0.0  # Unix timestamp
    halt_reason: str = ""
    total_trades: int = 0
    total_pnl: float = 0.0
    wins: int = 0  # ✅ 命中追踪
    version: int = 1

    @property
    def win_rate(self) -> float | None:
        if self.total_trades <= 0:
            return None
        return self.wins / self.total_trades

    @classmethod
    def load(cls, path: Path) -> DaemonState:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return cls(**{f.name: data.get(f.name, getattr(cls, f.name)) for f in fields(cls)})
            except Exception:
                pass
        return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════
# 通知系统
# ═══════════════════════════════════════════════════════════════════════════


class Notifier:
    """Send trade alerts via webhook (WeChat Work / DingTalk / Telegram)."""

    def __init__(self, webhook_url: str = "", channel: str = ""):
        self.url = webhook_url.strip()
        self.channel = (channel or self._detect(webhook_url)).lower()

    @staticmethod
    def _detect(url: str) -> str:
        if not url:
            return "log"
        if "qyapi.weixin" in url:
            return "wecom"
        if "dingtalk" in url or "oapi.dingtalk" in url:
            return "dingtalk"
        if "telegram" in url or "t.me" in url:
            return "telegram"
        return "generic"

    def send(self, text: str, level: str = "info") -> bool:
        """Send a notification. Falls back to console log if no webhook."""
        if not self.url:
            logging.getLogger("daemon").info(f"  [通知:{level}] {text}")
            return True
        try:
            if self.channel == "wecom":
                return self._send_wecom(text)
            if self.channel == "dingtalk":
                return self._send_dingtalk(text, level)
            if self.channel == "telegram":
                return self._send_telegram(text)
            return self._send_generic(text)
        except ImportError:
            logging.getLogger("daemon").info(f"  [通知:{level}] {text}")
            return True
        except Exception:
            return False

    def _send_wecom(self, text: str) -> bool:
        import requests

        try:
            resp = requests.post(
                self.url,
                json={
                    "msgtype": "markdown",
                    "markdown": {"content": text},
                },
                timeout=10,
            )
            return bool(resp.ok)
        except Exception:
            return False

    def _send_dingtalk(self, text: str, level: str) -> bool:
        import requests

        prefix = {"critical": "🚨", "trade": "📊", "info": "ℹ️"}.get(level, "")
        try:
            resp = requests.post(
                self.url,
                json={
                    "msgtype": "text",
                    "text": {"content": f"{prefix} {text}"},
                },
                timeout=10,
            )
            return bool(resp.ok)
        except Exception:
            return False

    def _send_telegram(self, text: str) -> bool:
        import requests

        try:
            resp = requests.post(
                self.url,
                json={
                    "text": text,
                    "parse_mode": "Markdown",
                },
                timeout=10,
            )
            return bool(resp.ok)
        except Exception:
            return False

    def _send_generic(self, text: str) -> bool:
        import requests

        try:
            resp = requests.post(self.url, json={"text": text, "level": "info"}, timeout=10)
            return bool(resp.ok)
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════════════════════
# Daemon 核心
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class DaemonConfig:
    """Full daemon configuration loaded from daemon.yaml."""

    market: str = "cn"  # cn | us
    poll_seconds: int = 120
    auto_restart: bool = True
    max_crash_before_cooldown: int = 5
    crash_cooldown_minutes: int = 30
    log_dir: str = "logs"
    state_file: str = "daemon_state.json"
    webhook_url: str = ""
    webhook_events: list[str] = field(default_factory=lambda: ["trade", "critical", "daily_summary"])
    pre_market_minutes: int = 5  # warm up N min before market
    post_market_minutes: int = 5  # cool down N min after market
    telegram_chat_id: str = ""
    # ── v2 增强 ──
    watchdog_enabled: bool = True  # 看门狗：主循环卡死自动重启
    watchdog_timeout: int = 300  # 看门狗超时（秒）
    adaptive_poll: bool = True  # 自适应轮询：波动大时加速
    poll_min: int = 30  # 自适应轮询下限（秒）
    poll_max: int = 300  # 自适应轮询上限（秒）
    fallback_providers: list[str] = field(default_factory=list)  # LLM 备用源
    config_hot_reload: bool = True  # 配置热加载
    # 信号诊断 / LLM 否决 / 自学习
    llm_veto_enabled: bool = True  # False: paper 调试时跳过 LLM 强烈反对 → HOLD
    llm_veto_confidence: float = 0.85  # 仅当 LLM 置信度超过此值且反向才否决 (旧 0.7 过保守)
    llm_sf_priority_tiers: list[str] = field(
        default_factory=lambda: ["tier1", "tier2"]
    )  # 这些 tier 的 SF 白名单信号免疫 LLM 否决
    signal_diagnostics: bool = True
    diagnostics_log_every: int = 10  # 每 N 个 tick 输出拦截统计摘要
    signal_producer: str = ""  # 空=legacy SymbolFilter; deep_dip | prediction_v2
    auto_tune_on_start: bool = True  # 启动时运行 tracker.auto_tune 更新 strategy_params
    ml_mode: str = ""  # 覆盖 sf_ml.ml_mode; 空=读 strategy_params 自动值
    self_learning_enabled: bool = True  # 每日收盘后跑 tracker.daily_cycle
    bootstrap_on_start: bool = True  # tracker 样本不足时冷启动回填
    ml_retrain_enabled: bool = True  # daily_cycle 内触发 v15 重训 (若模型过旧/OOS弱)

    @classmethod
    def load(cls, path: str = "daemon.yaml") -> DaemonConfig:
        p = Path(path)
        if p.exists():
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            kwargs: dict[str, Any] = {}
            for f in fields(cls):
                default: Any = f.default
                if default is _MISSING:
                    # field 要么有 default 要么有 default_factory; 双缺省回退 None
                    factory = f.default_factory
                    default = factory() if callable(factory) else None
                kwargs[f.name] = data.get(f.name, default)
            return cls(**kwargs)
        return cls()


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

        # Trading components — _init_trader 恒定完成赋值, 初始化后非 None
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
        self._last_health_check = 0.0  # 上次巡检时间戳
        self._health_check_interval = 600  # 10 分钟
        self._consecutive_llm_fails = 0  # 连续 LLM 失败计数
        self.pos_risk: dict[str, PositionRisk] = {}  # symbol -> PositionRisk
        self.open_fill: dict[str, dict] = {}  # symbol -> fill info
        self.day_equity_start = self.cfg.cash

        # ── v2 增强状态 ──
        self._last_tick_time = 0.0  # 上次 tick 完成时间（看门狗用）
        self._watchdog: threading.Thread | None = None
        self._watchdog_fired = False
        self._last_config_mtime = 0.0  # config.yaml 上次修改时间（热加载用）
        self._current_poll = float(self.dcfg.poll_seconds)  # 自适应轮询秒数
        self._last_volatility = 0.0  # 上次波动率（自适应用）

        # ── 多品种轮转 (初始化在 _init_trader 里加载) ──
        # self._symbol_pool 和 self._symbol_idx 在 _init_trader 中赋值

        # Scanner state (populated by _run_scanner)
        self._prev_scan_picks: list = []

        # 信号拦截诊断 (定位零成交)
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
        # 期货品种识别: 去掉末尾0后1-2字母代码 = 期货, 6位数字 = A股
        futures_codes = {'M','RB','I','CU','AU','AG','SC','FU','ZC','TA','MA','PP','RU',
                         'Y','A','P','OI','RM','C','CS','CF','SR','JD','LH','EG','EB',
                         'HC','ZN','NI','SN','SS','AL','SP','SA','UR','PG','SI','LC'}
        symbol_base = symbol.rstrip("0")  # SI0 → SI, M0 → M
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

        self.risk = RiskConfig(**self.cfg.risk)
        self.sizing = SizingConfig(**self.cfg.sizing)

        # ── 加载多品种轮转池 ──
        raw_pool = getattr(self.cfg, 'symbols', None) or []
        # 防御性: 确保每个元素是dict而非string
        self._symbol_pool = []
        for sp in raw_pool:
            if isinstance(sp, dict):
                self._symbol_pool.append(sp)
            elif isinstance(sp, str):
                # 字符串格式: "SI0" -> {"symbol": "SI0"}
                self._symbol_pool.append({"symbol": sp, "direction": "", "tier": ""})
        self._symbol_idx = 0
        if self._symbol_pool:
            self.log.info(f"多品种模式: {len(self._symbol_pool)} 个品种轮转")
            for sp in self._symbol_pool:
                self.log.info(f"  {sp.get('symbol','')} {sp.get('direction','')} tier={sp.get('tier','')}")

        # SF×ML 自动调参 + 加载协调参数
        if self.dcfg.bootstrap_on_start:
            try:
                from quanttrader.tracker import bootstrap_self_learning_if_needed
                boot = bootstrap_self_learning_if_needed()
                if boot.get("bootstrapped"):
                    self.log.info(
                        f"自学习冷启动: verified→{boot.get('verified_after')} "
                        f"acc={boot.get('accuracy_after')}"
                    )
            except Exception as e:
                self.log.debug(f"bootstrap跳过: {e}")
        if self.dcfg.auto_tune_on_start:
            try:
                from quanttrader.tracker import auto_tune
                auto_tune()
            except Exception as e:
                self.log.debug(f"auto_tune跳过: {e}")
        self._sf_ml_params: SfMlParams | None
        try:
            from quanttrader.engine.sf_ml_coordinator import load_sf_ml_params
            self._sf_ml_params = load_sf_ml_params()
            if self.dcfg.ml_mode:
                self._sf_ml_params.ml_mode = self.dcfg.ml_mode.strip().lower()
            self.log.info(
                f"SF×ML: mode={self._sf_ml_params.ml_mode} "
                f"use_v15={self._sf_ml_params.use_v15} "
                f"veto≥{self._sf_ml_params.ml_veto_confidence:.0%}"
            )
        except Exception as e:
            self.log.debug(f"sf_ml params skip: {e}")
            self._sf_ml_params = None

    def _fetch_prices(self) -> pd.DataFrame:

        req = BarRequest(
            symbol=self.cfg.symbol,
            start=self.cfg.start,
            end=self.cfg.end,
            interval=self.cfg.interval,
        )
        feed_kwargs = {}
        if self.cfg.data_source in ("csv", "file"):
            feed_kwargs["path"] = self.cfg.data_path
        try:
            return get_feed(self.cfg.data_source, **feed_kwargs).history(req)
        except Exception:
            # 期货品种fallback: 尝试sina_futures
            try:
                from quanttrader.data.sina_futures import get_history
                df = get_history(self.cfg.symbol, days=120)
                if df is not None and len(df) > 0:
                    return df
            except Exception:
                pass
            if self.cfg.data_source != "synthetic":
                return get_feed("synthetic").history(req)
            raise

    def _run_scanner(self) -> list:
        """① 选股扫描."""
        self.log.info("① 选股扫描...")
        picks = []
        try:
            picks = scan_candidates(top_n=12)
            self.log.info(f"   扫描完成: {len(picks)} 候选")
            for p in picks[:6]:
                self.log.info(
                    f"   {p.code} {p.name} score={p.score} → {p.action}"
                )
            # Store for diff
            self._prev_scan_picks = picks
        except Exception as e:
            self.log.warning(f"选股扫描失败 (不中断循环): {e}")
        return picks

    def _ask_ai(self, prices: pd.DataFrame, news_text: str = "", extra_ctx: str = "") -> dict:
        """STUB: simplified mode — direction comes from SymbolFilter, not LLM."""
        return {"signal": 0, "confidence": 0.0, "reason": "simplified mode"}

    def _compute_atr(self, prices: pd.DataFrame, period: int = 14) -> float:
        """计算 ATR(14)，用于动态止损。返回绝对价格值。"""
        import numpy as _np

        try:
            highs = prices["high"].astype(float)
            lows = prices["low"].astype(float)
            closes = prices["close"].astype(float)
            if len(closes) < period + 1:
                return 0.0
            trs = []
            for i in range(-period, 0):
                h = float(highs.iloc[i])
                l = float(lows.iloc[i])
                pc = float(closes.iloc[i - 1])
                trs.append(max(h - l, abs(h - pc), abs(l - pc)))
            return float(_np.mean(trs))
        except Exception:
            return 0.0

    def _notify(self, text: str, level: str = "info") -> None:
        self.log.info(text)
        event_types = self.dcfg.webhook_events
        if level == "critical" and "critical" not in event_types:
            return
        if level == "trade" and "trade" not in event_types:
            return
        self.notifier.send(text, level)

    # ── 市场时钟循环 ────────────────────────────────────────────────────

    def _wait_for_market(self) -> None:
        """Sleep until the market is open, with pre-market warmup + 夜间扫描."""
        market = self.dcfg.market
        label = market_label(market)
        wait = seconds_until_market(market)
        if wait > 0:
            wait_min = wait / 60
            self.log.info(f"{label}尚未开盘，等待 {wait_min:.0f} 分钟...")
            if wait > 300:
                open_time = _now().replace(hour=ASHARE_OPEN[0], minute=ASHARE_OPEN[1]) if market == "cn" else _now()
                self._notify(f"⏰ {label}尚未开盘，预计 {(open_time + _timedelta(wait)).strftime('%H:%M')} 开始交易")

            # ── 夜间定时扫描: 每 4 小时跑一次，检测候选变化 ──
            NIGHT_SCAN_INTERVAL = 4 * 3600  # 4h
            last_night_scan = 0.0

            while wait > 0 and self._running:
                chunk = min(60, wait)
                time.sleep(chunk)
                wait -= chunk

                # Periodic night scan
                now_ts = time.time()
                if now_ts - last_night_scan >= NIGHT_SCAN_INTERVAL:
                    self._night_scan()
                    last_night_scan = now_ts

                if wait < 300:
                    wait = seconds_until_market(market)

    def _night_scan(self) -> None:
        """夜间扫描: 选股 + 检测候选变化通知."""
        try:
            from quanttrader.scanner.lite import diff_results
            from quanttrader.scanner.lite import run as scan_run

            self.log.info("🌙 夜间扫描开始...")
            picks = scan_run(top_n=12)
            if not picks:
                self.log.info("🌙 夜间扫描: 无候选 (可能非交易时段)")
                return

            # 对比上次结果
            prev = getattr(self, "_prev_scan_picks", [])
            if prev:
                diff = diff_results(prev, picks)
                new_codes = [f"{p.code}({p.name})" for p in diff["new"]]
                gone_codes = [f"{p.code}({p.name})" for p in diff["gone"]]
                if new_codes or gone_codes:
                    msg_parts = []
                    if new_codes:
                        msg_parts.append(f"🟢 新入围: {', '.join(new_codes)}")
                    if gone_codes:
                        msg_parts.append(f"🔴 退出: {', '.join(gone_codes)}")
                    msg = "🌙 夜间扫描变化\n" + "\n".join(msg_parts)
                    self.log.info(msg)
                    self._notify(msg, level="info")
                else:
                    self.log.info(f"🌙 夜间扫描: {len(picks)} 候选，无变化")
            else:
                self.log.info(f"🌙 首次夜间扫描: {len(picks)} 候选")
                for p in picks[:5]:
                    self.log.info(
                        f"   {p.code} {p.name} score={p.score} "
                        f"→ {p.action}"
                    )

            self._prev_scan_picks = picks
        except Exception as e:
            self.log.warning(f"夜间扫描异常 (不中断): {e}")

    def _should_stop_trading(self) -> bool:
        """True if market is closed and we should pause."""
        return not market_is_open(self.dcfg.market)

    # ── 健康巡检 ────────────────────────────────────────────────────────

    def _health_check(self) -> None:
        """每 10 分钟巡检：LLM 连通性、API Key、异常计数。发现问题自动修复。"""
        now = time.time()
        if now - self._last_health_check < self._health_check_interval:
            return
        self._last_health_check = now
        issues = []

        # 1) API Key 检查
        try:
            cfg = self.llm.resolve()
            if not cfg.api_key:
                issues.append("API_KEY 缺失")
                # 尝试重新加载 .env
                self.log.warning("API Key 丢失，尝试重新加载 .env...")
                self._reload_env()
                cfg = self.llm.resolve()
                if cfg.api_key:
                    self.log.info("✅ .env 重载成功，API Key 已恢复")
                    issues.pop()
                else:
                    issues.append("API_KEY 重载后仍缺失")
        except Exception as e:
            issues.append(f"LLM 配置异常: {e}")

        # 2) LLM 连通性 ping（发一个最小请求测通）
        if cfg.api_key:
            try:
                import requests

                # 轻量 ping: 获取模型列表（不消耗 token）
                resp = requests.get(
                    f"{cfg.base_url.rstrip('/')}/models",
                    headers={"Authorization": f"Bearer {cfg.api_key}"},
                    timeout=10,
                )
                if resp.status_code == 401:
                    issues.append("API_KEY 已过期/无效 (401)")
                elif resp.status_code == 403:
                    issues.append("API_KEY 无权限 (403)")
                elif resp.status_code >= 500:
                    issues.append(f"LLM 服务端异常 ({resp.status_code})")
                # 404 = 正常（有些 provider 不支持 /models 端点）
            except requests.exceptions.ConnectionError:
                issues.append("LLM 网络不可达")
            except requests.exceptions.Timeout:
                issues.append("LLM 连接超时(10s)")
            except Exception as e:
                issues.append(f"LLM ping 异常: {e.__class__.__name__}")

        # 3) 连续失败检查
        if self._consecutive_llm_fails >= 5:
            issues.append(f"LLM 连续失败 {self._consecutive_llm_fails} 次")

        # 4) Broker 连通性
        try:
            acct = self.broker.get_account()
            if acct is None:
                issues.append("Broker 返回空账户")
        except Exception as e:
            issues.append(f"Broker 不可达: {e}")

        # 处理问题
        if issues:
            msg = "🏥 巡检发现问题:\n" + "\n".join(f"  ⚠️ {i}" for i in issues)
            self.log.warning(msg)
            self._notify(msg, level="critical")

            # 自动修复：重新初始化所有组件
            if any("API_KEY" in i or "LLM" in i for i in issues):
                self.log.info("🔧 尝试自愈：重载 .env + 重建 LLM 配置...")
                self._reload_env()
                try:
                    self.llm.resolve()
                    self.log.info("✅ LLM 配置重建成功")
                except Exception as e:
                    self.log.error(f"❌ LLM 自愈失败: {e}")

            if any("Broker" in i for i in issues):
                self.log.info("🔧 尝试自愈：重建 Broker 连接...")
                try:
                    self._init_trader()
                    self.log.info("✅ Broker 重连成功")
                except Exception as e:
                    self.log.error(f"❌ Broker 自愈失败: {e}")
        else:
            self.log.debug("🏥 巡检通过 ✓")

    @staticmethod
    def _reload_env() -> None:
        """重新加载 .env 文件到环境变量。"""
        env_path = Path(__file__).resolve().parent.parent / ".env"
        if not env_path.exists():
            return
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()

    # ── 看门狗：主循环卡死自动重启 ──────────────────────────────────────

    def _start_watchdog(self) -> None:
        """启动看门狗线程，检测主循环是否卡死。"""
        if not self.dcfg.watchdog_enabled:
            return
        self._watchdog_fired = False

        def _watchdog_loop():
            while self._running and not self._watchdog_fired:
                time.sleep(30)
                if not self._running:
                    break
                elapsed = time.time() - self._last_tick_time
                if self._last_tick_time > 0 and elapsed > self.dcfg.watchdog_timeout:
                    self.log.critical(
                        f"Watchdog triggered! Main loop stuck {elapsed:.0f}s (threshold {self.dcfg.watchdog_timeout}s)"
                    )
                    self._notify(
                        f"ALERT: Watchdog: main loop stuck {elapsed:.0f}s, restarting...",
                        level="critical",
                    )
                    self._watchdog_fired = True
                    try:
                        self._init_trader()
                        self._last_tick_time = time.time()
                        self.log.info("Watchdog restart OK")
                    except Exception as e:
                        self.log.error(f"Watchdog restart failed: {e}")

        self._watchdog = threading.Thread(target=_watchdog_loop, daemon=True, name="watchdog")
        self._watchdog.start()

    def _stop_watchdog(self) -> None:
        """停止看门狗。"""
        self._watchdog_fired = True
        if self._watchdog and self._watchdog.is_alive():
            self._watchdog.join(timeout=5)

    # ── 配置热加载 ─────────────────────────────────────────────────────

    def _hot_reload_config(self) -> None:
        """检测 config.yaml 修改时间，变化时自动重载。"""
        if not self.dcfg.config_hot_reload:
            return
        try:
            config_path = Path(self.config_path)
            if not config_path.exists():
                return
            mtime = config_path.stat().st_mtime
            if self._last_config_mtime > 0 and mtime > self._last_config_mtime:
                self.log.info("Config changed, hot-reloading...")
                old_symbol = self.cfg.symbol if self.cfg else ""
                self._init_trader()
                new_symbol = self.cfg.symbol if self.cfg else ""
                if old_symbol != new_symbol:
                    self.log.info(f"Config hot-reload done: {old_symbol} -> {new_symbol}")
                else:
                    self.log.info("Config hot-reload done")
                self._notify("Config hot-reloaded", level="info")
            self._last_config_mtime = mtime
        except Exception as e:
            self.log.warning(f"Config hot-reload failed: {e}")

    # ── 自适应轮询 ─────────────────────────────────────────────────────

    def _adaptive_poll_interval(self, prices: pd.DataFrame) -> float:
        """波动大时加速轮询，平静时减频。返回建议轮询秒数。"""
        if not self.dcfg.adaptive_poll:
            return float(self.dcfg.poll_seconds)

        try:
            import numpy as _np

            closes = prices["close"].astype(float)
            if len(closes) < 20:
                return float(self.dcfg.poll_seconds)

            ret_5 = float(_np.std(closes.pct_change().tail(5).dropna()) * 100)
            ret_20 = float(_np.std(closes.pct_change().tail(20).dropna()) * 100)
            vol_ratio = ret_5 / ret_20 if ret_20 > 0 else 1.0

            if vol_ratio > 1.5:
                factor = min(vol_ratio / 1.5, 2.0)
                new_poll = max(self.dcfg.poll_min, self.dcfg.poll_seconds / factor)
            elif vol_ratio < 0.7:
                new_poll = min(self.dcfg.poll_max, self.dcfg.poll_seconds * (0.7 / max(vol_ratio, 0.1)))
            else:
                new_poll = float(self.dcfg.poll_seconds)

            self._current_poll = self._current_poll * 0.7 + new_poll * 0.3
            self._last_volatility = vol_ratio

            if abs(self._current_poll - self.dcfg.poll_seconds) > 10:
                self.log.info(
                    f"   Adaptive poll: vol_ratio={vol_ratio:.2f} -> "
                    f"poll={self._current_poll:.0f}s (default {self.dcfg.poll_seconds}s)"
                )

            return max(self.dcfg.poll_min, min(self.dcfg.poll_max, self._current_poll))
        except Exception:
            return float(self.dcfg.poll_seconds)

    # ── 持仓对账 ───────────────────────────────────────────────────────

    def _reconcile_position(self, pos, price: float) -> None:
        """核对 broker 持仓与内部状态，发现偏差自动修正。"""
        symbol = self.cfg.symbol
        try:
            # 有持仓但没有 open_fill 记录 -> 补录
            if pos is not None and pos.qty > 0 and symbol not in self.open_fill:
                self.log.warning(
                    f"Position mismatch: broker has {pos.qty} shares but no open_fill, backfilling position record"
                )
                self.open_fill[symbol] = {
                    "price": float(pos.avg_price),
                    "notional": pos.qty * float(pos.avg_price),
                    "ts": _now_utc().isoformat(),
                }
                if self.risk.enabled():
                    self.pos_risk[symbol] = PositionRisk(float(pos.avg_price))

            # 没有持仓但有 open_fill -> 补录平仓
            elif (pos is None or pos.qty == 0) and symbol in self.open_fill:
                self.log.warning("Position mismatch: no broker position but open_fill exists, recording close")
                entry = self.open_fill[symbol].get("price", price)
                self._close_trade_simple(entry, price, "reconcile_missing_pos", 0.0, "position reconciliation")
                self.pos_risk.pop(symbol, None)

        except Exception as e:
            self.log.debug(f"Position reconciliation error (ignored): {e}")

    def _close_trade_simple(
        self, entry_price: float, exit_price: float, reason: str, confidence: float, llm_reason: str
    ) -> None:
        """简化版平仓记录（对账用），不操作 broker。"""
        symbol = self.cfg.symbol
        of = self.open_fill.get(symbol, {})
        if not of:
            return
        qty = int(of.get("notional", 0) / entry_price) if entry_price > 0 else 0
        notional = of.get("notional", 0)
        pnl = (exit_price - entry_price) * qty
        fees = notional * self.cfg.commission * 2
        pnl -= fees
        pnl_pct = pnl / notional if notional else 0
        self.state.day_pnl += pnl
        self.state.total_pnl += pnl
        self.state.total_trades += 1
        if pnl > 0:
            self.state.wins += 1
            self.state.consecutive_losses = 0
        else:
            self.state.consecutive_losses += 1
        self.state.save(self.state_file)
        self.open_fill.pop(symbol, None)
        self.log.info(
            f"Reconcile close: entry ${entry_price:,.2f} -> exit ${exit_price:,.2f} "
            f"pnl ${pnl:,.2f} ({pnl_pct * 100:+.2f}%) reason: {reason}"
        )

    # ── 自愈逻辑 ────────────────────────────────────────────────────────

    def _handle_crash(self, exc: Exception) -> bool:
        """Return False to stop the daemon, True to continue."""
        self._crash_count += 1
        now = time.time()
        if now - self._crash_window_start > 3600:
            self._crash_window_start = now
            self._crash_count = 1

        self.log.error(
            f"异常 ({self._crash_count}/{self.dcfg.max_crash_before_cooldown}): {exc}\n{traceback.format_exc()}"
        )

        if self._crash_count >= self.dcfg.max_crash_before_cooldown:
            msg = f"🚨 连续崩溃 {self._crash_count} 次，进入冷却 {self.dcfg.crash_cooldown_minutes} 分钟"
            self.log.critical(msg)
            self._notify(msg, level="critical")
            time.sleep(self.dcfg.crash_cooldown_minutes * 60)
            self._crash_count = 0
            self._init_trader()  # re-init everything
        else:
            time.sleep(min(30, 5 * self._crash_count))

        return self._running

    # ── 主循环 ──────────────────────────────────────────────────────────

    def run(self) -> None:
        self._running = True
        market = self.dcfg.market
        label = market_label(market)

        self.log.info("=" * 60)
        self.log.info(
            f"🚀 全自动交易守护进程启动 · {label} · "
            f"{self.cfg.symbol} · "
            f"{self.llm.provider}/{self.llm.model or '默认模型'}"
        )
        self.log.info(
            f"风控: 止损={self.risk.stop_loss * 100:.0f}% "
            f"移动止盈={self.risk.trailing_stop * 100:.0f}% "
            f"熔断={self.risk.max_drawdown * 100:.0f}%"
        )
        self.log.info(f"通知: {'已配置' if self.dcfg.webhook_url else '仅控制台'}")
        self.log.info("=" * 60)

        self._notify(
            f"🤖 量化交易守护进程已启动\n"
            f"市场: {label} | 标的: {self.cfg.symbol}\n"
            f"模型: {self.llm.provider}/{self.llm.model or '默认'}",
            level="info",
        )

        # 启动时立即做一次健康巡检
        self._health_check()

        # 初始化配置 mtime（热加载用）
        try:
            self._last_config_mtime = Path(self.config_path).stat().st_mtime
        except Exception:
            pass

        # 启动看门狗
        self._start_watchdog()
        self._last_tick_time = time.time()

        # Graceful shutdown handlers
        def _shutdown(sig, frame):
            self._running = False
            self.log.warning("收到退出信号，安全关闭中...")
            self._notify("⚠️ 守护进程收到退出信号，正在安全关闭...", level="critical")
            self._stop_watchdog()
            self._safe_exit()

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        while self._running:
            try:
                # 0) 健康巡检 (每10分钟)
                self._health_check()

                # 0.5) 配置热加载
                self._hot_reload_config()

                # 1) Wait for market
                if self._should_stop_trading():
                    self._wait_for_market()
                    if not self._running:
                        break
                    self.log.info(f"{label}开盘，开始交易")
                    self._notify(f"🔔 {label}开盘，开始交易 {self.cfg.symbol}", level="info")

                # 2) Trading tick
                self._tick()
                self._last_tick_time = time.time()  # 看门狗喂食

                # 2.5) 收盘后每日自学习 (每个自然日一次)
                self._maybe_run_daily_learning()

                # 3) 自适应轮询间隔（基于 tick 中获取的行情）
                time.sleep(self._current_poll)

            except KeyboardInterrupt:
                self._running = False
            except Exception as e:
                if not self._handle_crash(e):
                    break

        self._stop_watchdog()

        self._notify(
            f"⏹️ 守护进程已停止。今日交易 {self.state.day_trades} 笔，盈亏 ${self.state.day_pnl:,.2f}", level="critical"
        )

    def _safe_exit(self) -> None:
        """Liquidate all positions before shutting down."""
        try:
            pos = self.broker.get_position(self.cfg.symbol)
            if pos and pos.qty != 0:
                side = "多" if pos.qty > 0 else "空"
                self.log.warning(f"安全退出: 清仓{side}头 {abs(pos.qty)} 股")
                self.broker.sell_all(self.cfg.symbol)
                self._notify(f"🛡️ 安全退出: 已清仓 {self.cfg.symbol} ({side}头)", level="critical")
        except Exception:
            pass

    def _maybe_run_daily_learning(self) -> None:
        """收盘后触发 tracker.daily_cycle（验证 + 调参 + 可选 v15 重训）。"""
        if not self.dcfg.self_learning_enabled:
            return
        today = _now().strftime("%Y-%m-%d")
        if self._last_learning_date == today:
            return
        if market_is_open(self.dcfg.market):
            return
        try:
            from quanttrader.tracker import daily_cycle

            result = daily_cycle(retrain_ml=self.dcfg.ml_retrain_enabled)
            self._last_learning_date = today
            self.log.info(
                f"自学习完成: verified={result.get('total_verified')} "
                f"acc={result.get('total_accuracy')} "
                f"edge_acc={((result.get('edge_journal') or {}).get('overall_accuracy'))} "
                f"ml_retrain={result.get('ml_retrain')}"
            )
            if self.dcfg.auto_tune_on_start:
                from quanttrader.engine.sf_ml_coordinator import load_sf_ml_params
                self._sf_ml_params = load_sf_ml_params()
        except Exception as e:
            self.log.warning(f"自学习循环失败: {e}")

    def _rotate_symbol(self) -> None:
        """轮转到下一个品种。每轮tick调用一次。"""
        if not self._symbol_pool:
            return
        entry = self._symbol_pool[self._symbol_idx % len(self._symbol_pool)]
        new_symbol = entry.get("symbol", self.cfg.symbol)
        if new_symbol != self.cfg.symbol:
            self.cfg.symbol = new_symbol
            self.log.info(f"轮转品种 → {new_symbol} ({entry.get('direction','')} {entry.get('tier','')})")
        self._symbol_idx += 1

    def _tick(self) -> None:
        """One complete trading cycle (simplified mode).

        1) Rotate symbol (multi-symbol mode)
        2) Fetch prices
        3) v530 predict high/low range
        4) If range < 1.5%, HOLD (skip)
        5) SymbolFilter — get allowed direction for this symbol
        6) If not allowed, HOLD
        7) Execute: BUY or SELL based on allowed direction
        8) Stop loss / take profit from v530 predictions (ATR fallback)
        9) Fixed 15% position sizing
        """

        self.log.info("─" * 40)

        # ══════════ ① 多品种轮转 ══════════
        self._rotate_symbol()
        symbol = self.cfg.symbol

        # ══════════ 1) 行情数据 ══════════
        prices = self._fetch_prices()
        price = float(prices["close"].iloc[-1])

        # ══════════ v530 + v14 ML 高低点预测 ══════════
        hl_pred = None
        hl_source = "none"
        try:
            c = prices["close"].astype(float).values
            h = prices["high"].astype(float).values if "high" in prices.columns else c
            lo = prices["low"].astype(float).values if "low" in prices.columns else c

            # 优先用v14 ML模型
            try:
                from quanttrader.ml.ml_v14_hl import is_available as v14_available
                from quanttrader.ml.ml_v14_hl import predict_hl
                if v14_available():
                    ml_pred = predict_hl(symbol, c, h, lo)
                    if ml_pred and ml_pred.is_tradeable:
                        hl_pred = ml_pred.to_v530()
                        hl_source = "ml_v14"
                        self.log.info(
                            f"v14 ML预测: 高={ml_pred.predicted_high:,.1f} 低={ml_pred.predicted_low:,.1f} "
                            f"范围={ml_pred.range_pct:.1f}% 波动={ml_pred.volatility}"
                        )
            except Exception as e:
                self.log.debug(f"v14 ML跳过: {e}")

            # v14不可用或不可交易时，回退到v530
            if hl_pred is None:
                hl_pred = predict_range(symbol, c, h, lo)
                hl_source = "v530"
                if hl_pred:
                    self.log.info(
                        f"v530预测: 高={hl_pred.predicted_high:,.1f} 低={hl_pred.predicted_low:,.1f} "
                        f"范围={hl_pred.range_pct:.1f}% 波动={hl_pred.volatility}"
                    )
        except Exception as e:
            self.log.debug(f"高低点预测跳过: {e}")

        if hasattr(self.broker, "set_price"):
            prev = float(prices["close"].iloc[-2]) if len(prices) >= 2 else price
            if hasattr(self.broker, "_fn") and hasattr(self.broker._fn, "set_price"):
                try:
                    self.broker.set_price(self.cfg.symbol, price, prev)
                except TypeError:
                    self.broker.set_price(self.cfg.symbol, price)
            else:
                try:
                    self.broker.set_price(self.cfg.symbol, price)
                except Exception:
                    pass

        # ══════════ 账户/风控 ══════════
        acct = self.broker.get_account()
        pos = self.broker.get_position(self.cfg.symbol)
        equity = acct.equity

        # 持仓对账
        self._reconcile_position(pos, price)

        if self.state.peak_equity <= 0:
            self.state.peak_equity = equity
        self.state.peak_equity = max(self.state.peak_equity, equity)

        # Halt check
        now_ts = time.time()
        if now_ts < self.state.halt_until:
            remain = int(self.state.halt_until - now_ts)
            self.log.info(f"熔断冷却中 [{self.state.halt_reason}]，剩余 {remain}s")
            return

        # Sync position risk
        if pos is not None and pos.qty > 0 and symbol not in self.pos_risk:
            self.pos_risk[symbol] = PositionRisk(float(pos.avg_price))
        if pos is None or pos.qty == 0:
            self.pos_risk.pop(symbol, None)

        # Stop-loss / trailing-stop exits
        if symbol in self.pos_risk and pos is not None and pos.qty > 0:
            self.pos_risk[symbol].update(price)
            reason = self.pos_risk[symbol].hit_stop(price, self.risk)
            if reason:
                self.broker.sell_all(symbol)
                self._close_trade(pos, price, reason, 0.0, "")
                self.pos_risk.pop(symbol, None)
                self.state.day_trades += 1
                self.state.save(self.state_file)
                self.log.warning(f"风控退出: {reason} @ ${price:,.2f}")
                self._notify(
                    f"🔴 {symbol} 风控退出\n价格: ${price:,.2f} | 理由: {reason}",
                    level="trade",
                )
                return

        # Portfolio drawdown halt
        if self.risk.max_drawdown and equity <= self.state.peak_equity * (1 - self.risk.max_drawdown):
            if pos is not None and pos.qty > 0:
                self.broker.sell_all(self.cfg.symbol)
                self._close_trade(pos, price, "max_drawdown_halt", 0.0, "")
                self.pos_risk.pop(self.cfg.symbol, None)
                self.state.day_trades += 1
            self._halt(
                "max_drawdown",
                f"组合回撤熔断 ({self.risk.max_drawdown * 100:.0f}%) - "
                f"峰值 ${self.state.peak_equity:,.0f} → 当前 ${equity:,.0f}",
            )
            self.log.critical(f"组合熔断！回撤 {self.risk.max_drawdown * 100:.0f}%")
            self._notify(f"🚨 组合熔断！回撤超过 {self.risk.max_drawdown * 100:.0f}%", level="critical")
            return

        # ══════════ ② 方向决策 (SymbolFilter + v530) ══════════
        sig = 0
        label = "HOLD"
        confidence = 0.0
        reason = "simplified mode"

        producer_name = (self.dcfg.signal_producer or "").strip().lower()
        if producer_name:
            try:
                from quanttrader.engine.signal_producer import get_signal_producer
                ps = get_signal_producer(producer_name).produce(
                    symbol, prices,
                    profile="research" if producer_name in ("prediction_v2", "v2", "precise") else {},
                )
                if ps and ps.direction != 0:
                    sig = ps.direction
                    label = ps.label
                    confidence = ps.confidence / 100.0
                    reason = f"SignalProducer[{producer_name}]: {ps.reason}"
                    self.log.info(f"   生产者信号: {label} conf={confidence:.0%} | {reason}")
                elif ps:
                    reason = f"SignalProducer[{producer_name}]: {ps.reason}"
                    if self.dcfg.signal_diagnostics:
                        self._blockers.record(f"producer_hold:{producer_name}")
            except Exception as e:
                self.log.debug(f"SignalProducer跳过: {e}")

        if not hl_pred:
            self.log.info("v530预测不可用, SymbolFilter仍可独立出信号")
            if self.dcfg.signal_diagnostics:
                self._blockers.record("v530_unavailable")
        elif not hl_pred.is_tradeable:
            self.log.info(f"v530波动过滤: 范围{hl_pred.range_pct:.1f}%<1.5%, 仍尝试SymbolFilter")
            if self.dcfg.signal_diagnostics:
                self._blockers.record("v530_low_range")

        # legacy: SymbolFilter 白名单 — 不依赖 v530 是否可用
        if sig == 0 and not producer_name:
            try:
                from quanttrader.engine.symbol_filter import SymbolFilter
                sf = SymbolFilter()
                tier_buy, _ = sf.filter(symbol, "BUY", 0.5)
                tier_sell, _ = sf.filter(symbol, "SELL", 0.5)

                # 保存SymbolFilter数据供评分用
                self._current_tier = tier_buy or tier_sell or ""
                self._current_win_rate = 0.0
                self._current_sample = 0
                # 从白名单获取准确率和样本数
                whitelist = sf._whitelist
                sym_base = symbol.upper().rstrip("0")
                if sym_base in whitelist:
                    for d in ("BUY", "SELL"):
                        rec = whitelist[sym_base].get(d)
                        if rec:
                            self._current_win_rate = rec.accuracy
                            self._current_sample = rec.sample_count
                            break

                if tier_buy and not tier_sell:
                    sig = 1
                    label = "BUY"
                    confidence = 1.0
                    reason = f"SymbolFilter {tier_buy}: {symbol} allowed BUY"
                elif tier_sell and not tier_buy:
                    sig = -1
                    label = "SELL"
                    confidence = 1.0
                    reason = f"SymbolFilter {tier_sell}: {symbol} allowed SELL"
                elif tier_buy and tier_sell:
                    # Both allowed — check symbol_pool for preferred direction
                    pool_entry = next(
                        (s for s in self._symbol_pool if s.get("symbol", "").upper() == symbol.upper()),
                        None,
                    )
                    if pool_entry and pool_entry.get("direction"):
                        d = pool_entry["direction"].upper()
                        if d == "BUY":
                            sig = 1
                            label = "BUY"
                            confidence = 1.0
                            reason = "SymbolFilter both OK, pool prefers BUY"
                        elif d == "SELL":
                            sig = -1
                            label = "SELL"
                            confidence = 1.0
                            reason = "SymbolFilter both OK, pool prefers SELL"
                    else:
                        self.log.info(f"SymbolFilter: {symbol} 允许BUY+SELL但无偏好方向, HOLD")
                        if self.dcfg.signal_diagnostics:
                            self._blockers.record("symbol_filter_no_preference")
                else:
                    self.log.info(f"SymbolFilter: {symbol} 不在白名单, HOLD")
                    if self.dcfg.signal_diagnostics:
                        self._blockers.record("symbol_filter_not_whitelisted")
                    self.log.info(f"   {sf.summary()}")
            except Exception as e:
                self.log.debug(f"SymbolFilter跳过: {e}")

        # ══════════ ②b SF×ML 协调 (v14 edge 按 tier 自动门槛 + ML 不硬否决 tier1/2) ══════════
        edge_approved = False
        edge_info = ""
        if sig != 0:
            try:
                from quanttrader.engine.sf_ml_coordinator import evaluate_sf_ml, load_sf_ml_params

                params = getattr(self, "_sf_ml_params", None) or load_sf_ml_params()
                coord = evaluate_sf_ml(
                    symbol=symbol,
                    sf_sig=sig,
                    sf_label=label,
                    sf_confidence=confidence,
                    sf_tier=getattr(self, "_current_tier", ""),
                    sf_win_rate=getattr(self, "_current_win_rate", 0),
                    sf_sample=getattr(self, "_current_sample", 0),
                    prices=prices,
                    hl_pred=hl_pred,
                    params=params,
                    sf_reason=reason,
                )
                sig = coord.sig
                label = coord.label
                confidence = coord.confidence
                reason = coord.reason
                edge_approved = coord.edge_approved
                edge_info = coord.edge_info
                if coord.outcome == "edge_block" and self.dcfg.signal_diagnostics:
                    self._blockers.record("v14_edge_insufficient")
                elif coord.outcome == "ml_veto" and self.dcfg.signal_diagnostics:
                    self._blockers.record("ml_veto_sf")
                elif coord.outcome == "sf_priority" and coord.conflict:
                    self.log.info(f"   SF×ML: ML冲突→保留SF ({coord.ml_mode})")
                    try:
                        from quanttrader.engine.sf_ml_conflicts import record_conflict
                        record_conflict(
                            symbol=symbol,
                            sf_sig=coord.sig if coord.sig else sig,
                            sf_tier=getattr(self, "_current_tier", ""),
                            ml_signal=coord.ml_signal,
                            ml_confidence=coord.ml_confidence,
                            ml_mode=coord.ml_mode,
                            outcome=coord.outcome,
                            sf_win_rate=getattr(self, "_current_win_rate", 0) / 100.0
                            if getattr(self, "_current_win_rate", 0) > 1
                            else getattr(self, "_current_win_rate", 0),
                        )
                    except Exception:
                        pass
                if coord.outcome == "ml_boost":
                    self.log.info(f"   SF×ML: ML确认 conf={coord.ml_confidence:.0%}")
            except Exception as e:
                self.log.debug(f"SF×ML协调跳过: {e}")

        # ══════════ ②c LLM二次确认 (当方向已定时) ══════════
        if sig != 0 and self.llm_key and self.dcfg.llm_veto_enabled:
            try:
                from quanttrader.ai.llm import LLMConfig, ask_llm
                cfg = LLMConfig(provider=self.llm_provider, api_key=self.llm_key)
                llm_result = ask_llm(prices, cfg)
                llm_signal = int(llm_result.get("signal", 0))
                llm_conf = float(llm_result.get("confidence", 0))
                llm_reason = llm_result.get("reason", "")

                # LLM与ML+SF方向一致 → 最终确认
                if llm_signal == sig:
                    confidence = min(1.0, confidence * 1.05)
                    reason += f" | LLM确认({llm_conf:.0%})"
                    self.log.info(f"   LLM确认: conf={llm_conf:.0%} reason={llm_reason[:60]}")
                # LLM强烈反对 — tier1/tier2 白名单免疫；阈值默认 0.85 (旧 0.7 过保守)
                elif llm_signal != 0 and llm_signal != sig and llm_conf >= self.dcfg.llm_veto_confidence:
                    tier = (getattr(self, "_current_tier", "") or "").lower()
                    if tier in {t.lower() for t in self.dcfg.llm_sf_priority_tiers}:
                        reason += f" | LLM反对({llm_conf:.0%})但{tier}免疫"
                        self.log.info(f"   LLM反对但{tier}保留SF: conf={llm_conf:.0%}")
                    else:
                        sig = 0
                        label = "HOLD"
                        confidence = 0.0
                        reason = f"LLM强烈反对 (conf={llm_conf:.0%} {llm_reason[:50]}) → HOLD"
                        self.log.info(f"   LLM反对: conf={llm_conf:.0%} reason={llm_reason[:60]}")
                        if self.dcfg.signal_diagnostics:
                            self._blockers.record("llm_veto")
                else:
                    self.log.info(f"   LLM: 中性/弱反对 (conf={llm_conf:.0%}), 保持原信号")
            except Exception as e:
                self.log.debug(f"LLM确认跳过: {e}")
        elif sig != 0 and self.llm_key and not self.dcfg.llm_veto_enabled:
            self.log.debug("LLM否决已关闭 (llm_veto_enabled=false), 跳过二次确认")

        # ══════════ ②d 置信度门槛 (钳制 0.75 等不可达阈值) ══════════
        if sig != 0:
            try:
                from quanttrader.engine.confidence_policy import (
                    effective_min_confidence,
                    passes_confidence_gate,
                )
                from quanttrader.tracker import load_strategy_params

                sp = load_strategy_params()
                tier = getattr(self, "_current_tier", "")
                if not passes_confidence_gate(confidence, sp, tier):
                    need = effective_min_confidence(sp, tier)
                    prev_conf = confidence
                    self.log.info(
                        f"   置信度门槛: {prev_conf:.0%} < {need:.0%} (tier={tier or 'n/a'}) → HOLD"
                    )
                    if self.dcfg.signal_diagnostics:
                        self._blockers.record("min_confidence_gate")
                    sig = 0
                    label = "HOLD"
                    confidence = 0.0
                    reason = f"置信度{prev_conf:.0%}低于门槛{need:.0%}"
            except Exception as e:
                self.log.debug(f"置信度门槛跳过: {e}")

        self.log.info(f"   最终信号: {label} conf={confidence:.0%} | {reason}")

        # ══════════ ③ 生成交易建议卡（半自动模式）══════════
        from quanttrader.assistant.blocker import check_block
        from quanttrader.assistant.card import build_trade_card
        from quanttrader.assistant.score import compute_trade_score

        action = "hold"
        card = None

        if sig != 0 and hl_pred:
            # 计算ATR止损距离
            atr = self._compute_atr(prices)
            atr_stop_pct = 1.5 * atr / price * 100 if atr > 0 and price > 0 else 0

            # 计算评分
            ts = compute_trade_score(
                symbol=symbol,
                direction="BUY" if sig == 1 else "SELL",
                range_pct=hl_pred.range_pct,
                tier=getattr(self, '_current_tier', ''),
                win_rate=getattr(self, '_current_win_rate', 0),
                sample_size=getattr(self, '_current_sample', 0),
                v530_stop_distance=hl_pred.stop_distance_pct,
                atr_stop_distance=atr_stop_pct,
                upside_pct=hl_pred.target_distance_pct,
                downside_pct=hl_pred.stop_distance_pct,
            )

            # 禁止交易检查
            block = check_block(
                range_pct=hl_pred.range_pct,
                direction_allowed=True,
                sample_size=getattr(self, '_current_sample', 0),
                stop_status=ts.stop_status,
                score=ts.total,
            )

            if block.blocked:
                self.log.info(f"   禁止交易: {block.reason}")
                action = "blocked"
                if self.dcfg.signal_diagnostics:
                    self._blockers.record(f"assistant_block:{block.reason[:60]}")
            else:
                # 生成建议卡
                card = build_trade_card(
                    symbol=symbol,
                    direction="BUY" if sig == 1 else "SELL",
                    current_price=price,
                    pred_high=hl_pred.predicted_high,
                    pred_low=hl_pred.predicted_low,
                    range_pct=hl_pred.range_pct,
                    volatility=hl_pred.volatility,
                    tier=getattr(self, '_current_tier', ''),
                    win_rate=getattr(self, '_current_win_rate', 0),
                    sample_size=getattr(self, '_current_sample', 0),
                    atr_stop_distance=atr_stop_pct,
                    v530_stop_distance=hl_pred.stop_distance_pct,
                    stop_status=ts.stop_status,
                    score=ts.total,
                    rating=ts.rating,
                    rating_label=ts.rating_label,
                    reasons=[block.reason] if block.blocked else [],
                )
                action = f"SUGGEST_{card.rating}"

                # 保存建议卡
                from pathlib import Path
                today = _now().strftime("%Y%m%d")
                cards_path = Path(self.dcfg.log_dir) / f"signals_{today}.json"
                existing = []
                if cards_path.exists():
                    try:
                        import json as _json
                        existing = [_json.loads(line) for line in cards_path.read_text(encoding="utf-8").splitlines() if line.strip()]
                    except Exception:
                        existing = []
                existing.append(card.to_dict())
                cards_path.parent.mkdir(parents=True, exist_ok=True)
                cards_path.write_text(
                    "\n".join(_json.dumps(c, ensure_ascii=False) for c in existing) + "\n",
                    encoding="utf-8",
                )

                # 记录到日志
                from quanttrader.assistant.journal import TradeJournal
                journal = TradeJournal(Path(self.dcfg.log_dir))
                journal.record_suggestion(card)

                self.log.info(f"   交易建议: {card.final_suggestion} [{card.rating}] 评分={card.score:.0f}")
                self.log.info(f"   v530: 高={card.pred_high:,.1f} 低={card.pred_low:,.1f} 范围={card.range_pct:.1f}%")
                self.log.info(f"   止损={card.downside_pct:.1f}% 止盈={card.upside_pct:.1f}% RR={card.risk_reward:.2f}")
                self._notify(
                    f"📋 {symbol} 交易建议\n"
                    f"方向: {'做多' if sig == 1 else '做空'} | 评级: [{card.rating}] {card.rating_label}\n"
                    f"评分: {card.score:.0f}/100\n"
                    f"v530: 高={card.pred_high:,.1f} 低={card.pred_low:,.1f}\n"
                    f"止损: {card.downside_pct:.1f}% | 止盈: {card.upside_pct:.1f}%\n"
                    f"仓位建议: {card.position_suggestion}",
                    level="trade",
                )
        elif sig != 0 and not hl_pred:
            atr = self._compute_atr(prices)
            atr_stop_pct = 1.5 * atr / price * 100 if atr > 0 and price > 0 else 0
            action = f"SUGGEST_SF_{label}"
            self.log.info(
                f"   SF信号(无v530): {label} tier={getattr(self, '_current_tier', '')} "
                f"win={getattr(self, '_current_win_rate', 0):.1f}% ATR止损≈{atr_stop_pct:.1f}%"
            )

        # ══════════ 日志记录 ══════════
        if self.dcfg.signal_diagnostics:
            self._blockers.tick_done(had_signal=(sig != 0))
            every = max(1, int(self.dcfg.diagnostics_log_every))
            if self._blockers.ticks % every == 0:
                for line in self._blockers.summary_lines():
                    self.log.info(line)

        self._record_decision(
            price,
            sig,
            label,
            confidence,
            reason,
            equity,
            pos.qty if pos else 0,
            action,
        )
        self.state.last_decision_at = _now_utc().isoformat()
        self.state.save(self.state_file)

        # Status
        day_pnl = (equity / self.day_equity_start - 1) * 100
        is_open = market_is_open(self.dcfg.market)
        self.log.info(
            f"权益 ${equity:,.2f} | 日 {day_pnl:+.2f}% | "
            f"持仓 {pos.qty if pos else 0} | {label} | "
            f"累计 {self.state.total_trades}笔 | "
            f"{'交易中' if is_open else '等待开盘'}"
        )

        # Post-market check
        if not is_open and self.state.day_trades > 0 and pos is None:
            self.log.info("收盘，当日交易结束")
            self._notify(
                f"📊 {market_label(self.dcfg.market)}今日交易总结\n"
                f"标的: {self.cfg.symbol}\n"
                f"交易: {self.state.day_trades} 笔\n"
                f"日盈亏: {day_pnl:+.2f}%\n"
                f"期末权益: ${equity:,.2f}",
                level="daily_summary",
            )

        # 自适应轮询间隔
        self._current_poll = self._adaptive_poll_interval(prices)

    def _record_decision(
        self,
        price,
        sig,
        label,
        confidence,
        reason,
        equity,
        position,
        action,
        news_sent="",
        news_cnt=0,
    ) -> None:
        with open(self.decision_log, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(
                [
                    _now_utc().isoformat(),
                    self.cfg.symbol,
                    price,
                    sig,
                    label,
                    round(confidence, 4),
                    reason[:200],
                    round(equity, 2),
                    position,
                    action,
                    market_is_open(self.dcfg.market),
                    news_sent,
                    news_cnt,
                ]
            )

    def _close_trade(self, pos, exit_price, reason, confidence, llm_reason) -> None:
        symbol = self.cfg.symbol
        of = self.open_fill.get(symbol, {})
        if not of:
            return
        entry_price = of["price"]
        qty = pos.qty
        notional = of["notional"]
        pnl = (exit_price - entry_price) * qty
        fees = notional * self.cfg.commission * 2
        pnl -= fees
        pnl_pct = pnl / notional if notional else 0
        self.state.day_pnl += pnl
        self.state.total_pnl += pnl
        self.state.total_trades += 1
        if pnl > 0:
            self.state.wins += 1
            self.state.consecutive_losses = 0
        else:
            self.state.consecutive_losses += 1
        self.state.save(self.state_file)
        self.open_fill.pop(symbol, None)
        self.log.info(
            f"成交: 入场 ${entry_price:,.2f} → 出场 ${exit_price:,.2f} "
            f"盈亏 ${pnl:,.2f} ({pnl_pct * 100:+.2f}%) "
            f"理由: {reason}"
        )

    def _halt(self, reason: str, msg: str) -> None:
        self.state.halt_until = time.time() + self.dcfg.crash_cooldown_minutes * 60
        self.state.halt_reason = reason
        self.state.save(self.state_file)
        self._notify(f"⛔ 熔断触发\n{msg}", level="critical")


def _timedelta(seconds: float):
    from datetime import timedelta

    return timedelta(seconds=seconds)


# ═══════════════════════════════════════════════════════════════════════════
# Windows 服务注册
# ═══════════════════════════════════════════════════════════════════════════


def install_windows_service() -> int:
    """Install the daemon as a Windows service (requires admin)."""
    try:
        import servicemanager  # noqa: F401 — guard import
        import win32event  # noqa: F401 — guard import
        import win32service  # noqa: F401 — guard import
        import win32serviceutil  # noqa: F401 — guard import
    except ImportError:
        print("需要 pywin32: pip install pywin32")
        return 1

    service_name = "QuantTraderDaemon"
    display_name = "量化交易守护进程 (QuantTrader Daemon)"
    description = "全自动 AI 量化交易守护进程 — DeepSeek LLM 驱动"

    python = sys.executable
    script = str(Path(__file__).resolve())

    cmd = f'sc create {service_name} binPath= "{python} {script} --daemon" start= auto DisplayName= "{display_name}" '
    print("以管理员身份运行以下命令来注册服务:\n")
    print(f"  安装:  {cmd}")
    print(f"  启动:  sc start {service_name}")
    print(f"  停止:  sc stop {service_name}")
    print(f"  删除:  sc delete {service_name}")
    print()
    print("或者使用 NSSM (推荐): https://nssm.cc")
    print(f"  nssm install {service_name} {python} {script} --daemon")
    print(f"  nssm set {service_name} AppDirectory {Path(script).parent}")
    print(f"  nssm set {service_name} Start SERVICE_AUTO_START")
    return 0


def uninstall_windows_service() -> int:
    service_name = "QuantTraderDaemon"
    import subprocess

    subprocess.run(["sc", "stop", service_name], capture_output=True)
    subprocess.run(["sc", "delete", service_name], capture_output=True)
    print(f"服务 '{service_name}' 已停止并删除。")
    return 0


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="量化交易全自动守护进程",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--config", "-c", default="config.yaml", help="交易配置文件")
    parser.add_argument("--daemon-config", "-d", default="daemon.yaml", help="守护进程配置文件")
    parser.add_argument("--daemon", action="store_true", help="后台守护模式")
    parser.add_argument("--once", action="store_true", help="单次决策后退出")
    parser.add_argument("--install", action="store_true", help="注册 Windows 服务 (需管理员)")
    parser.add_argument("--uninstall", action="store_true", help="移除 Windows 服务")
    parser.add_argument("--status", action="store_true", help="查看守护进程状态")
    args = parser.parse_args(argv)

    if args.install:
        return install_windows_service()
    if args.uninstall:
        return uninstall_windows_service()

    daemon = TradingDaemon(
        config_path=args.config,
        daemon_config_path=args.daemon_config,
    )

    if args.status:
        state = daemon.state
        print("守护进程状态:")
        print(f"  日期: {state.date}")
        print(f"  今日交易: {state.day_trades} 笔")
        print(f"  今日盈亏: ${state.day_pnl:,.2f}")
        print(f"  累计交易: {state.total_trades} 笔")
        print(f"  命中: {state.wins} 次")
        wr = state.win_rate
        print(f"  命中率: {wr * 100:.1f}%" if wr is not None else "  命中率: N/A (无交易)")
        print(f"  累计盈亏: ${state.total_pnl:,.2f}")
        print(f"  连亏: {state.consecutive_losses}")
        print(f"  熔断: {'是' if state.halt_until > time.time() else '否'}")
        print(f"  最后决策: {state.last_decision_at or '无'}")
        return 0

    if args.once:
        # Single decision — for cron scheduling
        daemon._running = True
        daemon._tick()
        return 0

    # Full daemon mode
    if args.daemon:
        # Background mode
        daemon.run()
        return 0

    # Foreground mode (default)
    daemon.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
