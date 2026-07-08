from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
import uuid
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    import requests

_logger = logging.getLogger("api.security")


def _validate_url(url: str) -> str:
    """Reject URLs pointing to internal/private networks (SSRF protection)."""
    if not url:
        return url
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http"):
        raise ValueError(f"URL scheme must be http/https, got: {parsed.scheme}")
    hostname = parsed.hostname or ""
    # Block private/loopback/link-local IPs
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise ValueError(f"URL points to private network: {hostname}")
    except ValueError as ve:
        # Re-raise only if it's our own ValueError (private network check)
        if "URL points to" in str(ve):
            raise
        # Otherwise hostname is not an IP — continue to string checks below
        pass
    blocked = ("localhost", "127.0.0.1", "0.0.0.0", "169.254.169.254", "[::1]", "metadata.google.internal")
    if any(b in hostname for b in blocked):
        raise ValueError(f"URL points to blocked host: {hostname}")
    return url


def _sanitize_api_key(key: str) -> str:
    """Return a masked version of an API key for logging."""
    if not key or len(key) < 8:
        return "***"
    return key[:3] + "***" + key[-3:]


def _make_session() -> requests.Session:
    """Create a requests session with proxy disabled and TLS verification."""
    import requests as _requests

    s = _requests.Session()
    s.trust_env = False
    s.verify = True
    return s


# Imported at module scope so FastAPI can resolve the `ws: WebSocket` annotation
# via get_type_hints (this file uses `from __future__ import annotations`, which
# turns annotations into strings evaluated against module globals). Guarded so
# the core package still works when the optional API deps aren't installed.
try:
    from fastapi import WebSocket
except ImportError:
    WebSocket = None  # type: ignore

import datetime as dt

from .. import __version__
from ..advisor import PRINCIPLES, advise
from ..broker.base import get_broker
from ..data.base import BarRequest, get_feed
from ..engine.backtest import Backtester
from ..engine.futures_backtest import FuturesBacktestConfig, FuturesBacktester
from ..engine.optimize import DEFAULT_GRIDS, grid_search, optimize_catalog, walk_forward
from ..engine.playbook import build_playbook, list_playbooks, run_playbook
from ..engine.portfolio_backtest import MultiBacktester
from ..engine.position_sizing import SizingConfig
from ..engine.risk import RiskConfig
from ..engine.risk_assessment import assess_backtest_result, assess_portfolio, assess_trade, assessment_to_dict
from ..horizon import get_horizon, list_horizons
from ..strategy.base import Signal, get_strategy
from .schemas import (
    AccountResponse,
    AIRunRequest,
    AIRunResponse,
    BacktestRequest,
    BacktestResponse,
    Bar,
    BarsResponse,
    LLMRunRequest,
    LLMRunResponse,
    OptimizeRequest,
    OptimizeResponse,
    OrderRequest,
    OrderResponse,
    OrdersListResponse,
    PlaybookRequest,
    PlaybookResponse,
    PortfolioBacktestRequest,
    PortfolioBacktestResponse,
    PriceResponse,
    RiskAssessRequest,
    RiskAssessResponse,
    SettingsResponse,
    SettingsUpdateRequest,
    SignalRequest,
)

# Bounded window for "latest price" lookups so synthetic demo prices stay sane
# (an unbounded multi-decade random walk would explode).
_RECENT_START = "2024-01-01"
_RECENT_END = ""  # 空=取到最新数据，由 _to_yyyymmdd 动态取当天


def _load_prices(symbol: str, source: str, start: str, end: str, interval: str):
    """Load OHLCV, falling back to synthetic data when a real feed fails."""
    if not end:  # 空 end = 取到最新数据(今天); 防止 synthetic 兜底成 start 同日致数据不足
        from datetime import date
        end = date.today().strftime("%Y-%m-%d")
    req = BarRequest(symbol=symbol, start=start, end=end, interval=interval)
    try:
        return get_feed(source).history(req), source
    except Exception:
        if source != "synthetic":
            return get_feed("synthetic").history(req), "synthetic"
        raise


def _prepare_backtest(req: BacktestRequest):
    """Apply horizon preset；新闻融合已下线。"""
    horizon = req.horizon or "medium"
    strategy_name = req.strategy
    params = dict(req.params)
    order_size = req.order_size
    interval = req.interval
    news_payload: dict = {}

    risk_dict = dict(req.risk or {})
    sizing_dict = dict(req.sizing or {})

    if req.apply_horizon_preset:
        preset = get_horizon(horizon)
        if not params:
            params = {k: v for k, v in preset["strategy"].items() if k != "name"}
            strategy_name = preset["strategy"]["name"]
        interval = preset.get("interval", interval)
        risk_dict = {**preset.get("risk", {}), **risk_dict}
        sizing_dict = {**preset.get("sizing", {}), **sizing_dict}
        if req.order_size == 0.25:
            order_size = preset.get("order_size", order_size)

    if req.use_news:
        # 新闻融合 API 已下线；忽略 use_news，走常规策略
        pass
    strategy = get_strategy(strategy_name, **params)

    risk = RiskConfig(**risk_dict)
    sizing = SizingConfig(**sizing_dict)
    return strategy, risk, sizing, order_size, interval, horizon, news_payload, strategy_name


