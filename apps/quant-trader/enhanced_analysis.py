"""增强版自选分析 — 从各个角度全面分析单标的, 生成用户可操作建议.

整合:
  - 多因子评分
  - 扩展技术指标
  - 成交量分析
  - 可迭代筛选器
  - 投资建议引擎
  - 分析日志记录
"""
from __future__ import annotations

import time

import pandas as pd

from .advisor_engine import (
    format_report_text,
    generate_investment_advice,
)
from .analysis import (
    default_screener,
    indicator_summary,
    multi_factor_score,
    volume_summary,
)
from .journal import (
    AnalysisJournal,
    create_record_from_analysis,
)

# ═══════════════════════════════════════════════════════════════════════
# 增强分析函数
# ═══════════════════════════════════════════════════════════════════════

def enhanced_analyze(
    symbol: str,
    name: str = "",
    kind: str = "stock",
    prices: pd.DataFrame | None = None,
    loader_fn=None,
    journal: AnalysisJournal | None = None,
    use_screener: bool = True,
    factor_weights: dict[str, float] | None = None,
    save_to_journal: bool = True,
) -> dict:
    """增强版单标的全面分析.

    Args:
        symbol: 代码
        name: 名称
        kind: "stock" | "future"
        prices: 行情数据 (可选, 不传则自动加载)
        loader_fn: 数据加载函数 (可选, 不传则自动选择)
        journal: 分析日志实例 (可选)
        use_screener: 是否使用筛选器
        factor_weights: 自定义因子权重
        save_to_journal: 是否保存到日志

    Returns:
        dict: 完整分析结果
    """
    t0 = time.time()

    # 自动选择加载函数
    if loader_fn is None:
        from .ashare_pipeline import _load_futures_prices, _load_stock_prices
        loader_fn = _load_stock_prices if kind == "stock" else _load_futures_prices

    # 加载数据
    if prices is None:
        prices = loader_fn(symbol)
    if prices is None or len(prices) < 30:
        return {
            "symbol": symbol, "name": name, "kind": kind,
            "status": "no_data", "error": "无法加载行情数据",
            "elapsed_s": round(time.time() - t0, 2),
        }

    price = float(prices["close"].iloc[-1])

    # 1. 多因子评分
    factors = multi_factor_score(prices, factor_weights)

    # 2. 扩展技术指标
    indicators = indicator_summary(prices)

    # 3. 成交量分析
    volume = volume_summary(prices)

    # 4. 可迭代筛选器
    screener_result = None
    if use_screener:
        screener = default_screener(min_pass_ratio=0.5, factor_weights=factor_weights)
        screener_result = screener.screen(symbol, name, prices)

    # 5. 生成投资建议报告
    advice_report = generate_investment_advice(
        symbol=symbol,
        name=name,
        price=price,
        analysis=None,
        factors=factors,
        indicators=indicators,
        volume_info=volume,
        screener_result=screener_result.to_dict() if screener_result else None,
    )
    # generate_investment_advice 恒定产出三条建议; 收窄为非 None 局部变量供下方安全访问
    adv_short, adv_medium, adv_long = (
        advice_report.advice_short,
        advice_report.advice_medium,
        advice_report.advice_long,
    )
    assert adv_short is not None and adv_medium is not None and adv_long is not None

    # 6. 保存到日志
    if save_to_journal and journal:
        record = create_record_from_analysis(
            symbol=symbol,
            name=name,
            kind=kind,
            price=price,
            analysis_result={},
            advice_report={
                "overall_score": advice_report.overall_score,
                "overall_grade": advice_report.overall_grade,
                "overall_signal": advice_report.overall_signal,
                "tech_score": advice_report.tech_score,
                "momentum_score": advice_report.momentum_score,
                "volume_score": advice_report.volume_score,
                "risk_score": advice_report.risk_score,
                "advice_medium": {
                    "action": adv_medium.action.value,
                    "confidence": adv_medium.confidence,
                    "entry_price": adv_medium.entry_price,
                    "stop_loss": adv_medium.stop_loss,
                    "take_profit": adv_medium.take_profit,
                    "position_pct": adv_medium.position_pct,
                    "reasons": adv_medium.reasons,
                    "risks": adv_medium.risks,
                },
                "key_metrics": advice_report.key_metrics,
            },
        )
        journal.add(record)

    # 组装结果
    result = {
        "symbol": symbol,
        "name": name,
        "kind": kind,
        "status": "ok",
        "price": round(price, 2),
        "elapsed_s": round(time.time() - t0, 3),

        # 综合评分
        "overall_score": advice_report.overall_score,
        "overall_grade": advice_report.overall_grade,
        "overall_signal": advice_report.overall_signal,

        # 多因子评分
        "factor_score": factors["composite"],
        "factor_grade": factors["grade"],
        "factor_signal": factors["signal"],
        "factors": factors["factors"],
        "top_signals": factors["top_signals"],

        # 技术指标
        "indicators": {
            "macd": indicators.get("macd", {}),
            "atr": indicators.get("atr", {}),
            "kdj": indicators.get("kdj", {}),
            "obv": indicators.get("obv", {}),
            "vwap": indicators.get("vwap", {}),
            "ma_alignment": indicators.get("ma_alignment", {}),
            "ichimoku": indicators.get("ichimoku", {}),
            "composite": indicators.get("composite_score", 50),
        },

        # 成交量分析
        "volume": {
            "ratio": volume.get("volume_ratio", {}),
            "obv_slope": volume.get("obv_slope", {}),
            "divergence": volume.get("vp_divergence", {}),
            "money_flow": volume.get("money_flow", {}),
            "composite": volume.get("composite_score", 50),
        },

        # 筛选器结果
        "screener": screener_result.to_dict() if screener_result else None,
        "passed_screener": screener_result.passed if screener_result else None,

        # 投资建议 (键结构由 InvestmentAdvice.to_dict 统一给出, 对外契约不变)
        "advice": {
            "short": adv_short.to_dict(),
            "medium": adv_medium.to_dict(),
            "long": adv_long.to_dict(),
        },

        # 看多/看空逻辑
        "bull_case": advice_report.bull_case,
        "bear_case": advice_report.bear_case,

        # 操作策略
        "entry_strategy": advice_report.entry_strategy,
        "exit_strategy": advice_report.exit_strategy,
        "position_strategy": advice_report.position_strategy,

        # 风险管理
        "max_loss_pct": advice_report.max_loss_pct,
        "risk_reward_ratio": advice_report.risk_reward_ratio,

        # 格式化报告
        "report_text": format_report_text(advice_report),
    }

    return result


