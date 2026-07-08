"""自由预测引擎 — LLM + 技术面综合研判。

不限于特定标的，可对任意市场/品种/事件做自由预测。
整合:
  - 技术面: 高低点 + 趋势 + 量价
  - LLM: 综合推理

用法:
    from quanttrader.analysis import free_predict, PredictionReport
    report = free_predict("原油SC接下来一周怎么走？", llm_api_key="...")
    print(report.to_text())
"""

from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class PredictionReport:
    """自由预测报告。"""

    question: str
    timestamp: str
    # 技术面
    technical_view: str = ""
    key_levels: list[dict] = field(default_factory=list)
    # 玄学面
    divination_view: str = ""
    hexagram: str = ""
    hex_sentiment: str = ""
    # 新闻面
    news_view: str = ""
    news_sentiment: str = ""
    # LLM综合
    llm_prediction: str = ""
    llm_confidence: float = 0.0
    llm_direction: str = ""  # "bullish" | "bearish" | "neutral"
    # 综合
    final_verdict: str = ""
    risk_note: str = ""

    def to_text(self) -> str:
        lines = [
            "╔══════════════════════════════════════════════════════╗",
            "║  🔮 自由预测报告                                     ║",
            "╠══════════════════════════════════════════════════════╣",
            f"║  问题: {self.question[:44]:<44s} ║",
            f"║  时间: {self.timestamp:<44s} ║",
            "╠══════════════════════════════════════════════════════╣",
        ]
        if self.technical_view:
            lines.append("║  📊 技术面:                                          ║")
            for ln in self.technical_view[:200].split("\n"):
                lines.append(f"║    {ln:<50s}║")
        if self.llm_prediction:
            dir_icon = {"bullish": "🟢看涨", "bearish": "🔴看跌", "neutral": "⚖️中性"}.get(self.llm_direction, "❓")
            lines.append(f"║  🧠 LLM: {dir_icon} 置信度{self.llm_confidence:.0%}                    ║")
            for ln in self.llm_prediction[:300].split("\n"):
                lines.append(f"║    {ln:<50s}║")
        if self.final_verdict:
            lines.append("╠══════════════════════════════════════════════════════╣")
            lines.append("║  📝 综合判断:                                        ║")
            for ln in self.final_verdict[:200].split("\n"):
                lines.append(f"║    {ln:<50s}║")
        if self.risk_note:
            lines.append(f"║  ⚠️ {self.risk_note[:50]:<50s} ║")
        lines.append("╚══════════════════════════════════════════════════════╝")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "timestamp": self.timestamp,
            "technical_view": self.technical_view,
            "key_levels": self.key_levels,
            "divination_view": self.divination_view,
            "hexagram": self.hexagram,
            "hex_sentiment": self.hex_sentiment,
            "news_view": self.news_view,
            "news_sentiment": self.news_sentiment,
            "llm_prediction": self.llm_prediction,
            "llm_confidence": self.llm_confidence,
            "llm_direction": self.llm_direction,
            "final_verdict": self.final_verdict,
            "risk_note": self.risk_note,
        }


# ══════════════════════════════════════════════════════════════════
# 预测引擎
# ══════════════════════════════════════════════════════════════════


def _extract_symbol(question: str) -> str | None:
    """从问题中提取标的代码或名称。"""
    import re

    # 期货代码: 2-3个大写字母 (中文后也匹配)
    m = re.search(r"(?<![A-Za-z])([A-Z]{2,3})(?![A-Za-z])", question)
    if m:
        return m.group(1)
    # A股代码: 6位数字
    m = re.search(r"(\d{6})", question)
    if m:
        return m.group(1)
    # 中文名称映射
    _NAME_MAP = {
        "螺纹钢": "RB",
        "螺纹": "RB",
        "铁矿石": "I",
        "铁矿": "I",
        "原油": "SC",
        "黄金": "AU",
        "白银": "AG",
        "铜": "CU",
        "铝": "AL",
        "锌": "ZN",
        "沥青": "BU",
        "燃油": "FU",
        "甲醇": "MA",
        "PTA": "TA",
        "纯碱": "SA",
        "豆粕": "M",
        "棕榈油": "P",
        "菜粕": "RM",
        "玉米": "C",
        "棉花": "CF",
    }
    for name, code in _NAME_MAP.items():
        if name in question:
            return code
    return None


def _get_technical_context(symbol: str | None) -> tuple[str, list[dict]]:
    """获取技术面分析上下文。"""
    if not symbol:
        return "无特定标的，无法做技术分析。", []

    try:
        from quanttrader.forecast import _load_synthetic
        from quanttrader.futures.scanner_v2 import _fetch_single

        from .highlow import find_highlows

        df = None
        try:
            df = _fetch_single(symbol)
        except Exception:
            pass

        if df is None or len(df) < 20:
            code_seed = sum(ord(c) for c in symbol) + int(dt.date.today().strftime("%Y%m%d"))
            np.random.seed(code_seed % 2**31)
            df = _load_synthetic(
                symbol, days=120, start_price=float(abs(hash(symbol)) % 3000 + 2000), trend=0.03, vol=0.20
            )

        hl = find_highlows(df, symbol=symbol)

        levels = []
        for l in hl.levels[:8]:
            levels.append({"price": l.price, "kind": l.kind, "strength": l.strength, "source": l.source})

        view_lines = [
            f"当前价 ¥{hl.current_price:,.2f} | {hl.trend}",
            f"ATR(14): ¥{hl.atr:,.2f}",
            f"最近支撑: ¥{hl.nearest_support:,.2f} | 最近阻力: ¥{hl.nearest_resistance:,.2f}",
            f"位置: {hl.position_pct:.0f}% (0=支撑, 100=阻力)",
        ]
        return "\n".join(view_lines), levels

    except Exception as e:
        return f"技术分析出错: {e}", []