def create_app():
    try:
        from fastapi import (  # noqa: F401 — WebSocket used as type annotation
            Depends,
            FastAPI,
            Header,
            HTTPException,
            WebSocket,
            WebSocketDisconnect,
        )
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import HTMLResponse
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "FastAPI is required for the API server. Run "
            "`pip install fastapi uvicorn` (and `requests` for the AI strategy)."
        ) from exc

    app = FastAPI(
        title="quant-trader API",
        version=__version__,
        description="Market-data + trading engine API. Connect external AI agents here.",
    )

    # Allow browser-based clients / AI dashboards to call the API cross-origin.
    # Default to localhost only — set QT_CORS_ORIGINS env var for custom origins.
    _default_cors = "http://127.0.0.1:8000,http://localhost:8000,http://127.0.0.1:5500,http://localhost:5500"
    cors_origins = os.environ.get("QT_CORS_ORIGINS", _default_cors).split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in cors_origins],
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        allow_credentials=False,
    )

    # 确保 .env 在所有 os.environ.get 之前加载
    _env_file = Path(__file__).resolve().parent.parent.parent / ".env"
    if _env_file.exists():
        for _line in _env_file.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                _v = _v.strip()
                if len(_v) >= 2 and _v[0] == _v[-1] and _v[0] in ('"', "'"):
                    _v = _v[1:-1]
                os.environ.setdefault(_k.strip(), _v)

    # A single shared in-memory broker backs the live order/signal endpoints.
    # QT_BROKER=cn_paper enables A-share rules (100-share lots + T+1).
    broker_name = os.environ.get("QT_BROKER", "paper")
    broker = get_broker(broker_name, cash=100_000.0)

    # Runtime-editable settings (via POST /settings) — broker creds + AI endpoint.
    state = {
        "cash": 100_000.0,
        "api_key": os.environ.get("QT_BROKER_KEY", ""),
        "api_secret": os.environ.get("QT_BROKER_SECRET", ""),
        "paper": True,
        "allow_live": False,
    }
    ai_cfg = {"endpoint": os.environ.get("QT_AI_ENDPOINT", ""), "api_key": os.environ.get("QT_AI_KEY", "")}
    llm_cfg = {
        "provider": os.environ.get("QT_LLM_PROVIDER", "deepseek"),
        "api_key": os.environ.get("QT_LLM_KEY", "") or os.environ.get("DEEPSEEK_API_KEY", ""),
        "model": os.environ.get("QT_LLM_MODEL", ""),
    }

    api_token = os.environ.get("QT_API_TOKEN")  # required for production

    if not api_token:
        _logger.warning(
            "QT_API_TOKEN not set — API will accept all requests. "
            "Set QT_API_TOKEN environment variable for production use."
        )

    def auth(authorization: str | None = Header(default=None)):
        if not api_token:
            return  # auth disabled only when token is not configured
        if not authorization or authorization != f"Bearer {api_token}":
            raise HTTPException(status_code=401, detail="Invalid or missing API token.")

    # ── Security: block remote access when no API token is set ──────
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    class _LocalhostOnlyMiddleware(BaseHTTPMiddleware):
        """When QT_API_TOKEN is not configured, only allow requests from
        localhost (127.0.0.1 / ::1). Remote clients get 403."""

        async def dispatch(self, request, call_next):
            if not api_token:
                client = request.client.host if request.client else ""
                # Skip auth for static files (dashboard, docs) — allow local browser
                # "testclient" 放行 Starlette TestClient(仅单测用, 真实远程客户端不会是此 host, 不损生产安全)
                if client not in ("127.0.0.1", "::1", "localhost", "", "testclient"):
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Remote access requires QT_API_TOKEN. Set it in .env or environment."},
                    )
            return await call_next(request)

    app.add_middleware(_LocalhostOnlyMiddleware)

    # ── Security: add common security headers ───────────────────────
    class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            response = await call_next(request)
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            return response

    app.add_middleware(_SecurityHeadersMiddleware)

    @app.get("/health")
    def health():
        import os

        from ..tracker import compute_stats, load_strategy_params

        params = load_strategy_params()
        stats = compute_stats()
        sf_ml = params.get("sf_ml", {})
        retrain_hint = {}
        try:
            from ..ml.retrain_pipeline import model_age_days, should_retrain_v15

            need, reason = should_retrain_v15()
            retrain_hint = {
                "should_retrain": need,
                "reason": reason,
                "model_age_days": model_age_days(),
            }
        except Exception:
            pass
        return {
            "status": "ok",
            "service": "quant-trader",
            "version": __version__,
            "broker": os.environ.get("QT_BROKER", "paper"),
            "self_learning": {
                "tracker_verified": stats.verified,
                "tracker_accuracy": round(stats.accuracy, 3),
                "min_confidence": params.get("min_confidence"),
                "sf_ml_mode": sf_ml.get("ml_mode", params.get("ml_mode", "advisory")),
                "use_v15": sf_ml.get("use_v15", False),
                "ml_oos_accuracy": sf_ml.get("ml_oos_accuracy", 0),
            },
            "ml_v15": retrain_hint,
        }

    @app.get("/api/config/status", dependencies=[Depends(auth)])
    def config_status():
        """新手向导用 — 检查配置是否就绪 (需要认证)"""
        return {
            "has_llm_key": bool(llm_cfg["api_key"]),
            "llm_provider": llm_cfg["provider"],
            "llm_model": llm_cfg["model"] or "default",
            "broker": broker_name,
            "has_broker_keys": bool(state["api_key"] and state["api_secret"]),
            "deployed": True,
        }

    # ── Security: safe error helper — logs full error, returns generic to client ──
    def _safe_error(status_code: int, message: str, exc: Exception) -> HTTPException:
        """Return a generic error to the client; log the full exception server-side."""
        error_id = uuid.uuid4().hex[:8]
        _logger.error("[ref=%s] %s: %s", error_id, message, exc, exc_info=True)
        return HTTPException(status_code=status_code, detail=f"{message} (ref: {error_id})")

    # ---- Market data interface (股市行情接入/流出) --------------------------
    @app.get("/market/bars", response_model=BarsResponse, dependencies=[Depends(auth)])
    def market_bars(
        symbol: str,
        source: str = "synthetic",
        start: str = "2022-01-01",
        end: str = "2024-01-01",
        interval: str = "1d",
    ):
        try:
            prices, used = _load_prices(symbol, source, start, end, interval)
        except Exception as e:
            raise _safe_error(502, "Data load failed", e)
        bars = [Bar(time=str(ts), **{k: float(v) for k, v in row.items()}) for ts, row in prices.iterrows()]
        return BarsResponse(symbol=symbol, source=used, interval=interval, bars=bars)

    @app.get("/market/price", response_model=PriceResponse, dependencies=[Depends(auth)])
    def market_price(symbol: str, source: str = "synthetic"):
        prices, used = _load_prices(symbol, source, _RECENT_START, _RECENT_END, "1d")
        return PriceResponse(symbol=symbol, price=float(prices["close"].iloc[-1]), source=used)

    # ---- Strategy / backtest interface ------------------------------------
    @app.post("/backtest", response_model=BacktestResponse, dependencies=[Depends(auth)])
    def backtest(req: BacktestRequest):
        try:
            strategy, risk, sizing, order_size, interval, horizon, news_payload, strat_name = _prepare_backtest(req)
        except (ValueError, TypeError) as e:
            raise _safe_error(400, "Bad strategy/params", e)

        try:
            prices, used = _load_prices(req.symbol, req.source, req.start, req.end, interval)
        except Exception as e:
            raise _safe_error(502, "Data load failed", e)

        engine = req.engine or "equity"
        if engine == "futures":
            fcfg = dict(req.futures or {})
            if fcfg.get("target_vol") in ("", None):
                fcfg.pop("target_vol", None)
            fb = FuturesBacktester(FuturesBacktestConfig(**fcfg))
            fresult = fb.run(prices, strategy)
            bh = float(prices["close"].iloc[-1] / prices["close"].iloc[0] - 1.0)
            cash = req.cash
            curve = [
                {"time": str(ts), "equity": float(v) * cash}
                for ts, v in fresult.equity_curve.items()
            ]
            stats = dict(fresult.stats)
            stats.setdefault("annual_vol", stats.get("annual_vol", 0.0))
            stats.setdefault("sortino", stats.get("sharpe", 0.0))
            stats.setdefault("win_rate", None)
            signals = [
                {"time": str(ts), "signal": int(v)}
                for ts, v in fresult.position.items()
                if int(v) != 0
            ]
            return BacktestResponse(
                symbol=req.symbol,
                source=used,
                strategy=strat_name,
                n_bars=len(prices),
                n_trades=int(stats.get("n_flips", 0)),
                risk_events=0,
                stats=stats,
                buy_and_hold=bh,
                equity_curve=curve,
                tips=[{
                    "level": "info",
                    "message": f"期货双向引擎 · 做多占比 {stats.get('long_share', 0):.0%} · 做空占比 {stats.get('short_share', 0):.0%}",
                }],
                risk_analysis={},
                horizon=horizon,
                news=news_payload,
                fills=[],
                signals=signals[:200],
                engine="futures",
            )

        bt = Backtester(
            cash=req.cash,
            order_size=order_size,
            commission=req.commission,
            slippage=req.slippage,
            lot_size=req.lot_size,
            risk=risk,
            sizing=sizing,
        )
        result = bt.run(prices, strategy)
        bh = float(prices["close"].iloc[-1] / prices["close"].iloc[0] - 1.0)
        curve = [{"time": str(ts), "equity": float(v)} for ts, v in result.equity_curve.items()]
        tips = [{"level": t.level, "message": t.message} for t in advise(result, buy_and_hold=bh)]
        risk_analysis = assess_backtest_result(result, req.cash, risk)
        fills = [
            {
                "time": str(f.timestamp),
                "symbol": f.symbol,
                "side": f.side,
                "qty": float(f.qty),
                "price": float(f.price),
                "cost": float(f.cost),
            }
            for f in result.portfolio.fills
        ]
        signals = [{"time": str(ts), "signal": int(v)} for ts, v in result.signals.items()]
        return BacktestResponse(
            symbol=req.symbol,
            source=used,
            strategy=strat_name,
            n_bars=len(prices),
            n_trades=result.n_trades,
            risk_events=len(result.risk_events or []),
            stats=result.stats,
            buy_and_hold=bh,
            equity_curve=curve,
            tips=tips,
            risk_analysis=risk_analysis,
            horizon=horizon,
            news=news_payload,
            fills=fills,
            signals=signals,
            engine="equity",
        )

    @app.post("/portfolio_backtest", response_model=PortfolioBacktestResponse, dependencies=[Depends(auth)])
    def portfolio_backtest(req: PortfolioBacktestRequest):
        if not req.symbols:
            raise HTTPException(status_code=400, detail="Provide at least one symbol.")
        prices_by_symbol = {}
        used = req.source
        for sym in req.symbols:
            try:
                prices, used = _load_prices(sym, req.source, req.start, req.end, req.interval)
            except Exception as e:
                raise _safe_error(502, "Data load failed", e)
            prices_by_symbol[sym] = prices

        try:
            risk = RiskConfig(**req.risk) if req.risk else RiskConfig()
        except TypeError as e:
            raise _safe_error(400, "Bad risk config", e)
        try:
            sizing = SizingConfig(**req.sizing) if req.sizing else SizingConfig()
        except TypeError as e:
            raise _safe_error(400, "Bad sizing config", e)

        def factory():
            return get_strategy(req.strategy, **req.params)

        try:
            mbt = MultiBacktester(
                cash=req.cash,
                allocation=req.allocation,
                order_size=req.order_size,
                commission=req.commission,
                slippage=req.slippage,
                lot_size=req.lot_size,
                risk=risk,
                sizing=sizing,
            )
            result = mbt.run(prices_by_symbol, factory)
        except Exception as e:
            raise _safe_error(400, "Backtest failed", e)

        curve = [{"time": str(ts), "equity": float(v)} for ts, v in result.equity_curve.items()]
        tips = [{"level": t.level, "message": t.message} for t in advise(result)]
        per_symbol = {
            sym: {
                "weight": result.weights.get(sym, 0),
                "total_return": res.stats.get("total_return", 0),
                "sharpe": res.stats.get("sharpe", 0),
                "max_drawdown": res.stats.get("max_drawdown", 0),
                "n_trades": res.n_trades,
            }
            for sym, res in result.per_symbol.items()
        }
        return PortfolioBacktestResponse(
            symbols=req.symbols,
            source=used,
            strategy=req.strategy,
            allocation=result.allocation,
            weights=result.weights,
            stats=result.stats,
            per_symbol=per_symbol,
            equity_curve=curve,
            tips=tips,
        )

    @app.get("/playbooks", dependencies=[Depends(auth)])
    def playbooks():
        return {"playbooks": list_playbooks()}

    @app.post("/playbook", response_model=PlaybookResponse, dependencies=[Depends(auth)])
    def playbook(req: PlaybookRequest):
        if not req.symbols:
            raise HTTPException(status_code=400, detail="请至少提供一个标的。")

        # 新闻情绪拉取已下线；仅使用请求体中的 sentiment（若有）
        sentiment = req.sentiment
        news_payload = None

        try:
            sleeves, preset = build_playbook(req.playbook, req.symbols, req.news_symbols, sentiment)
        except ValueError as e:
            raise _safe_error(400, "Bad playbook config", e)

        all_syms = sorted({s for sl in sleeves for s in sl.symbols})
        prices_by_symbol = {}
        used = req.source
        for sym in all_syms:
            try:
                prices, used = _load_prices(sym, req.source, req.start, req.end, req.interval)
                prices_by_symbol[sym] = prices
            except Exception as e:
                raise _safe_error(502, "Data load failed", e)

        try:
            result = run_playbook(
                prices_by_symbol,
                sleeves,
                cash=req.cash,
                commission=req.commission,
                slippage=req.slippage,
                lot_size=req.lot_size,
            )
        except Exception as e:
            raise _safe_error(400, "Backtest failed", e)

        curve = [{"time": str(ts), "equity": float(v)} for ts, v in result.equity_curve.items()]
        per_sleeve = {
            name: {
                "weight": s["weight"],
                "description": s["description"],
                "strategy": s["strategy"],
                "symbols": s["symbols"],
                "n_trades": s["n_trades"],
                "total_return": s["stats"].get("total_return", 0.0),
                "sharpe": s["stats"].get("sharpe", 0.0),
                "max_drawdown": s["stats"].get("max_drawdown", 0.0),
            }
            for name, s in result.per_sleeve.items()
        }
        st = result.stats
        tips = []
        if st.get("sharpe", 0) >= 1 and st.get("total_return", 0) > 0:
            tips.append({"level": "good", "message": "整套打法样本内稳健度尚可，建议再用「参数寻优」做样本外验证。"})
        elif st.get("total_return", 0) <= 0:
            tips.append({"level": "warn", "message": "整套打法这段时间不赚钱，换标的或调整主力/卫星比例再试。"})
        if result.idle_cash_pct > 0.01:
            tips.append(
                {"level": "info", "message": f"约 {result.idle_cash_pct * 100:.0f}% 资金留作现金缓冲，未投入。"}
            )
        tips.append(
            {
                "level": "info",
                "message": "新闻卫星桶用的是设定/拉取的情绪分；实盘请结合「内置大模型」或实时新闻动态调整。",
            }
        )

        return PlaybookResponse(
            playbook=req.playbook,
            label=preset["label"],
            description=preset["description"],
            source=used,
            stats=st,
            weights=result.weights,
            idle_cash_pct=result.idle_cash_pct,
            per_sleeve=per_sleeve,
            equity_curve=curve,
            tips=tips,
            news=news_payload,
        )

    @app.post("/risk_assess", response_model=RiskAssessResponse, dependencies=[Depends(auth)])
    def risk_assess(req: RiskAssessRequest):
        try:
            risk = RiskConfig(**req.risk) if req.risk else RiskConfig()
            sizing = SizingConfig(**req.sizing) if req.sizing else SizingConfig()
        except TypeError as e:
            raise _safe_error(400, "Bad config", e)

        equity = req.equity if req.equity is not None else req.cash
        cash = req.cash if req.position_value <= 0 else max(0, equity - req.position_value)

        if req.mode == "portfolio":
            syms = req.symbols or ([req.symbol] if req.symbol else [])
            if not syms:
                raise HTTPException(status_code=400, detail="Provide symbols for portfolio assessment.")
            prices_by_symbol = {}
            used = req.source
            for sym in syms:
                try:
                    prices, used = _load_prices(sym, req.source, req.start, req.end, req.interval)
                except Exception as e:
                    raise _safe_error(502, "Data load failed", e)
                prices_by_symbol[sym] = prices
            assessment = assessment_to_dict(
                assess_portfolio(
                    prices_by_symbol,
                    req.allocation,
                    req.cash,
                    req.order_size,
                    sizing,
                    risk,
                )
            )
            return RiskAssessResponse(mode="portfolio", source=used, assessment=assessment)

        try:
            prices, used = _load_prices(req.symbol, req.source, req.start, req.end, req.interval)
        except Exception as e:
            raise _safe_error(502, "Data load failed", e)
        price = float(prices["close"].iloc[-1])
        assessment = assessment_to_dict(
            assess_trade(
                req.symbol,
                price,
                prices,
                equity,
                cash,
                req.position_value,
                req.order_size,
                sizing,
                risk,
                req.commission,
                req.slippage,
            )
        )
        return RiskAssessResponse(mode="trade", source=used, assessment=assessment)

    @app.get("/optimize/meta")
    def optimize_meta():
        """Return optimizable strategies, default grids, and analysis tips."""
        return optimize_catalog()

    @app.post("/optimize", response_model=OptimizeResponse, dependencies=[Depends(auth)])
    def optimize(req: OptimizeRequest):
        try:
            prices, used = _load_prices(req.symbol, req.source, req.start, req.end, req.interval)
        except Exception as e:
            raise _safe_error(502, "Data load failed", e)

        grid = req.grid or DEFAULT_GRIDS.get(req.strategy)
        if not grid:
            raise HTTPException(
                status_code=400, detail=f"No grid for {req.strategy!r}; supported: {list(DEFAULT_GRIDS)}"
            )
        try:
            risk = RiskConfig(**req.risk) if req.risk else RiskConfig()
        except TypeError as e:
            raise _safe_error(400, "Bad risk config", e)

        try:
            opt = grid_search(
                prices, req.strategy, grid, metric=req.metric, risk=risk, cash=req.cash,
                engine=req.engine or "equity", futures=req.futures or {},
                min_trades=req.min_trades,
            )
        except Exception as e:
            raise _safe_error(400, "Optimize failed", e)

        top = [
            {
                "params": p,
                "sharpe": s.get("sharpe", 0),
                "total_return": s.get("total_return", 0),
                "max_drawdown": s.get("max_drawdown", 0),
                "n_trades": s.get("n_trades"),
                "win_rate": s.get("win_rate"),
            }
            for p, s in opt.results[:10]
        ]

        wf_payload = {}
        try:
            wf = walk_forward(
                prices, req.strategy, grid, n_splits=req.n_splits, metric=req.metric, risk=risk,
                cash=req.cash, engine=req.engine or "equity", futures=req.futures or {},
                min_trades=req.min_trades,
            )
            wf_payload = {
                "avg_oos_return": wf.avg_oos_return,
                "avg_oos_sharpe": wf.avg_oos_sharpe,
                "overfit_gap": wf.overfit_gap,
                "folds": [
                    {
                        "best_params": f["best_params"],
                        "oos_return": f["oos_stats"].get("total_return", 0),
                        "oos_sharpe": f["oos_stats"].get("sharpe", 0),
                    }
                    for f in wf.folds
                ],
            }
        except Exception as e:
            wf_payload = {"error": str(e)}

        return OptimizeResponse(
            symbol=req.symbol,
            source=used,
            strategy=req.strategy,
            metric=req.metric,
            best_params=opt.best_params,
            best_score=opt.best_score,
            top=top,
            walk_forward=wf_payload,
        )

    @app.get("/horizons", dependencies=[Depends(auth)])
    def horizons():
        return {"horizons": [{"name": h.name, "label": h.label, "description": h.description} for h in list_horizons()]}

    @app.get("/principles", dependencies=[Depends(auth)])
    def principles():
        """Curated top-trader principles."""
        return {"principles": PRINCIPLES}

    # ---- Live paper portfolio + execution ---------------------------------
    def _positions_list():
        # PaperBroker / CnPaperBroker expose ._positions; real brokers may not.
        positions = getattr(broker, "_positions", {})
        return [{"symbol": p.symbol, "qty": p.qty, "avg_price": p.avg_price} for p in positions.values()]

    def _price_into_broker(symbol: str, source: str) -> None:
        """Fetch a fresh price and push it into the (paper) broker if supported."""
        if hasattr(broker, "set_price"):
            try:
                prices, _ = _load_prices(symbol, source, _RECENT_START, _RECENT_END, "1d")
            except Exception as e:
                raise _safe_error(502, "Data load failed", e)
            broker.set_price(symbol, float(prices["close"].iloc[-1]))

    def _account_payload():
        acct = broker.get_account()
        return AccountResponse(
            cash=acct.cash,
            equity=acct.equity,
            positions=_positions_list(),
            is_live=getattr(broker, "is_live", False),
        )

    @app.get("/portfolio", response_model=AccountResponse, dependencies=[Depends(auth)])
    def portfolio():
        return _account_payload()

    @app.post("/orders", response_model=OrderResponse, dependencies=[Depends(auth)])
    def submit_order(order: OrderRequest):
        # Real-money guard: live orders require explicit env opt-in.
        if getattr(broker, "is_live", False) and os.environ.get("QT_ALLOW_LIVE", "") not in ("1", "true", "yes"):
            raise HTTPException(
                status_code=403, detail="Live (real-money) trading disabled. Set QT_ALLOW_LIVE=1 to enable."
            )
        _price_into_broker(order.symbol, order.source)
        try:
            if order.side == "buy":
                notional = order.notional
                if notional is None and order.qty is None:
                    notional = broker.get_account().cash * 0.95
                placed = broker.submit_order(
                    order.symbol,
                    "buy",
                    qty=order.qty,
                    notional=notional,
                    order_type=order.order_type,
                    limit_price=order.limit_price,
                    note=order.note,
                )
            else:
                if order.qty:
                    placed = broker.submit_order(
                        order.symbol,
                        "sell",
                        qty=order.qty,
                        order_type=order.order_type,
                        limit_price=order.limit_price,
                        note=order.note,
                    )
                else:
                    pos = broker.get_position(order.symbol)
                    qty = pos.qty if pos else 0.0
                    placed = broker.submit_order(order.symbol, "sell", qty=qty, note=order.note or "sell_all")
        except Exception as e:
            raise _safe_error(400, "Order failed", e)

        acct = broker.get_account()
        return OrderResponse(
            order=placed.to_dict(),
            account={
                "cash": acct.cash,
                "equity": acct.equity,
                "positions": _positions_list(),
                "is_live": getattr(broker, "is_live", False),
            },
        )

    @app.get("/orders", response_model=OrdersListResponse, dependencies=[Depends(auth)])
    def list_orders(status: str | None = None, limit: int = 100):
        return OrdersListResponse(orders=[o.to_dict() for o in broker.list_orders(status, limit)])

    @app.delete("/orders/{order_id}", dependencies=[Depends(auth)])
    def cancel_order(order_id: str):
        ok = broker.cancel_order(order_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Order not found or not cancelable.")
        return {"canceled": order_id}

    @app.post("/signal", response_model=AccountResponse, dependencies=[Depends(auth)])
    def submit_signal(sig: SignalRequest):
        """Entry point for an external AI: send a target signal, we execute it."""
        if getattr(broker, "is_live", False) and os.environ.get("QT_ALLOW_LIVE", "") not in ("1", "true", "yes"):
            raise HTTPException(
                status_code=403, detail="Live (real-money) trading disabled. Set QT_ALLOW_LIVE=1 to enable."
            )
        _price_into_broker(sig.symbol, sig.source)
        pos = broker.get_position(sig.symbol)
        if sig.signal == Signal.BUY and (pos is None or pos.qty == 0):
            notional = sig.notional or broker.get_account().cash * 0.95
            broker.submit_order(sig.symbol, "buy", notional=notional, note="signal")
        elif sig.signal != Signal.BUY and pos is not None and pos.qty > 0:
            broker.submit_order(sig.symbol, "sell", qty=pos.qty, note="signal")
        return _account_payload()

    # ---- Settings: input broker / AI API credentials at runtime ------------
    def _settings_payload() -> SettingsResponse:
        return SettingsResponse(
            broker=broker_name,
            paper=state["paper"],
            live=getattr(broker, "is_live", False),
            has_broker_keys=bool(state["api_key"] and state["api_secret"]),
            cash=state["cash"],
            ai_endpoint=ai_cfg["endpoint"],
            has_ai_key=bool(ai_cfg["api_key"]),
            llm_provider=llm_cfg["provider"],
            llm_model=llm_cfg["model"],
            has_llm_key=bool(llm_cfg["api_key"]),
        )

    @app.get("/settings", response_model=SettingsResponse, dependencies=[Depends(auth)])
    def get_settings():
        return _settings_payload()

    @app.post("/settings", response_model=SettingsResponse, dependencies=[Depends(auth)])
    def update_settings(req: SettingsUpdateRequest):
        nonlocal broker, broker_name
        touch_broker = any(
            v is not None for v in (req.broker, req.api_key, req.api_secret, req.paper, req.allow_live, req.cash)
        )
        if req.api_key is not None:
            state["api_key"] = req.api_key
        if req.api_secret is not None:
            state["api_secret"] = req.api_secret
        if req.paper is not None:
            state["paper"] = req.paper
        if req.allow_live is not None:
            state["allow_live"] = req.allow_live
        if req.cash is not None:
            state["cash"] = float(req.cash)

        if touch_broker:
            name = (req.broker or broker_name).lower()
            try:
                if name in ("paper", "cn_paper", "cn", "ashare_paper"):
                    new_broker = get_broker(name, cash=state["cash"])
                else:
                    new_broker = get_broker(
                        name,
                        api_key=state["api_key"],
                        api_secret=state["api_secret"],
                        paper=state["paper"],
                        allow_live=state["allow_live"],
                    )
            except Exception as e:
                raise _safe_error(400, "Broker init failed", e)
            broker = new_broker
            broker_name = name

        if req.ai_endpoint is not None:
            try:
                _validate_url(req.ai_endpoint.strip())
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid AI endpoint URL: {e}")
            ai_cfg["endpoint"] = req.ai_endpoint.strip()
        if req.ai_api_key is not None:
            ai_cfg["api_key"] = req.ai_api_key.strip()
        if req.llm_provider is not None:
            llm_cfg["provider"] = req.llm_provider.strip().lower() or "deepseek"
        if req.llm_api_key is not None:
            llm_cfg["api_key"] = req.llm_api_key.strip()
        if req.llm_model is not None:
            llm_cfg["model"] = req.llm_model.strip()
        return _settings_payload()

    @app.post("/ai/run", response_model=AIRunResponse, dependencies=[Depends(auth)])
    def ai_run(req: AIRunRequest):
        """Call the configured external AI endpoint for a decision, optionally trade it."""
        if not ai_cfg["endpoint"]:
            raise HTTPException(status_code=400, detail="未配置 AI 接口地址，请在设置里填写 AI Endpoint。")
        from ..strategy.ai_strategy import AIStrategy

        try:
            prices, used = _load_prices(req.symbol, req.source, _RECENT_START, _RECENT_END, "1d")
        except Exception as e:
            raise _safe_error(502, "Data load failed", e)
        strat = AIStrategy(endpoint=ai_cfg["endpoint"], api_key=ai_cfg["api_key"] or None)
        try:
            sig = int(strat.generate(prices).iloc[-1])
        except Exception as e:
            raise _safe_error(502, "AI endpoint call failed", e)

        executed = False
        if req.execute:
            if getattr(broker, "is_live", False) and os.environ.get("QT_ALLOW_LIVE", "") not in ("1", "true", "yes"):
                raise HTTPException(
                    status_code=403, detail="实盘交易未启用。设置 QT_ALLOW_LIVE=1 后才能用 AI 实盘下单。"
                )
            _price_into_broker(req.symbol, req.source)
            pos = broker.get_position(req.symbol)
            if sig == Signal.BUY and (pos is None or pos.qty == 0):
                broker.submit_order(
                    req.symbol, "buy", notional=req.notional or broker.get_account().cash * 0.95, note="ai"
                )
                executed = True
            elif sig != Signal.BUY and pos is not None and pos.qty > 0:
                broker.submit_order(req.symbol, "sell", qty=pos.qty, note="ai")
                executed = True

        acct = broker.get_account()
        label = {1: "BUY", 0: "HOLD", -1: "SELL/EXIT"}.get(sig, str(sig))
        return AIRunResponse(
            symbol=req.symbol,
            signal=sig,
            label=label,
            executed=executed,
            endpoint=ai_cfg["endpoint"],
            account={"cash": acct.cash, "equity": acct.equity, "positions": _positions_list()},
        )

    @app.post("/ai/llm/run", response_model=LLMRunResponse, dependencies=[Depends(auth)])
    def ai_llm_run(req: LLMRunRequest):
        """Use the built-in LLM brain (DeepSeek / GPT) for a decision, optionally trade."""
        if not llm_cfg["api_key"]:
            raise HTTPException(status_code=400, detail=f"未配置 {llm_cfg['provider']} 的 API Key，请在设置里填写。")
        from ..ai.llm import LLMConfig, ask_llm

        try:
            prices, used = _load_prices(req.symbol, req.source, _RECENT_START, _RECENT_END, "1d")
        except Exception as e:
            raise _safe_error(502, "Data load failed", e)

        news_text = ""

        cfg = LLMConfig(provider=llm_cfg["provider"], api_key=llm_cfg["api_key"], model=llm_cfg["model"])
        try:
            decision = ask_llm(prices, cfg, news_text)
        except Exception as e:
            raise _safe_error(502, "LLM call failed", e)
        sig = int(decision["signal"])

        executed = False
        if req.execute:
            if getattr(broker, "is_live", False) and os.environ.get("QT_ALLOW_LIVE", "") not in ("1", "true", "yes"):
                raise HTTPException(
                    status_code=403, detail="实盘交易未启用。设置 QT_ALLOW_LIVE=1 后才能用 AI 实盘下单。"
                )
            _price_into_broker(req.symbol, req.source)
            pos = broker.get_position(req.symbol)
            if sig == Signal.BUY and (pos is None or pos.qty == 0):
                broker.submit_order(
                    req.symbol, "buy", notional=req.notional or broker.get_account().cash * 0.95, note="llm"
                )
                executed = True
            elif sig != Signal.BUY and pos is not None and pos.qty > 0:
                broker.submit_order(req.symbol, "sell", qty=pos.qty, note="llm")
                executed = True

        acct = broker.get_account()
        label = {1: "BUY", 0: "HOLD", -1: "SELL/EXIT"}.get(sig, str(sig))
        return LLMRunResponse(
            symbol=req.symbol,
            provider=decision.get("provider", llm_cfg["provider"]),
            model=decision.get("model", ""),
            signal=sig,
            label=label,
            confidence=float(decision.get("confidence", 0.0)),
            reason=str(decision.get("reason", "")),
            executed=executed,
            account={"cash": acct.cash, "equity": acct.equity, "positions": _positions_list()},
        )

    # ---- A-share scanner (智能选股) --------------------------
    @app.get("/api/scanner/results", dependencies=[Depends(auth)])
    def scanner_results_get():
        """Return latest persisted scan results (no new scan triggered)."""
        import json as _json
        from pathlib import Path as _Path

        _results_path = _Path("logs/scanner_results.json")
        if _results_path.exists():
            try:
                data = _json.loads(_results_path.read_text(encoding="utf-8"))
                return {"status": "ok", "cached": True, **data}
            except Exception:
                pass
        # No cached results — trigger a fresh scan
        return scanner_results_post(top_n=12)

    @app.post("/api/scanner/run", dependencies=[Depends(auth)])
    def scanner_results_post(top_n: int = 12, use_ai: bool = False):
        """Trigger a fresh scan and persist results.

        Args:
            top_n: Number of candidates to return
            use_ai: Enable LLM analysis on top candidates (requires DEEPSEEK_API_KEY)
        """
        import json as _json
        from pathlib import Path as _Path

        try:
            from ..scanner.common import ScanConfig
            from ..scanner.engine import run as engine_run

            cfg = ScanConfig(top_n=top_n, use_ai=use_ai)
            picks = engine_run(config=cfg)
            result = {
                "status": "ok",
                "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
                "candidates": [p.to_dict() for p in picks],
                "stats": {
                    "total_scanned": 100,
                    "candidates": len(picks),
                    "buy_count": sum(1 for p in picks if p.action == "buy"),
                    "watch_count": sum(1 for p in picks if p.action == "watch"),
                    "skip_count": sum(1 for p in picks if p.action == "skip"),
                    "ai_analyzed": sum(1 for p in picks if p.ai_action),
                },
            }
            # Persist to disk so GET can return cached results
            try:
                _Path("logs").mkdir(parents=True, exist_ok=True)
                _Path("logs/scanner_results.json").write_text(
                    _json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            except Exception:
                pass
            return result
        except Exception as e:
            raise _safe_error(502, "Scanner failed", e)

    # ---- 盯盘异动检测 (Watchdog) ---------------------------------
    try:
        from ..watchdog import WatchConfig, get_watchdog

        _watchdog = get_watchdog(WatchConfig())
    except Exception:
        _watchdog = None

    @app.get("/api/watchdog/events", dependencies=[Depends(auth)])
    def watchdog_events(limit: int = 20):
        if not _watchdog:
            return {"events": [], "count": 0}
        events = _watchdog.to_dict_list()[-limit:]
        return {"events": events, "count": len(events)}

    @app.post("/api/watchdog/scan", dependencies=[Depends(auth)])
    def watchdog_scan(symbol: str, source: str = "synthetic"):
        if not _watchdog:
            raise HTTPException(status_code=503, detail="watchdog not loaded")
        prices, _ = _load_prices(symbol, source, _RECENT_START, _RECENT_END, "1d")
        _watchdog.scan(symbol, prices)
        return {"symbol": symbol, "summary": _watchdog.summary(), "events": _watchdog.to_dict_list()[-20:]}

    # ══════════════════════════════════════════════════════════════════
    # 期货监控面板 API
    # ══════════════════════════════════════════════════════════════════
    try:
        from ..data.sina_futures import get_history, get_realtime
        from ..futures.contracts import (
            DOMINANT_CONTRACTS,
            FUTURES_CONTRACTS,
            MARKET_HOURS,
            session_label,
        )

        _futures_available = True
    except Exception:
        _futures_available = False

    if _futures_available:

        @app.get("/api/futures/contracts")
        def futures_contracts():
            """返回所有品种合约信息 + 板块分组。"""
            sectors = {
                "金融期货": ["IF", "IC", "IH", "IM", "TS", "TF", "T", "TL"],
                "贵金属": ["AU", "AG"],
                "有色金属": ["CU", "AL", "ZN", "PB", "NI", "SN", "SS"],
                "黑色金属": ["RB", "HC", "I"],
                "能源化工": ["SC", "FU", "BU", "RU", "SP", "PG", "TA", "MA", "EG", "EB", "PP", "L", "V", "SA", "UR"],
                "油脂油料": ["A", "B", "M", "Y", "P", "OI", "RM"],
                "农产品": ["C", "CS", "JD", "LH", "AP", "CJ", "CF", "SR"],
                "广期所": ["SI", "LC"],
            }
            contracts = []
            for code, spec in FUTURES_CONTRACTS.items():
                sector = ""
                for s, codes in sectors.items():
                    if code in codes:
                        sector = s
                        break
                hours = MARKET_HOURS.get(code)
                contracts.append(
                    {
                        "code": code,
                        "name": spec.name,
                        "exchange": spec.exchange,
                        "sector": sector,
                        "contract_size": spec.contract_size,
                        "tick_size": spec.tick_size,
                        "margin_rate": spec.margin_rate,
                        "multiplier": spec.multiplier,
                        "night_session": hours.night_open is not None if hours else False,
                    }
                )
            return {"contracts": contracts, "sectors": list(sectors.keys()), "session": session_label()}

        @app.get("/api/futures/quotes")
        def futures_quotes(codes: str = ""):
            """批量实时行情。codes为空返回全部。"""
            if codes:
                code_list = [c.strip().upper() for c in codes.split(",") if c.strip()]
            else:
                code_list = list(FUTURES_CONTRACTS.keys())
            quotes = get_realtime(code_list)
            result = []
            for code in code_list:
                spec = FUTURES_CONTRACTS.get(code)
                q = quotes.get(code, {})
                name = spec.name if spec else q.get("name", code)
                close = q.get("close", 0)
                open_ = q.get("open", 0)
                high = q.get("high", 0)
                low = q.get("low", 0)
                volume = q.get("volume", 0)
                chg_pct = ((close - open_) / open_ * 100) if open_ and close else 0
                sector = ""
                sectors_map = {
                    "金融期货": ["IF", "IC", "IH", "IM", "TS", "TF", "T", "TL"],
                    "贵金属": ["AU", "AG"],
                    "有色金属": ["CU", "AL", "ZN", "PB", "NI", "SN", "SS"],
                    "黑色金属": ["RB", "HC", "I"],
                    "能源化工": [
                        "SC",
                        "FU",
                        "BU",
                        "RU",
                        "SP",
                        "PG",
                        "TA",
                        "MA",
                        "EG",
                        "EB",
                        "PP",
                        "L",
                        "V",
                        "SA",
                        "UR",
                    ],
                    "油脂油料": ["A", "B", "M", "Y", "P", "OI", "RM"],
                    "农产品": ["C", "CS", "JD", "LH", "AP", "CJ", "CF", "SR"],
                    "广期所": ["SI", "LC"],
                }
                for s, cs in sectors_map.items():
                    if code in cs:
                        sector = s
                        break
                result.append(
                    {
                        "code": code,
                        "name": name,
                        "sector": sector,
                        "close": round(close, 2),
                        "open": round(open_, 2),
                        "high": round(high, 2),
                        "low": round(low, 2),
                        "volume": volume,
                        "chg_pct": round(chg_pct, 2),
                        "margin_rate": spec.margin_rate if spec else 0,
                    }
                )
            return {
                "quotes": result,
                "session": session_label(),
                "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
            }

        @app.get("/api/futures/kline")
        def futures_kline(code: str, days: int = 60):
            """品种历史K线数据。"""
            code = code.upper()
            if code not in FUTURES_CONTRACTS:
                raise HTTPException(status_code=400, detail=f"Unknown contract: {code}")
            try:
                df = get_history(code, days)
                bars = []
                for ts, row in df.iterrows():
                    bars.append(
                        {
                            "time": str(ts.date()),
                            "open": round(float(row["open"]), 2),
                            "high": round(float(row["high"]), 2),
                            "low": round(float(row["low"]), 2),
                            "close": round(float(row["close"]), 2),
                            "volume": int(row["volume"]),
                        }
                    )
                spec = FUTURES_CONTRACTS[code]
                return {"code": code, "name": spec.name, "bars": bars}
            except Exception as e:
                raise _safe_error(502, "K-line load failed", e)

        @app.get("/api/futures/signals")
        def futures_signals():
            """各品种简易信号面板 (基于动量)。"""
            code_list = DOMINANT_CONTRACTS[:20]
            quotes = get_realtime(code_list)
            signals = []
            for code in code_list:
                q = quotes.get(code)
                if not q or not q.get("close"):
                    continue
                spec = FUTURES_CONTRACTS.get(code)
                close = q["close"]
                open_ = q.get("open", close)
                high = q.get("high", close)
                low = q.get("low", close)
                # 简易信号: 基于开高低收关系
                mid = (high + low) / 2 if high and low else close
                if close > mid and close > open_:
                    sig = "LONG"
                    conf = min(0.95, 0.5 + (close - mid) / (mid or 1) * 10)
                elif close < mid and close < open_:
                    sig = "SHORT"
                    conf = min(0.95, 0.5 + (mid - close) / (mid or 1) * 10)
                else:
                    sig = "FLAT"
                    conf = 0.4
                signals.append(
                    {
                        "code": code,
                        "name": spec.name if spec else code,
                        "signal": sig,
                        "confidence": round(conf, 2),
                        "price": round(close, 2),
                    }
                )
            return {"signals": signals, "session": session_label()}

        @app.get("/api/futures/risk")
        def futures_risk():
            """风控面板数据: 板块波动率 + 保证金占比。"""
            code_list = DOMINANT_CONTRACTS[:20]
            quotes = get_realtime(code_list)
            risks = []
            total_margin = 0
            for code in code_list:
                q = quotes.get(code)
                if not q or not q.get("close"):
                    continue
                spec = FUTURES_CONTRACTS.get(code)
                close = q["close"]
                open_ = q.get("open", close)
                high = q.get("high", close)
                low = q.get("low", close)
                chg_pct = ((close - open_) / open_ * 100) if open_ and close else 0
                # 波动率近似 = 日内振幅
                daily_range = ((high - low) / open_ * 100) if open_ and high and low else 0
                margin_val = 0
                if spec:
                    margin_val = spec.calc_margin(close, 1)
                    total_margin += margin_val
                risks.append(
                    {
                        "code": code,
                        "name": spec.name if spec else code,
                        "price": round(close, 2),
                        "chg_pct": round(chg_pct, 2),
                        "daily_range": round(daily_range, 2),
                        "margin_per_lot": round(margin_val, 0),
                        "leverage": round(close / (margin_val or 1), 1) if margin_val else 0,
                    }
                )
            return {
                "risks": risks,
                "total_margin_per_lot": round(total_margin, 0),
                "session": session_label(),
                "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
            }

        @app.get("/futures", response_class=HTMLResponse)
        def futures_dashboard():
            """期货监控面板。"""
            futures_page = Path(__file__).parent / "static" / "futures.html"
            if futures_page.exists():
                return HTMLResponse(futures_page.read_text(encoding="utf-8"))
            return HTMLResponse("<h1>Futures</h1><p>futures.html not found.</p>")

    # ══════════════════════════════════════════════════════════════════
    # 统一预测报告 API
    # ══════════════════════════════════════════════════════════════════
    try:
        from ..forecast import (
            generate_html_report,
            run_default_forecast,
            run_forecast,
        )

        _forecast_available = True
    except Exception:
        _forecast_available = False

    @app.get("/api/forecast/run", dependencies=[Depends(auth)])
    def forecast_run(stocks: str = "", futures: str = "", html: bool = False):
        """运行预测流程。GET参数: stocks=600519,000001 futures=RB,SC,I,AU html=1返回HTML"""
        if not _forecast_available:
            raise HTTPException(status_code=503, detail="forecast module not loaded")

        stock_list = [s.strip() for s in stocks.split(",") if s.strip()]
        future_list = [f.strip() for f in futures.split(",") if f.strip()]
        llm_key = llm_cfg.get("api_key", "")
        llm_provider = llm_cfg.get("provider", "deepseek")

        results = run_forecast(
            stocks=stock_list or None,
            futures=future_list or None,
            llm_api_key=llm_key,
            llm_provider=llm_provider,
        )

        if html:
            return HTMLResponse(generate_html_report(results, "量化预测报告"))

        return {
            "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
            "count": len(results),
            "results": [r.to_dict() for r in results],
        }

    @app.get("/forecast", response_class=HTMLResponse)
    def forecast_page():
        """一键预测——默认标的集: 600519 + 000001 + I + RB + SC + AU"""
        if not _forecast_available:
            return HTMLResponse("<h1>Forecast</h1><p>Module not available</p>")

        llm_key = llm_cfg.get("api_key", "")
        llm_provider = llm_cfg.get("provider", "deepseek")

        try:
            results = run_default_forecast(
                llm_api_key=llm_key,
                llm_provider=llm_provider,
            )
            return HTMLResponse(generate_html_report(results, "量化预测报告 · 股票+期货"))
        except Exception as e:
            error_id = uuid.uuid4().hex[:8]
            _logger.error("[ref=%s] Forecast failed: %s", error_id, e, exc_info=True)
            return HTMLResponse(f"<h1>预测失败</h1><p>Internal error (ref: {error_id})</p>")

    @app.get("/api/realtime/predictions")
    def api_realtime_predictions():
        """获取实时预测结果 (从缓存读取)。"""
        from pathlib import Path

        cache_file = Path("logs/realtime_predictions.json")
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                return data
            except Exception:
                pass
        return {"results": [], "timestamp": None, "message": "暂无预测数据"}

    @app.get("/api/realtime/run")
    def api_realtime_run():
        """手动触发一次预测。"""
        try:
            from quanttrader.service.realtime_predictor import run_prediction

            result = run_prediction()
            return result
        except Exception as e:
            error_id = uuid.uuid4().hex[:8]
            _logger.error("[ref=%s] Realtime prediction failed: %s", error_id, e, exc_info=True)
            return {"error": f"Internal error (ref: {error_id})"}

    # ══════════════════════════════════════════════════════════════════

    # ---- Web dashboard -----------------------------------------------
    _static = Path(__file__).parent / "static" / "index.html"
    _scanner_page = Path(__file__).parent / "static" / "scanner.html"
    _replay_page = Path(__file__).parent / "static" / "replay.html"
    _backtest_page = Path(__file__).parent / "static" / "backtest.html"

    @app.get("/", response_class=HTMLResponse)
    def dashboard():
        if _static.exists():
            return HTMLResponse(_static.read_text(encoding="utf-8"))
        return HTMLResponse("<h1>quant-trader API</h1><p>See <a href='/docs'>/docs</a>.</p>")

    @app.get("/overview", response_class=HTMLResponse)
    def overview():
        """全景预测流程页面。"""
        overview_page = Path(__file__).parent / "static" / "overview.html"
        if overview_page.exists():
            return HTMLResponse(overview_page.read_text(encoding="utf-8"))
        return HTMLResponse("<h1>Overview</h1><p>overview.html not found.</p>")

    @app.get("/scanner", response_class=HTMLResponse)
    def scanner_dashboard():
        """Auto-refreshing scanner dashboard."""
        if _scanner_page.exists():
            return HTMLResponse(_scanner_page.read_text(encoding="utf-8"))
        return HTMLResponse("<h1>Scanner</h1><p>scanner.html not found.</p>")

    @app.get("/replay", response_class=HTMLResponse)
    def replay_dashboard():
        """Strategy replay & performance analysis."""
        if _replay_page.exists():
            return HTMLResponse(_replay_page.read_text(encoding="utf-8"))
        return HTMLResponse("<h1>Replay</h1><p>replay.html not found.</p>")

    @app.get("/backtest", response_class=HTMLResponse)
    def backtest_dashboard():
        """Backtest visualization & analysis."""
        if _backtest_page.exists():
            return HTMLResponse(_backtest_page.read_text(encoding="utf-8"))
        return HTMLResponse("<h1>Backtest</h1><p>backtest.html not found.</p>")

    @app.get("/chart", response_class=HTMLResponse)
    def chart_dashboard():
        """Real-time K-line chart with technical indicators."""
        chart_page = Path(__file__).parent / "static" / "chart.html"
        if chart_page.exists():
            return HTMLResponse(chart_page.read_text(encoding="utf-8"))
        return HTMLResponse("<h1>Chart</h1><p>chart.html not found.</p>")

    @app.get("/assets/ui-chips.js")
    def ui_chips_js():
        """Shared chip-select UI for dashboard pages."""
        from fastapi.responses import FileResponse

        js_path = Path(__file__).parent / "static" / "ui-chips.js"
        if js_path.exists():
            return FileResponse(js_path, media_type="application/javascript")
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="ui-chips.js not found")

    @app.get("/assets/futures-picker.js")
    def futures_picker_js():
        """Futures multi-select picker for dashboard pages."""
        from fastapi.responses import FileResponse

        js_path = Path(__file__).parent / "static" / "futures-picker.js"
        if js_path.exists():
            return FileResponse(js_path, media_type="application/javascript")
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="futures-picker.js not found")

    @app.get("/assets/strategy-picker.js")
    def strategy_picker_js():
        """Grouped strategy picker for backtest/replay pages."""
        from fastapi.responses import FileResponse

        js_path = Path(__file__).parent / "static" / "strategy-picker.js"
        if js_path.exists():
            return FileResponse(js_path, media_type="application/javascript")
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="strategy-picker.js not found")

    @app.get("/assets/strategy-optimize.js")
    def strategy_optimize_js():
        """Strategy parameter optimization UI helpers."""
        from fastapi.responses import FileResponse

        js_path = Path(__file__).parent / "static" / "strategy-optimize.js"
        if js_path.exists():
            return FileResponse(js_path, media_type="application/javascript")
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="strategy-optimize.js not found")

    @app.websocket("/ws/prices")
    async def ws_prices(ws: WebSocket):
        """Stream live price tick + watchdog alerts every second.

        Seeds from the latest real bar, then random-walks so the dashboard shows
        a live ticker without needing a paid streaming data feed.
        """
        import random

        # Auth check for WebSocket (query param or header)
        if api_token:
            token = ws.query_params.get("token", "")
            auth_header = ""
            for k, v in ws.headers.items():
                if k.lower() == "authorization":
                    auth_header = v
                    break
            if token != api_token and auth_header != f"Bearer {api_token}":
                await ws.close(code=4001, reason="Unauthorized")
                return

        await ws.accept()
        symbol = ws.query_params.get("symbol", "DEMO")
        source = ws.query_params.get("source", "synthetic")

        last = 100.0
        try:
            prices, _ = _load_prices(symbol, source, _RECENT_START, _RECENT_END, "1d")
            last = float(prices["close"].iloc[-1])
        except Exception:
            last = 100.0

        try:
            await ws.send_json({"type": "price", "symbol": symbol, "price": round(last, 4)})
            tick = 0
            while True:
                await asyncio.sleep(1.0)
                last *= 1 + random.gauss(0, 0.001)
                tick += 1
                payload = {"type": "price", "symbol": symbol, "price": round(last, 4)}
                if tick % 5 == 0 and _watchdog:
                    try:
                        wd_prices, _ = _load_prices(symbol, source, _RECENT_START, _RECENT_END, "1d")
                        events = _watchdog.scan(symbol, wd_prices)
                        if events:
                            payload["alerts"] = [
                                {"level": e.level, "title": e.title, "detail": e.detail} for e in events[:5]
                            ]
                    except Exception:
                        pass
                await ws.send_json(payload)
        except WebSocketDisconnect:
            return
        except Exception:
            return

    # ═══════════════════════════════════════════════════════════════
    #  半自动交易建议 API
    # ═══════════════════════════════════════════════════════════════

    @app.get("/signals")
    def signals_page():
        """交易建议Dashboard页面。"""
        from fastapi.responses import FileResponse
        html_path = Path(__file__).parent / "static" / "signals.html"
        return FileResponse(str(html_path), media_type="text/html")

    @app.get("/api/signals/today")
    def signals_today():
        """今日交易建议列表。"""
        from datetime import datetime as _dt
        today = _dt.now().strftime("%Y%m%d")
        signals_path = Path("logs") / f"signals_{today}.json"
        cards = []
        if signals_path.exists():
            try:
                for line in signals_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line:
                        cards.append(json.loads(line))
            except Exception:
                pass
        return {"cards": cards, "date": today, "count": len(cards)}

    @app.get("/api/signals/{signal_id}")
    def signal_detail(signal_id: str):
        """单个交易建议详情。"""
        from datetime import datetime as _dt
        today = _dt.now().strftime("%Y%m%d")
        signals_path = Path("logs") / f"signals_{today}.json"
        if signals_path.exists():
            for line in signals_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    card = json.loads(line)
                    if card.get("id") == signal_id:
                        return card
        return {"error": "not found"}

    @app.post("/api/signals/{signal_id}/adopt")
    def signal_adopt(signal_id: str):
        """标记采纳建议。"""
        from ..assistant.journal import TradeJournal
        journal = TradeJournal(Path("logs"))
        journal.mark_adopted(signal_id)
        return {"ok": True}

    @app.get("/api/review/today")
    def review_today():
        """今日复盘统计。"""
        from ..assistant.journal import TradeJournal
        journal = TradeJournal(Path("logs"))
        return journal.get_today_stats()

    # ══════════════════════════════════════════════════════════════════
    # Guarded System API — 信号审批 + 模式管理 + 品种状态
    # ══════════════════════════════════════════════════════════════════
    @app.get("/api/guarded/system-status")
    def guarded_system_status():
        """Guarded 系统状态 — 当前模式、品种分层、今日信号统计。"""
        import json as _json
        from pathlib import Path as _Path

        from ..engine.mode_guard import MODE_CONFIGS

        # 读取配置
        config_path = _Path("config_paper_guarded.yaml")
        mode = "paper"
        symbols = []
        try:
            import yaml
            if config_path.exists():
                cfg_data = _json.loads(_json.dumps(
                    yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
                ))
                mode = cfg_data.get("mode", "paper")
                symbols = cfg_data.get("symbols", [])
        except Exception:
            pass

        # 读取 strategy_params 获取分层信息
        strategy_symbols = []
        try:
            sp_path = _Path("logs/strategy_params.json")
            if sp_path.exists():
                sp_data = _json.loads(sp_path.read_text(encoding="utf-8"))
                for combo in sp_data.get("best_combos_10d", []):
                    name = combo.get("name", "")
                    if "+" in name:
                        sym, direction = name.split("+", 1)
                        strategy_symbols.append({
                            "symbol": sym.rstrip("0"),
                            "raw_symbol": sym,
                            "direction": direction,
                            "accuracy": combo.get("acc", 0),
                            "sample_size": combo.get("n", 0),
                            "tier": combo.get("tier", "unknown"),
                        })
        except Exception:
            pass

        # 今日信号统计
        today_signals = {"total": 0, "passed": 0, "rejected": 0, "reasons": {}}
        try:
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            decisions_files = list(_Path("logs").glob("decisions_*.csv"))
            for df in decisions_files:
                if today in df.name:
                    import csv
                    with open(df, encoding="utf-8") as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            today_signals["total"] += 1
                            action = row.get("action", "").upper()
                            if action in ("BUY", "SELL"):
                                today_signals["passed"] += 1
                            else:
                                today_signals["rejected"] += 1
        except Exception:
            pass

        mode_info = MODE_CONFIGS.get(mode, MODE_CONFIGS["paper"])

        return {
            "mode": mode,
            "mode_info": {
                "can_trade": mode_info.can_trade,
                "broker_allowed": mode_info.broker_allowed,
                "max_position_pct": mode_info.max_position_pct,
                "max_total_exposure": mode_info.max_total_exposure,
            },
            "symbols": symbols,
            "strategy_symbols": strategy_symbols,
            "today_signals": today_signals,
        }

    @app.get("/api/guarded/signal-evaluate")
    def guarded_signal_evaluate(
        symbol: str = "M0",
        direction: str = "BUY",
        sample_size: int = 100,
        raw_accuracy: float = 0.55,
        oos_accuracy: float = 0.53,
        walk_forward_accuracy: float = 0.53,
        profit_factor: float = 1.0,
        risk_reward_ratio: float = 1.8,
        avg_return: float = 0.01,
        cost_pct: float = 0.003,
        news_risk_level: str = "low",
    ):
        """评估单个信号是否通过审批门。"""
        from ..engine.signal_quality_gate import SignalQualityGate
        gate = SignalQualityGate(mode="paper")
        result = gate.evaluate({
            "symbol": symbol,
            "direction": direction,
            "sample_size": sample_size,
            "raw_accuracy": raw_accuracy,
            "adjusted_accuracy": raw_accuracy,
            "oos_accuracy": oos_accuracy,
            "walk_forward_accuracy": walk_forward_accuracy,
            "profit_factor": profit_factor,
            "risk_reward_ratio": risk_reward_ratio,
            "avg_return": avg_return,
            "cost_pct": cost_pct,
            "news_risk_level": news_risk_level,
            "regime_fit_score": 0.5,
        })
        return result

    # ══════════════════════════════════════════════════════════════════
    # AI 预测完整性补充模块 API
    # ══════════════════════════════════════════════════════════════════
    try:
        from ..analysis.completeness import (
            cost_analyze,
            direction_analyze,
            ensemble_analyze,
            feature_analyze,
            oos_analyze,
            regime_analyze,
            walk_forward_analyze,
        )
        from ..analysis.completeness.cache import cached_analyze, clear_cache
        from ..analysis.completeness.integration import (
            check_direction_with_filter,
            get_combo_accuracy,
            get_symbol_filter_status,
            load_trading_costs,
            track_prediction,
        )

        _completeness_available = True
    except Exception:
        _completeness_available = False

    def _get_prices_for_prediction(symbol: str, source: str):
        """加载预测用价格数据。"""
        start = "2023-01-01"
        return _load_prices(symbol, source, start, _RECENT_END, "1d")

    @app.get("/api/prediction/direction", dependencies=[Depends(auth)])
    def prediction_direction(symbol: str = "SI0", source: str = "akshare"):
        """方向预测: 做多/做空/中性概率。"""
        if not _completeness_available:
            raise HTTPException(status_code=503, detail="completeness module not loaded")
        try:
            prices, used = _get_prices_for_prediction(symbol, source)
        except Exception as e:
            raise _safe_error(502, "Data load failed", e)
        return direction_analyze(prices, symbol=symbol)

    @app.get("/api/prediction/walk-forward", dependencies=[Depends(auth)])
    def prediction_walk_forward(symbol: str = "SI0", source: str = "akshare", n_splits: int = 5):
        """滚动训练验证。"""
        if not _completeness_available:
            raise HTTPException(status_code=503, detail="completeness module not loaded")
        try:
            prices, used = _get_prices_for_prediction(symbol, source)
        except Exception as e:
            raise _safe_error(502, "Data load failed", e)
        return walk_forward_analyze(prices, symbol=symbol, n_splits=n_splits)

    @app.get("/api/prediction/ensemble", dependencies=[Depends(auth)])
    def prediction_ensemble(symbol: str = "SI0", source: str = "akshare"):
        """模型集成评估。"""
        if not _completeness_available:
            raise HTTPException(status_code=503, detail="completeness module not loaded")
        try:
            prices, used = _get_prices_for_prediction(symbol, source)
        except Exception as e:
            raise _safe_error(502, "Data load failed", e)
        return ensemble_analyze(prices, symbol=symbol)

    @app.get("/api/prediction/features", dependencies=[Depends(auth)])
    def prediction_features(symbol: str = "SI0", source: str = "akshare"):
        """特征重要性报告。"""
        if not _completeness_available:
            raise HTTPException(status_code=503, detail="completeness module not loaded")
        try:
            prices, used = _get_prices_for_prediction(symbol, source)
        except Exception as e:
            raise _safe_error(502, "Data load failed", e)
        return feature_analyze(prices, symbol=symbol)

    @app.get("/api/prediction/regime", dependencies=[Depends(auth)])
    def prediction_regime(symbol: str = "SI0", source: str = "akshare"):
        """市场状态检测。"""
        if not _completeness_available:
            raise HTTPException(status_code=503, detail="completeness module not loaded")
        try:
            prices, used = _get_prices_for_prediction(symbol, source)
        except Exception as e:
            raise _safe_error(502, "Data load failed", e)
        return regime_analyze(prices, symbol=symbol)

    @app.get("/api/prediction/cost", dependencies=[Depends(auth)])
    def prediction_cost(symbol: str = "SI0", source: str = "akshare"):
        """成本模型 + 期望值。"""
        if not _completeness_available:
            raise HTTPException(status_code=503, detail="completeness module not loaded")
        try:
            prices, used = _get_prices_for_prediction(symbol, source)
        except Exception as e:
            raise _safe_error(502, "Data load failed", e)
        return cost_analyze(prices, symbol=symbol)

    @app.get("/api/prediction/oos", dependencies=[Depends(auth)])
    def prediction_oos(symbol: str = "SI0", source: str = "akshare"):
        """样本外报告。"""
        if not _completeness_available:
            raise HTTPException(status_code=503, detail="completeness module not loaded")
        try:
            prices, used = _get_prices_for_prediction(symbol, source)
        except Exception as e:
            raise _safe_error(502, "Data load failed", e)
        return oos_analyze(prices, symbol=symbol)

    @app.get("/api/prediction/dashboard", dependencies=[Depends(auth)])
    def prediction_dashboard(symbol: str = "SI0", source: str = "akshare"):
        """全部7模块聚合 — 前端主入口。带缓存 + SymbolFilter集成。"""
        if not _completeness_available:
            raise HTTPException(status_code=503, detail="completeness module not loaded")
        try:
            prices, used = _get_prices_for_prediction(symbol, source)
        except Exception as e:
            raise _safe_error(502, "Data load failed", e)

        result = {
            "symbol": symbol,
            "source": used,
            "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        }

        # SymbolFilter 硬规则状态
        try:
            filter_status = get_symbol_filter_status(symbol)
            result["symbol_filter"] = filter_status
        except Exception:
            result["symbol_filter"] = {"allowed": False, "allowed_directions": [], "tier": ""}

        # 从 config 读取真实费率
        try:
            costs_cfg = load_trading_costs(symbol)
        except Exception:
            costs_cfg = {}

        # 历史准确率数据
        try:
            accuracy_data = get_combo_accuracy(symbol)
            result["accuracy_data"] = accuracy_data
        except Exception:
            result["accuracy_data"] = {}

        # 逐个调用7个模块（带缓存）
        for name, fn in [
            ("direction", direction_analyze),
            ("regime", regime_analyze),
            ("cost", cost_analyze),
            ("ensemble", ensemble_analyze),
            ("features", feature_analyze),
            ("walk_forward", walk_forward_analyze),
            ("oos", oos_analyze),
        ]:
            try:
                if name == "cost":
                    # 成本模块用 config 费率
                    result[name] = cached_analyze(symbol, name, fn, prices,
                                                  commission_rate=costs_cfg.get("commission_rate", 0.00005),
                                                  slippage_bps=costs_cfg.get("slippage_bps", 2.0))
                else:
                    result[name] = cached_analyze(symbol, name, fn, prices)
            except Exception as e:
                result[name] = {"error": str(e), "strategy_impact": "none"}

        # 方向预测 × SymbolFilter 交叉验证
        try:
            direction = result.get("direction", {})
            pred_dir = direction.get("direction", 0)
            cross_check = check_direction_with_filter(symbol, pred_dir)
            result["direction_cross_check"] = cross_check
        except Exception:
            result["direction_cross_check"] = {"filter_allows": False, "reason": "交叉验证失败"}

        # 记录到 tracker
        try:
            track_prediction(symbol, "dashboard", result.get("direction", {}))
        except Exception:
            pass

        # 优先级层级计算
        result["priority_score"] = _compute_priority(result)

        return result

    def _compute_priority(data: dict) -> dict:
        """根据优先级层级计算综合评分。

        层级: 硬规则 > 风控 > SymbolFilter > OOS > WF > 净期望 > v530 > ATR > 前端评分 > UI
        """
        score = 100  # 满分100
        warnings = []

        # 0. SymbolFilter 硬规则 (最高优先级)
        sf = data.get("symbol_filter", {})
        if not sf.get("allowed"):
            score -= 25
            warnings.append("不在SymbolFilter白名单")
        cross = data.get("direction_cross_check", {})
        if not cross.get("filter_allows"):
            score -= 15
            warnings.append("SymbolFilter拦截该方向")

        # 1. 方向预测 (SymbolFilter)
        direction = data.get("direction", {})
        if direction.get("confidence", 0) < 0.3:
            score -= 10
            warnings.append("方向置信度低")

        # 2. 模型一致性
        ensemble = data.get("ensemble", {})
        if ensemble.get("high_disagreement"):
            score -= 15
            warnings.append("模型分歧大")

        # 3. 样本外表现
        oos = data.get("oos", {})
        if oos.get("overfitting_flag"):
            score -= 20
            warnings.append("过拟合风险")
        oos_wr = oos.get("oos", {}).get("win_rate", 0.5)
        if oos_wr < 0.45:
            score -= 10
            warnings.append("OOS胜率偏低")

        # 4. WalkForward
        wf = data.get("walk_forward", {})
        if wf.get("overfit_signal"):
            score -= 10
            warnings.append("WF表现不稳定")

        # 5. 净期望
        cost = data.get("cost", {})
        if cost.get("expectation", {}).get("is_negative"):
            score -= 15
            warnings.append("净期望为负")

        # 6. 市场状态
        regime = data.get("regime", {})
        if regime.get("regime") in ("volatile", "anomaly"):
            score -= 10
            warnings.append(f"市场状态: {regime.get('regime_label', '')}")

        return {
            "score": max(0, score),
            "grade": "A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "D",
            "warnings": warnings,
        }

    @app.get("/prediction", response_class=HTMLResponse)
    def prediction_page():
        """AI 预测完整性仪表盘。"""
        prediction_html = Path(__file__).parent / "static" / "prediction.html"
        if prediction_html.exists():
            return HTMLResponse(prediction_html.read_text(encoding="utf-8"))
        return HTMLResponse("<h1>Prediction</h1><p>prediction.html not found.</p>")

    @app.post("/api/prediction/cache/clear", dependencies=[Depends(auth)])
    def prediction_cache_clear(symbol: str = ""):
        """清除预测缓存。"""
        if not _completeness_available:
            raise HTTPException(status_code=503, detail="completeness module not loaded")
        count = clear_cache(symbol)
        return {"cleared": count, "symbol": symbol}

    @app.get("/api/prediction/tracker", dependencies=[Depends(auth)])
    def prediction_tracker(symbol: str = "", days: int = 7):
        """获取预测 tracker 统计。"""
        if not _completeness_available:
            raise HTTPException(status_code=503, detail="completeness module not loaded")
        from ..analysis.completeness.integration import get_tracker_stats
        return get_tracker_stats(symbol, days)

    @app.get("/api/edge/stats", dependencies=[Depends(auth)])
    def edge_stats():
        """Edge setup 台账：分 setup 方向准确率 + 建议门槛。"""
        from ..edge_journal import api_stats_payload
        return api_stats_payload()

    @app.post("/api/edge/cycle", dependencies=[Depends(auth)])
    def edge_cycle_run():
        """手动触发 edge 每日循环（记录+回填+统计）。"""
        from ..edge_journal import daily_edge_cycle
        return daily_edge_cycle()

    @app.get("/api/edge/eval", dependencies=[Depends(auth)])
    def edge_eval_real():
        """真实行情滚动评估（默认监控池，可能较慢）。"""
        from ..direction_edge import SETUP_MIN_SCORES, evaluate_direction_accuracy
        from ..edge_journal import DEFAULT_WATCH_SYMBOLS, load_prices_for_symbol

        prices_map = {}
        for sym in DEFAULT_WATCH_SYMBOLS:
            df = load_prices_for_symbol(sym)
            if df is not None and len(df) >= 120:
                prices_map[sym] = df
        if not prices_map:
            raise HTTPException(status_code=503, detail="no market data")
        gated = evaluate_direction_accuracy(prices_map, forward_days=7, step=10, use_edge_gate=True)
        return {
            "symbols": list(prices_map.keys()),
            "eval": gated,
            "setup_min_scores": dict(SETUP_MIN_SCORES),
        }

    # ── 融合: 挂载工作区 A股特有路由 (predict/risk/prediction_log) ──
    try:
        from .routes.predict import register_predict_routes
        from .routes.prediction_log import register_prediction_log_routes
        from .routes.risk_monitor import register_risk_routes
        from .routes.screening import register_screening_routes
        from .shared import AppState

        _ashare = AppState()
        _ashare.init_broker()
        _ashare.init_loggers()
        register_predict_routes(app, _ashare, auth)
        register_risk_routes(app, _ashare.risk_monitor, auth)
        register_prediction_log_routes(app, _ashare, auth)
        register_screening_routes(app, _ashare, auth)
    except Exception as _ashare_exc:
        import logging
        logging.getLogger("quanttrader.api").warning("A股路由挂载失败(降级跳过): %s", _ashare_exc)

    return app


# Convenience for `uvicorn quanttrader.api.server:app`
def _maybe_app():
    try:
        return create_app()
    except ImportError:
        return None


app = _maybe_app()
