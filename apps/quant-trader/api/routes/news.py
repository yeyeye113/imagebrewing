"""News & horizon routes（未挂载；新闻 API 已下线，仅保留 horizons 供参考）。"""
from __future__ import annotations

from fastapi import Depends

from ...advisor import PRINCIPLES
from ...horizon import list_horizons
from ...news import analyze_items, analyze_text, fetch_news, horizon_fit_from_news
from ...news.feeds import news_item_dict
from ...news.parser import recommend_action
from ..schemas import NewsAnalyzeRequest, NewsAnalyzeResponse


def register_news_routes(app, shared, auth):
    """Register news and horizon endpoints."""

    @app.get("/horizons", dependencies=[Depends(auth)])
    def horizons():
        return {
            "horizons": [
                {"name": h.name, "label": h.label, "description": h.description}
                for h in list_horizons()
            ]
        }

    @app.get("/news", dependencies=[Depends(auth)])
    def news_list(symbol: str, source: str = "auto", limit: int = 20):
        items, used = fetch_news(symbol, source, limit)
        return {"symbol": symbol, "source": used, "items": [news_item_dict(i) for i in items]}

    @app.post("/news/analyze", response_model=NewsAnalyzeResponse, dependencies=[Depends(auth)])
    def news_analyze(req: NewsAnalyzeRequest):
        if req.text.strip():
            sent = analyze_text(req.text)
            items: list = []
            used = "text"
        else:
            items, used = fetch_news(req.symbol, req.source, req.limit)
            sent = analyze_items(items)
        hf = horizon_fit_from_news(items) if items else {"short": 0.33, "medium": 0.34, "long": 0.33}
        return NewsAnalyzeResponse(
            symbol=req.symbol,
            source=used,
            horizon=req.horizon,
            items=[news_item_dict(i) for i in items[: req.limit]],
            sentiment={
                "score": sent.score, "label": sent.label, "summary": sent.summary,
                "bullish": sent.bullish_count, "bearish": sent.bearish_count,
            },
            horizon_fit=hf,
            recommendation=recommend_action(sent, req.horizon),
            keywords=sent.keywords,
        )

    @app.get("/principles", dependencies=[Depends(auth)])
    def principles():
        return {"principles": PRINCIPLES}
