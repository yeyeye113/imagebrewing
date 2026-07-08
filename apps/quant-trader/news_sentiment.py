"""新闻情绪分析模块 — NLP 分析财经新闻情绪.

功能:
  1. 获取财经新闻
  2. 情绪词典分析
  3. 情绪评分
  4. 生成交易信号
"""
from __future__ import annotations

from dataclasses import dataclass

from .log import get_logger

logger = get_logger("news_sentiment")


# 情绪词典
POSITIVE_WORDS = {
    '利好', '上涨', '增长', '突破', '新高', '反弹', '回升', '强势', '看多',
    '买入', '增持', '推荐', '优秀', '超预期', '利润增长', '营收增长',
    '大涨', '涨停', '暴涨', '飙升', '创新高', '放量', '资金流入',
    '机构买入', '北向资金', '主力', '做多', '看涨', '利多', '正面',
}

NEGATIVE_WORDS = {
    '利空', '下跌', '下滑', '跌破', '新低', '回调', '回落', '弱势', '看空',
    '卖出', '减持', '回避', '糟糕', '低于预期', '利润下降', '营收下降',
    '大跌', '跌停', '暴跌', '跳水', '创新低', '缩量', '资金流出',
    '机构卖出', '主力出逃', '做空', '看跌', '负面', '风险',
}


@dataclass
class NewsSentiment:
    """新闻情绪分析结果."""
    symbol: str
    news_count: int         # 新闻数量
    positive_count: int     # 正面新闻数
    negative_count: int     # 负面新闻数
    sentiment_score: float  # 情绪分 (-1 到 1)
    signal: str             # "BUY" | "SELL" | "HOLD"
    confidence: float       # 置信度 (0-100)
    reason: str             # 分析原因


def get_stock_news(symbol: str, days: int = 7) -> list[dict]:
    """获取股票新闻.

    Args:
        symbol: 股票代码
        days: 获取天数

    Returns:
        list[dict]: 新闻列表
    """
    try:
        import akshare as ak

        # 获取新闻
        df = ak.stock_news_em(symbol=symbol)

        if df is None or df.empty:
            return []

        # 转换为列表
        news_list = []
        for _, row in df.head(20).iterrows():
            news_list.append({
                "title": str(row.get("新闻标题", "")),
                "content": str(row.get("新闻内容", "")),
                "time": str(row.get("发布时间", "")),
            })

        return news_list
    except Exception as e:
        logger.warning("获取新闻失败 %s: %s", symbol, e)
        return []


def analyze_text_sentiment(text: str) -> float:
    """分析文本情绪.

    Args:
        text: 文本内容

    Returns:
        float: 情绪分 (-1 到 1)
    """
    if not text:
        return 0.0

    # 统计正面和负面词
    positive_count = sum(1 for word in POSITIVE_WORDS if word in text)
    negative_count = sum(1 for word in NEGATIVE_WORDS if word in text)

    total = positive_count + negative_count

    if total == 0:
        return 0.0

    # 计算情绪分
    sentiment = (positive_count - negative_count) / total

    return sentiment


def analyze_news_sentiment(symbol: str, days: int = 7) -> NewsSentiment:
    """分析新闻情绪.

    Args:
        symbol: 股票代码
        days: 获取天数

    Returns:
        NewsSentiment: 情绪分析结果
    """
    # 获取新闻
    news_list = get_stock_news(symbol, days)

    if not news_list:
        return NewsSentiment(
            symbol=symbol,
            news_count=0,
            positive_count=0,
            negative_count=0,
            sentiment_score=0.0,
            signal="HOLD",
            confidence=50,
            reason="无新闻数据",
        )

    # 分析每条新闻
    positive_count = 0
    negative_count = 0
    total_sentiment = 0.0

    for news in news_list:
        title = news.get("title", "")
        content = news.get("content", "")
        text = title + " " + content

        sentiment = analyze_text_sentiment(text)
        total_sentiment += sentiment

        if sentiment > 0.1:
            positive_count += 1
        elif sentiment < -0.1:
            negative_count += 1

    # 计算平均情绪分
    avg_sentiment = total_sentiment / len(news_list) if news_list else 0.0

    # 计算置信度
    news_count = len(news_list)
    if news_count >= 10:
        confidence = 80
    elif news_count >= 5:
        confidence = 60
    else:
        confidence = 40

    # 判断信号
    if avg_sentiment > 0.2:
        signal = "BUY"
        reason = f"新闻情绪正面 (正面{positive_count}条, 负面{negative_count}条)"
    elif avg_sentiment < -0.2:
        signal = "SELL"
        reason = f"新闻情绪负面 (正面{positive_count}条, 负面{negative_count}条)"
    else:
        signal = "HOLD"
        reason = f"新闻情绪中性 (正面{positive_count}条, 负面{negative_count}条)"

    return NewsSentiment(
        symbol=symbol,
        news_count=news_count,
        positive_count=positive_count,
        negative_count=negative_count,
        sentiment_score=round(avg_sentiment, 3),
        signal=signal,
        confidence=confidence,
        reason=reason,
    )


def get_news_sentiment_signal(symbol: str) -> dict:
    """获取新闻情绪信号.

    Returns:
        dict: {
            "signal": str,
            "confidence": float,
            "sentiment_score": float,
            "news_count": int,
            "reason": str,
        }
    """
    result = analyze_news_sentiment(symbol)

    return {
        "signal": result.signal,
        "confidence": result.confidence,
        "sentiment_score": result.sentiment_score,
        "news_count": result.news_count,
        "reason": result.reason,
    }