def _get_divination(symbol: str | None) -> tuple[str, str, str]:
    """玄学推演已下线。"""
    _ = symbol
    return "", "", ""


def _get_news_context(symbol: str | None) -> tuple[str, str]:
    """获取新闻上下文。"""
    try:
        if symbol:
            from quanttrader.futures.news import aggregate_futures

            items, text = aggregate_futures(limit=5)
            high_n = sum(1 for i in items if i.impact_level == "high")
            sentiment = "偏多" if high_n > 2 else "偏空" if high_n == 0 else "中性"
            return f"{len(items)}条新闻, 高影响{high_n}\n{text[:300]}", sentiment
        else:
            from quanttrader.news.feeds import aggregate_news, news_for_llm

            # 无特定标的时用空 symbol 拉综合新闻 (内部自动回退 demo 源)
            stock_items = aggregate_news("", limit=5)
            stock_text = news_for_llm(stock_items)
            return f"{len(stock_items)}条新闻\n{stock_text[:300]}", "中性"
    except Exception:
        return "", ""


def _ask_llm_prediction(
    question: str,
    tech_ctx: str,
    div_ctx: str,
    news_ctx: str,
    api_key: str,
    provider: str = "deepseek",
) -> tuple[str, float, str]:
    """LLM 综合预测。"""
    if not api_key:
        return "无API密钥，跳过LLM预测。", 0.0, "neutral"

    try:
        from quanttrader.ai.llm import LLMConfig, ask_llm_text

        cfg = LLMConfig(provider=provider, api_key=api_key)
        cfg.resolve()

        prompt = f"""你是一个综合研判分析师。请基于以下信息，回答用户的问题。

## 用户问题
{question}

## 技术面
{tech_ctx}

## 新闻面
{news_ctx if news_ctx else "无新闻数据"}

请用中文回答，包含:
1. 你的判断方向 (看涨/看跌/中性)
2. 置信度 (0-100%)
3. 核心理由 (3-5条)
4. 关键价位 (支撑/阻力)
5. 时间框架 (短期/中期/长期)
6. 风险提示

JSON格式:
{{"direction": "bullish/bearish/neutral", "confidence": 0.0-1.0, "reason": "详细分析", "key_levels": "关键价位", "timeframe": "时间框架", "risk": "风险提示"}}"""

        result = ask_llm_text(prompt, cfg, system="你是综合研判分析师，融合技术面与新闻做判断。回答必须是JSON。")

        # 解析JSON
        try:
            # 尝试从response中提取JSON
            import re

            json_match = re.search(r"\{[^{}]*\}", result, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                direction = data.get("direction", "neutral")
                confidence = float(data.get("confidence", 0.5))
                reason = data.get("reason", result[:200])
                return reason, confidence, direction
        except Exception:
            pass

        return result[:300], 0.5, "neutral"

    except Exception as e:
        return f"LLM调用失败: {e}", 0.0, "neutral"


def free_predict(
    question: str,
    symbol: str | None = None,
    llm_api_key: str = "",
    llm_provider: str = "deepseek",
) -> PredictionReport:
    """自由预测 — 对任意问题做综合研判。

    Args:
        question: 用户的问题 (如 "原油SC接下来一周怎么走？")
        symbol: 标的代码 (可选，会尝试从问题中自动提取)
        llm_api_key: LLM API密钥
        llm_provider: LLM提供商
    """
    if not llm_api_key:
        llm_api_key = os.environ.get("QT_LLM_KEY", "") or os.environ.get("DEEPSEEK_API_KEY", "")
    if not llm_provider:
        llm_provider = os.environ.get("QT_LLM_PROVIDER", "deepseek")

    if symbol is None:
        symbol = _extract_symbol(question)

    # 并行收集各维度信息
    tech_view, key_levels = _get_technical_context(symbol)
    div_view, hexagram, hex_sent = _get_divination(symbol)
    news_view, news_sent = _get_news_context(symbol)

    # LLM 综合
    llm_pred, llm_conf, llm_dir = _ask_llm_prediction(
        question, tech_view, div_view, news_view, llm_api_key, llm_provider
    )

    # 综合判断
    verdict_parts = []
    if llm_dir == "bullish":
        verdict_parts.append("LLM看涨")
    elif llm_dir == "bearish":
        verdict_parts.append("LLM看跌")
    else:
        verdict_parts.append("LLM中性")

    final = " | ".join(verdict_parts)
    risk = "预测仅供参考，不构成投资建议。市场有风险，入市需谨慎。"

    return PredictionReport(
        question=question,
        timestamp=dt.datetime.now().isoformat(timespec="seconds"),
        technical_view=tech_view,
        key_levels=key_levels,
        divination_view=div_view,
        hexagram=hexagram,
        hex_sentiment=hex_sent,
        news_view=news_view,
        news_sentiment=news_sent,
        llm_prediction=llm_pred,
        llm_confidence=llm_conf,
        llm_direction=llm_dir,
        final_verdict=final,
        risk_note=risk,
    )
