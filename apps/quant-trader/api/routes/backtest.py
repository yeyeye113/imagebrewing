"""Backtest & optimize routes: /backtest, /portfolio_backtest, /optimize."""
from __future__ import annotations

from fastapi import Depends, HTTPException

from ...advisor import advise
from ...engine.backtest import Backtester
from ...engine.optimize import DEFAULT_GRIDS, grid_search, walk_forward
from ...engine.portfolio_backtest import MultiBacktester
from ...engine.position_sizing import SizingConfig
from ...engine.risk import RiskConfig
from ...engine.risk_assessment import assess_backtest_result, assess_portfolio, assess_trade, assessment_to_dict
from ...horizon import get_horizon
from ...strategy.base import get_strategy
from ..helpers import load_prices
from ..schemas import (
    BacktestRequest,
    BacktestResponse,
    OptimizeRequest,
    OptimizeResponse,
    PortfolioBacktestRequest,
    PortfolioBacktestResponse,
    RiskAssessRequest,
    RiskAssessResponse,
)


def _prepare_backtest(req):
    """Apply horizon preset; news blend 已下线。"""
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
        pass  # 新闻融合已下线
    strategy = get_strategy(strategy_name, **params)

    risk = RiskConfig(**risk_dict)
    sizing = SizingConfig(**sizing_dict)
    return strategy, risk, sizing, order_size, interval, horizon, news_payload, strategy_name