# ═══════════════════════════════════════════════════════════════════════
# 批量增强分析
# ═══════════════════════════════════════════════════════════════════════

def enhanced_batch_analyze(
    symbols: list[tuple[str, str, str]],  # [(code, name, kind), ...]
    loader_fn_stock=None,
    loader_fn_future=None,
    journal: AnalysisJournal | None = None,
    top_n: int = 10,
    min_score: float = 55.0,
    save_to_journal: bool = True,
) -> tuple[list[dict], dict]:
    """批量增强分析.

    Args:
        symbols: [(代码, 名称, 类型), ...]
        loader_fn_stock: 股票数据加载函数
        loader_fn_future: 期货数据加载函数
        journal: 分析日志实例
        top_n: 输出 Top N
        min_score: 最低分门槛
        save_to_journal: 是否保存到日志

    Returns:
        (results, log)
    """
    t0 = time.time()
    results = []

    for code, name, kind in symbols:
        try:
            loader = loader_fn_stock if kind == "stock" else loader_fn_future
            result = enhanced_analyze(
                symbol=code,
                name=name,
                kind=kind,
                loader_fn=loader,
                journal=journal,
                save_to_journal=save_to_journal,
            )

            if result.get("status") != "ok":
                continue

            if result.get("overall_score", 0) < min_score:
                continue

            results.append(result)

        except Exception as e:
            print(f"[enhanced_batch] {code} {name} 异常: {e}")

    # 排序: 通过筛选优先, 然后按综合分
    results.sort(
        key=lambda x: (x.get("passed_screener", False), x.get("overall_score", 0)),
        reverse=True,
    )
    results = results[:top_n]

    log = {
        "total_scanned": len(symbols),
        "passed_min_score": len(results),
        "top_n": len(results),
        "elapsed_s": round(time.time() - t0, 2),
    }

    return results, log


# ═══════════════════════════════════════════════════════════════════════
# 格式化输出
# ═══════════════════════════════════════════════════════════════════════

def format_analysis_summary(result: dict) -> str:
    """格式化分析结果摘要."""
    if result.get("status") != "ok":
        return f"{result.get('symbol', '?')} {result.get('name', '?')}: {result.get('error', '数据不足')}"

    lines = [
        f"═══ {result['name']}({result['symbol']}) ═══",
        f"价格: {result['price']:.2f}  评分: {result['overall_score']:.0f} ({result['overall_grade']}) {result['overall_signal']}",
        "",
        "【多因子】",
        f"  综合: {result['factor_score']:.0f}  技术: {result['indicators']['composite']:.0f}  成交量: {result['volume']['composite']:.0f}",
    ]

    # 因子详情
    for f in result.get("factors", []):
        lines.append(f"  {f['name']}: {f['score']:.0f} (权重{f['weight']:.0%})")

    # 关键信号
    if result.get("top_signals"):
        lines.append("")
        lines.append("【关键信号】")
        for sig in result["top_signals"]:
            lines.append(f"  {sig}")

    # 投资建议
    advice = result.get("advice", {})
    if advice:
        lines.append("")
        lines.append("【操作建议】")
        for horizon in ["short", "medium", "long"]:
            a = advice.get(horizon, {})
            lines.append(f"  {horizon}: {a.get('action', '?')} | 仓位{a.get('position_pct', '?')} | 止损{a.get('stop_loss', 0):.2f} | 止盈{a.get('take_profit', 0):.2f}")

    # 看多逻辑
    if result.get("bull_case"):
        lines.append("")
        lines.append("【看多逻辑】")
        for r in result["bull_case"]:
            lines.append(f"  ✅ {r}")

    # 看空逻辑
    if result.get("bear_case"):
        lines.append("")
        lines.append("【风险提示】")
        for r in result["bear_case"]:
            lines.append(f"  ⚠️ {r}")

    return "\n".join(lines)
