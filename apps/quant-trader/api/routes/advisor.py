"""Advisor & strategy routes: /advisor/*, /strategy/*, /playbooks, /playbook."""
from __future__ import annotations

from fastapi import Depends, HTTPException

from ...advisor import (
    TRADER_TACTICS,
    get_playbook_by_id,
    merge_playbook_allocation,
    playbooks_for_horizon,
    tactics_for_horizon,
    time_allocation_summary,
)
from ...engine.playbook import build_playbook, list_playbooks, run_playbook
from ...news import analyze_items, fetch_news
from ..helpers import load_prices
from ..schemas import PlaybookRequest, PlaybookResponse


def register_advisor_routes(app, shared, auth):
    """Register advisor and strategy endpoints."""

    @app.get("/playbooks", dependencies=[Depends(auth)])
    def playbooks():
        return {"playbooks": list_playbooks()}

    @app.post("/playbook", response_model=PlaybookResponse, dependencies=[Depends(auth)])
    def playbook(req: PlaybookRequest):
        if not req.symbols:
            raise HTTPException(status_code=400, detail="请至少提供一个标的。")

        sentiment = req.sentiment
        news_payload = None
        if req.use_news and sentiment is None:
            try:
                items, news_src = fetch_news(req.symbols[0], "auto", 12)
                sent = analyze_items(items)
                sentiment = sent.score
                news_payload = {"source": news_src, "score": sent.score, "label": sent.label,
                                "summary": sent.summary, "keywords": sent.keywords}
            except Exception:
                sentiment = None

        try:
            sleeves, preset = build_playbook(req.playbook, req.symbols, req.news_symbols, sentiment)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        all_syms = sorted({s for sl in sleeves for s in sl.symbols})
        prices_by_symbol = {}
        used = req.source
        for sym in all_syms:
            try:
                prices, used = load_prices(sym, req.source, req.start, req.end, req.interval)
                prices_by_symbol[sym] = prices
            except Exception as e:
                raise HTTPException(status_code=502, detail=f"行情加载失败 {sym}: {e}")

        try:
            result = run_playbook(prices_by_symbol, sleeves, cash=req.cash,
                                  commission=req.commission, slippage=req.slippage,
                                  lot_size=req.lot_size)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"回测失败: {e}")

        curve = [{"time": str(ts), "equity": float(v)} for ts, v in result.equity_curve.items()]
        per_sleeve = {
            name: {
                "weight": s["weight"], "description": s["description"], "strategy": s["strategy"],
                "symbols": s["symbols"], "n_trades": s["n_trades"],
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
            tips.append({"level": "info", "message": f"约 {result.idle_cash_pct*100:.0f}% 资金留作现金缓冲，未投入。"})
        tips.append({"level": "info", "message": "新闻卫星桶用的是设定/拉取的情绪分；实盘请结合「内置大模型」或实时新闻动态调整。"})

        return PlaybookResponse(
            playbook=req.playbook, label=preset["label"], description=preset["description"],
            source=used, stats=st, weights=result.weights, idle_cash_pct=result.idle_cash_pct,
            per_sleeve=per_sleeve, equity_curve=curve, tips=tips, news=news_payload,
        )

    @app.get("/advisor/tactics", dependencies=[Depends(auth)])
    def advisor_tactics(horizon: str = "both"):
        items = tactics_for_horizon(horizon) if horizon != "both" else TRADER_TACTICS
        return {"horizon": horizon, "tactics": items}

    @app.get("/advisor/playbooks")
    def advisor_playbooks(horizon: str = "both"):
        raw = playbooks_for_horizon(horizon) if horizon != "both" else playbooks_for_horizon("blend")
        enriched = shared.strategy_journal.enrich_playbooks(raw)
        primary = shared.strategy_journal.get_primary_strategy(horizon if horizon != "both" else "")
        return {
            "horizon": horizon,
            "playbooks": enriched,
            "time_allocation": time_allocation_summary(horizon),
            "primary_strategy": primary.to_dict() if primary else None,
        }

    @app.get("/advisor/allocate")
    def advisor_allocate(
        cash: float = 100_000,
        horizon: str = "long",
        template: str = "balanced",
        playbook_id: str = "",
    ):
        templates = {
            "aggressive": {"main": 0.70, "stable": 0.30, "cash": 0.0},
            "balanced": {"main": 0.50, "stable": 0.30, "cash": 0.20},
            "conservative": {"main": 0.30, "stable": 0.40, "cash": 0.30},
            "technical": {"main": 0.55, "stable": 0.25, "cash": 0.20},
        }
        base = dict(templates.get(template, templates["balanced"]))
        pb_dict = None
        if playbook_id:
            pb_dict = get_playbook_by_id(playbook_id)
        if pb_dict is None:
            primary = shared.strategy_journal.get_primary_strategy(horizon if horizon != "blend" else "")
            if primary:
                pb_dict = get_playbook_by_id(primary.playbook_id)
        enriched = shared.strategy_journal.enrich_playbooks([pb_dict]) if pb_dict else []
        pb = enriched[0] if enriched else pb_dict
        weights = merge_playbook_allocation(base, pb)
        if pb:
            eff = float(pb.get("effective_win_rate") or pb.get("historical_win_rate") or 0.5)
            boost = min(1.12, 0.88 + eff * 0.4)
            weights["main"] = min(0.78, weights["main"] * boost)
            s = sum(weights.values()) or 1.0
            weights = {k: round(v / s, 3) for k, v in weights.items()}
        return {
            "cash": cash,
            "horizon": horizon,
            "template": template,
            "playbook_id": pb.get("id") if pb else None,
            "playbook_name": pb.get("name") if pb else None,
            "trader_name": pb.get("trader_name") if pb else None,
            "weights": weights,
            "amounts": {
                "main": round(cash * weights["main"], 0),
                "stable": round(cash * weights["stable"], 0),
                "cash": round(cash * weights["cash"], 0),
            },
        }

    @app.get("/strategy/leaderboard")
    def strategy_leaderboard(period_days: int = 90):
        board = shared.strategy_journal.compute_leaderboard(period_days=period_days)
        return {"leaderboard": [e.to_dict() for e in board], "period_days": period_days}

    @app.get("/strategy/journal")
    def strategy_journal_list(limit: int = 50):
        return {"signals": shared.strategy_journal.recent_signals(limit)}

    @app.get("/strategy/summary")
    def strategy_summary_get():
        latest = shared.strategy_journal.latest_summary()
        if latest:
            return latest
        report = shared.strategy_journal.generate_summary()
        return report.to_dict()

    @app.post("/strategy/summary")
    def strategy_summary_refresh(period_days: int = 90):
        filled_logs = shared.prediction_logger.get_filled_predictions(n=500)
        shared.strategy_journal.sync_outcomes_from_predictions(filled_logs)
        report = shared.strategy_journal.generate_summary(period_days=period_days, append_history=True)
        return report.to_dict()