def register_backtest_routes(app, shared, auth):
    """Register backtest and optimize endpoints."""

    @app.post("/backtest", response_model=BacktestResponse, dependencies=[Depends(auth)])
    def backtest(req: BacktestRequest):
        try:
            strategy, risk, sizing, order_size, interval, horizon, news_payload, strat_name = (
                _prepare_backtest(req)
            )
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=400, detail=f"Bad strategy/params: {e}")

        try:
            prices, used = load_prices(req.symbol, req.source, req.start, req.end, interval)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Data load failed: {e}")

        bt = Backtester(
            cash=req.cash, order_size=order_size,
            commission=req.commission, slippage=req.slippage,
            lot_size=req.lot_size, risk=risk, sizing=sizing,
        )
        result = bt.run(prices, strategy)
        bh = float(prices["close"].iloc[-1] / prices["close"].iloc[0] - 1.0)
        curve = [{"time": str(ts), "equity": float(v)} for ts, v in result.equity_curve.items()]
        tips = [{"level": t.level, "message": t.message} for t in advise(result, buy_and_hold=bh)]
        risk_analysis = assess_backtest_result(result, req.cash, risk)
        return BacktestResponse(
            symbol=req.symbol, source=used, strategy=strat_name,
            n_bars=len(prices), n_trades=result.n_trades,
            risk_events=len(result.risk_events or []),
            stats=result.stats, buy_and_hold=bh, equity_curve=curve, tips=tips,
            risk_analysis=risk_analysis, horizon=horizon, news=news_payload,
        )

    @app.post("/portfolio_backtest", response_model=PortfolioBacktestResponse,
              dependencies=[Depends(auth)])
    def portfolio_backtest(req: PortfolioBacktestRequest):
        if not req.symbols:
            raise HTTPException(status_code=400, detail="Provide at least one symbol.")
        prices_by_symbol = {}
        used = req.source
        for sym in req.symbols:
            try:
                prices, used = load_prices(sym, req.source, req.start, req.end, req.interval)
            except Exception as e:
                raise HTTPException(status_code=502, detail=f"Data load failed for {sym}: {e}")
            prices_by_symbol[sym] = prices

        try:
            risk = RiskConfig(**req.risk) if req.risk else RiskConfig()
        except TypeError as e:
            raise HTTPException(status_code=400, detail=f"Bad risk config: {e}")
        try:
            sizing = SizingConfig(**req.sizing) if req.sizing else SizingConfig()
        except TypeError as e:
            raise HTTPException(status_code=400, detail=f"Bad sizing config: {e}")

        def factory():
            return get_strategy(req.strategy, **req.params)
        try:
            mbt = MultiBacktester(
                cash=req.cash, allocation=req.allocation, order_size=req.order_size,
                commission=req.commission, slippage=req.slippage, lot_size=req.lot_size,
                risk=risk, sizing=sizing,
            )
            result = mbt.run(prices_by_symbol, factory)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Backtest failed: {e}")

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
            symbols=req.symbols, source=used, strategy=req.strategy,
            allocation=result.allocation, weights=result.weights,
            stats=result.stats, per_symbol=per_symbol, equity_curve=curve, tips=tips,
        )

    @app.post("/risk_assess", response_model=RiskAssessResponse, dependencies=[Depends(auth)])
    def risk_assess(req: RiskAssessRequest):
        try:
            risk = RiskConfig(**req.risk) if req.risk else RiskConfig()
            sizing = SizingConfig(**req.sizing) if req.sizing else SizingConfig()
        except TypeError as e:
            raise HTTPException(status_code=400, detail=f"Bad config: {e}")

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
                    prices, used = load_prices(sym, req.source, req.start, req.end, req.interval)
                except Exception as e:
                    raise HTTPException(status_code=502, detail=f"Data load failed for {sym}: {e}")
                prices_by_symbol[sym] = prices
            assessment = assessment_to_dict(assess_portfolio(
                prices_by_symbol, req.allocation, req.cash, req.order_size, sizing, risk,
            ))
            return RiskAssessResponse(mode="portfolio", source=used, assessment=assessment)

        try:
            prices, used = load_prices(req.symbol, req.source, req.start, req.end, req.interval)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Data load failed: {e}")
        price = float(prices["close"].iloc[-1])
        assessment = assessment_to_dict(assess_trade(
            req.symbol, price, prices, equity, cash, req.position_value,
            req.order_size, sizing, risk, req.commission, req.slippage,
        ))
        return RiskAssessResponse(mode="trade", source=used, assessment=assessment)

    @app.post("/optimize", response_model=OptimizeResponse, dependencies=[Depends(auth)])
    def optimize(req: OptimizeRequest):
        try:
            prices, used = load_prices(req.symbol, req.source, req.start, req.end, req.interval)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Data load failed: {e}")

        grid = req.grid or DEFAULT_GRIDS.get(req.strategy)
        if not grid:
            raise HTTPException(status_code=400,
                                detail=f"No grid for {req.strategy!r}; supported: {list(DEFAULT_GRIDS)}")
        try:
            risk = RiskConfig(**req.risk) if req.risk else RiskConfig()
        except TypeError as e:
            raise HTTPException(status_code=400, detail=f"Bad risk config: {e}")

        try:
            opt = grid_search(prices, req.strategy, grid, metric=req.metric, risk=risk, cash=req.cash)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Optimize failed: {e}")

        top = [{"params": p, "sharpe": s.get("sharpe", 0), "total_return": s.get("total_return", 0),
                "max_drawdown": s.get("max_drawdown", 0)} for p, s in opt.results[:10]]

        wf_payload = {}
        try:
            wf = walk_forward(prices, req.strategy, grid, n_splits=req.n_splits,
                              metric=req.metric, risk=risk, cash=req.cash)
            wf_payload = {
                "avg_oos_return": wf.avg_oos_return,
                "avg_oos_sharpe": wf.avg_oos_sharpe,
                "overfit_gap": wf.overfit_gap,
                "folds": [{"best_params": f["best_params"],
                           "oos_return": f["oos_stats"].get("total_return", 0),
                           "oos_sharpe": f["oos_stats"].get("sharpe", 0)} for f in wf.folds],
            }
        except Exception as e:
            wf_payload = {"error": str(e)}

        return OptimizeResponse(
            symbol=req.symbol, source=used, strategy=req.strategy, metric=req.metric,
            best_params=opt.best_params, best_score=opt.best_score, top=top, walk_forward=wf_payload,
        )
