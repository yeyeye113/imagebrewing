from __future__ import annotations

from .feeds import NewsItem, aggregate_news, fetch_news, news_for_llm, news_item_dict
from .parser import (
    SentimentResult,
    analyze_items,
    analyze_text,
    assess_news_risk,
    horizon_fit_from_news,
    recommend_action,
)

__all__ = [
    "NewsItem",
    "SentimentResult",
    "aggregate_news",
    "analyze_items",
    "analyze_text",
    "assess_news_risk",
    "fetch_news",
    "horizon_fit_from_news",
    "news_for_llm",
    "news_item_dict",
    "recommend_action",
]
