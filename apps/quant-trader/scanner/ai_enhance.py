"""Scanner AI 增强模块 — 对 top 候选运行 LLM 批量研判。

流程:
  1. 取技术评分 top N (默认5)
  2. 对每只并发调 LLM 生成 ai_action / ai_confidence / ai_reason
  3. AI 置信度可选叠加到最终 score (需 config.use_ai_score=True)

调用方式:
  from .ai_enhance import ai_enhance
  ai_enhance(picks, klines, cfg)
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pandas as pd

from ..ai.llm import LLMConfig, ask_llm
from .common import ScanConfig

logger = logging.getLogger("quanttrader.scanner.ai_enhance")


# ── Prompt 模板 ─────────────────────────────────────────────────────

_SYSTEM = (
    "你是A股短线交易分析师。给定一只股票的K线数据和板块/市场环境信息，"
    "判断未来1-2天的操作方向。严格返回JSON，不要多余文字。\n"
    '返回格式: {"ai_action":"buy|hold|sell", "ai_confidence":0.0-1.0, '
    '"ai_reason":"<=80字中文理由", "risk_level":"low|mid|high"}\n\n'
    "判断框架:\n"
    "- 趋势: 均线多头排列=看多, 空头排列=看空\n"
    "- 量价: 放量突破=强信号, 缩量上涨=假突破风险\n"
    "- 位置: 高位(>20日新高)追涨风险大, 低位反弹机会多\n"
    "- 板块: 板块共振上涨=加分, 独立上涨=警惕\n"
    "- 风险: 已涨>7%不追, 已跌>5%不接飞刀\n"
    "- 置信度: 信号明确>0.7, 模糊=0.4-0.6, 冲突<0.4"
)


def _build_stock_prompt(
    stock: dict[str, Any],
    kline: list[dict[str, Any]] | None,
    regime: str,
    sector_info: str,
) -> str:
    """为单只股票构建 prompt。"""
    code = stock.get("code", "")
    name = stock.get("name", "")
    price = stock.get("price", 0)
    chg = stock.get("chg_pct", 0)
    turnover = stock.get("turnover", 0)
    amount_yi = stock.get("amount_yi", 0)
    mom_5d = stock.get("mom_5d", 0)
    mom_20d = stock.get("mom_20d", 0)
    vol_ratio = stock.get("vol_ratio", 1.0)
    trend_pct = stock.get("trend_pct", 0)

    lines = [
        f"【{code} {name}】",
        f"现价: ¥{price:.2f} | 今日涨跌: {chg:+.2f}%",
        f"5日动量: {mom_5d:+.2f}% | 20日动量: {mom_20d:+.2f}%",
        f"量比: {vol_ratio:.2f}x | 换手率: {turnover:.2f}%",
        f"成交额: {amount_yi:.1f}亿 | 偏离SMA10: {trend_pct:+.2f}%",
        f"市场环境: {regime}",
    ]

    if sector_info:
        lines.append(f"板块: {sector_info}")

    # K线摘要: 最近5根
    if kline and len(kline) >= 3:
        recent = kline[-5:] if len(kline) >= 5 else kline
        lines.append("近K线(开/高/低/收/量):")
        for k in recent:
            lines.append(
                f"  {k.get('day','?')} O={k.get('open',0):.2f} "
                f"H={k.get('high',0):.2f} L={k.get('low',0):.2f} "
                f"C={k.get('close',0):.2f} V={k.get('volume',0):.0f}"
            )
        # 简单技术
        closes = [float(k.get("close", 0)) for k in kline if k.get("close")]
        if len(closes) >= 10:
            sma5 = sum(closes[-5:]) / 5
            sma10 = sum(closes[-10:]) / 10
            lines.append(f"SMA5={sma5:.2f} SMA10={sma10:.2f} → {'多头' if sma5 > sma10 else '空头'}排列")
    else:
        lines.append("(无K线历史数据)")

    return "\n".join(lines)


def _call_llm_single(
    stock: dict[str, Any],
    kline: list[dict[str, Any]] | None,
    regime: str,
    sector_info: str,
    llm_cfg: LLMConfig,
) -> dict[str, Any]:
    """对单只股票调 LLM，返回解析后的结果。"""
    code = stock.get("code", "?")
    try:
        prompt = _build_stock_prompt(stock, kline, regime, sector_info)

        # 用 ask_llm 需要 DataFrame，这里直接构造一个最小的
        if kline and len(kline) >= 3:
            rows = []
            for k in kline:
                rows.append({
                    "open": float(k.get("open", 0)),
                    "high": float(k.get("high", 0)),
                    "low": float(k.get("low", 0)),
                    "close": float(k.get("close", 0)),
                    "volume": float(k.get("volume", 0)),
                })
            df = pd.DataFrame(rows)
        else:
            # 最小 DataFrame 防空
            df = pd.DataFrame({"close": [stock.get("price", 10.0)] * 5})

        # 构造 extra_ctx 传入 prompt
        result = ask_llm(df, llm_cfg, extra_ctx=prompt)
        ai_action = result.get("signal", 0)
        ai_conf = result.get("confidence", 0.5)
        ai_reason = result.get("reason", "")

        # signal 1/0/-1 → buy/hold/sell
        action_map = {1: "buy", 0: "hold", -1: "sell"}
        action_str = action_map.get(ai_action, "hold")

        return {
            "code": code,
            "ai_action": action_str,
            "ai_confidence": round(ai_conf, 2),
            "ai_reason": ai_reason[:120],
            "risk_level": _infer_risk(stock),
            "ok": True,
        }
    except Exception as e:
        logger.warning("AI enhance failed for %s: %s", code, e)
        return {
            "code": code,
            "ai_action": "hold",
            "ai_confidence": 0.0,
            "ai_reason": f"LLM调用失败: {e}",
            "risk_level": "mid",
            "ok": False,
        }


def _infer_risk(stock: dict[str, Any]) -> str:
    """根据基础指标推断风险等级。"""
    chg = abs(stock.get("chg_pct", 0))
    mom5 = abs(stock.get("mom_5d", 0))
    turnover = stock.get("turnover", 0)
    if chg > 7 or mom5 > 15 or turnover > 15:
        return "high"
    elif chg > 3 or mom5 > 8 or turnover > 8:
        return "mid"
    return "low"


# ── 主入口 ──────────────────────────────────────────────────────────


def ai_enhance(
    picks: list[dict[str, Any]],
    klines: dict[str, list[dict[str, Any]]],
    config: ScanConfig,
    regime: str = "unknown",
) -> list[dict[str, Any]]:
    """对 top 候选运行 LLM 批量研判，返回增强后的候选列表。

    Args:
        picks: 排序后的候选列表 (dict 格式, 来自 engine.py)
        klines: {code: [kline_dict, ...]} K线数据
        config: 扫描配置
        regime: 市场环境描述

    Returns:
        picks 列表 (原地更新 ai_* 字段 + 可选 score 调整)
    """
    if not config.use_ai:
        return picks

    ai_top = config.ai_top_n
    targets = picks[:ai_top]
    logger.info("AI enhance: analyzing top %d candidates", len(targets))

    # 构造 LLM config
    llm_cfg = LLMConfig(
        provider=config.ai_provider,
        api_key=config.ai_api_key,
        temperature=0.15,
        timeout=config.ai_timeout,
    )

    # 并发调用
    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=min(len(targets), config.ai_concurrency)) as pool:
        futures = {}
        for s in targets:
            code = s.get("code", "")
            sector_info = ""
            if s.get("sector_resonance"):
                sector_info = f"{s.get('sector_group', '')} (共振:{s['sector_resonance']})"
            elif s.get("sector_group"):
                sector_info = s["sector_group"]

            fut = pool.submit(
                _call_llm_single,
                s,
                klines.get(code),
                regime,
                sector_info,
                llm_cfg,
            )
            futures[fut] = code

        for fut in as_completed(futures):
            code = futures[fut]
            try:
                r = fut.result()
                results[code] = r
            except Exception as e:
                logger.warning("AI future failed for %s: %s", code, e)
                results[code] = {
                    "code": code,
                    "ai_action": "hold",
                    "ai_confidence": 0.0,
                    "ai_reason": str(e)[:120],
                    "risk_level": "mid",
                    "ok": False,
                }

    # 回写到 picks
    for s in picks:
        code = s.get("code", "")
        if code in results:
            r = results[code]
            s["ai_action"] = r["ai_action"]
            s["ai_confidence"] = r["ai_confidence"]
            s["ai_reason"] = r["ai_reason"]
            s["risk_level"] = r["risk_level"]

            # 可选: AI 置信度叠加到 score
            if config.use_ai_score and r["ok"]:
                ai_adj = r["ai_confidence"] * config.ai_score_weight
                if r["ai_action"] == "sell":
                    ai_adj = -ai_adj
                s["score"] = round(min(max(s["score"] + ai_adj, 0), 100))

    ok_count = sum(1 for r in results.values() if r.get("ok"))
    logger.info("AI enhance done: %d/%d succeeded", ok_count, len(targets))
    return picks
