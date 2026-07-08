"""Screening routes: /screening/*."""
from __future__ import annotations

from ...screening_journal import ScreeningWeights


def register_screening_routes(app, shared, auth):
    """Register screening endpoints."""

    @app.get("/screening/live-panel")
    def screening_live_panel(limit: int = 48):
        summary = shared.live_panel.summary()
        from ...market_schedule import market_schedule
        sched = market_schedule().to_dict()
        return {**summary, "schedule": sched}

    @app.get("/screening/config")
    def screening_config_get():
        w = shared.screening_journal.load_weights()
        return {"weights": w.to_dict(), "defaults": ScreeningWeights().to_dict()}

    @app.post("/screening/config")
    def screening_config_post(
        tech: float = 0.82, news: float = 0.08, wuxing: float = 0.05, meta: float = 0.05,
    ):
        w = ScreeningWeights(tech=tech, news=news, wuxing=wuxing, meta=meta).normalized()
        saved = shared.screening_journal.save_weights(w, note="manual")
        return saved

    @app.get("/screening/journal")
    def screening_journal_list(limit: int = 40):
        return {"entries": shared.screening_journal.recent_runs(limit)}

    @app.get("/screening/analyze/{symbol}")
    def screening_analyze_symbol(
        symbol: str,
        name: str = "",
        kind: str = "stock",
        use_news: bool = True,
        use_wuxing: bool = True,
    ):
        from ...ashare_pipeline import analyze_single_future, analyze_single_stock

        sw = shared.screening_journal.load_weights()
        if kind == "future":
            return analyze_single_future(
                symbol, name=name, use_news=use_news, use_wuxing=use_wuxing, weights=sw,
            )
        return analyze_single_stock(
            symbol, name=name, use_news=use_news, use_wuxing=use_wuxing, weights=sw,
        )

    @app.post("/screening/iterate")
    def screening_iterate():
        stats = shared.deviation_tracker.compute_global_stats()
        filled_logs = shared.prediction_logger.get_filled_predictions(n=200)
        shared.strategy_journal.sync_outcomes_from_predictions(filled_logs)
        strat_sum = shared.strategy_journal.latest_summary() or {}
        strat_wr = strat_sum.get("global_logged_win_rate")
        new_w, note = shared.screening_journal.iterate_weights(stats, strategy_global_wr=strat_wr)
        primary = shared.strategy_journal.get_primary_strategy()
        if primary and primary.n_filled >= 3 and primary.logged_win_rate is not None:
            note += f"；日志优选: {primary.trader_name}「{primary.playbook_name}」胜率{primary.logged_win_rate:.0%}"
        shared.strategy_journal.update_summary_light()
        return {"weights": new_w.to_dict(), "note": note, "deviation": stats,
                "primary_strategy": primary.to_dict() if primary else None}
