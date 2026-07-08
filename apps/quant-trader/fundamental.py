"""财务报表分析模块 — 自动分析财报关键指标.

分析维度:
  1. 盈利能力 (ROE/ROA/净利润率)
  2. 成长能力 (营收增长/利润增长)
  3. 偿债能力 (资产负债率/流动比率)
  4. 运营效率 (存货周转/应收账款周转)
  5. 估值指标 (PE/PB/PS)
"""
from __future__ import annotations

from dataclasses import dataclass

from .log import get_logger

logger = get_logger("fundamental")


@dataclass
class FinancialAnalysis:
    """财务分析结果."""
    symbol: str
    name: str
    # 盈利能力
    roe: float              # 净资产收益率
    roa: float              # 总资产收益率
    net_margin: float       # 净利润率
    # 成长能力
    revenue_growth: float   # 营收增长率
    profit_growth: float    # 利润增长率
    # 偿债能力
    debt_ratio: float       # 资产负债率
    current_ratio: float    # 流动比率
    # 估值指标
    pe_ratio: float         # 市盈率
    pb_ratio: float         # 市净率
    # 综合评分
    score: float            # 0-100 综合评分
    grade: str              # A/B/C/D 评级
    signal: str             # "BUY" | "SELL" | "HOLD"
    reason: str             # 分析原因


def get_financial_data(symbol: str) -> dict | None:
    """获取财务数据.

    Args:
        symbol: 股票代码

    Returns:
        dict: 财务数据
    """
    try:
        import akshare as ak

        # 获取财务指标
        df = ak.stock_financial_analysis_indicator(symbol=symbol)

        if df is None or df.empty:
            return None

        # 取最新一期数据
        latest = df.iloc[0]

        return {
            "roe": float(latest.get("净资产收益率(%)", 0)),
            "roa": float(latest.get("总资产收益率(%)", 0)),
            "net_margin": float(latest.get("销售净利率(%)", 0)),
            "revenue_growth": float(latest.get("主营业务收入增长率(%)", 0)),
            "profit_growth": float(latest.get("净利润增长率(%)", 0)),
            "debt_ratio": float(latest.get("资产负债率(%)", 0)),
            "current_ratio": float(latest.get("流动比率", 0)),
        }
    except Exception as e:
        logger.warning("获取财务数据失败 %s: %s", symbol, e)
        return None


def get_valuation_data(symbol: str) -> dict | None:
    """获取估值数据.

    Args:
        symbol: 股票代码

    Returns:
        dict: 估值数据
    """
    try:
        import akshare as ak

        # 获取实时行情
        df = ak.stock_zh_a_spot()

        if df is None or df.empty:
            return None

        # 查找股票
        row = df[df['代码'] == symbol]

        if row.empty:
            return None

        r = row.iloc[0]

        return {
            "pe_ratio": float(r.get('市盈率-动态', 0) or 0),
            "pb_ratio": float(r.get('市净率', 0) or 0),
            "total_market_value": float(r.get('总市值', 0) or 0),
        }
    except Exception as e:
        logger.warning("获取估值数据失败 %s: %s", symbol, e)
        return None


def analyze_financial_health(financial_data: dict) -> dict:
    """分析财务健康度.

    Args:
        financial_data: 财务数据

    Returns:
        dict: 分析结果
    """
    score = 50
    reasons = []

    # 1. 盈利能力 (30分)
    roe = financial_data.get("roe", 0)
    if roe > 15:
        score += 15
        reasons.append(f"ROE优秀({roe:.1f}%)")
    elif roe > 10:
        score += 10
        reasons.append(f"ROE良好({roe:.1f}%)")
    elif roe > 5:
        score += 5
        reasons.append(f"ROE一般({roe:.1f}%)")
    else:
        score -= 5
        reasons.append(f"ROE偏低({roe:.1f}%)")

    # 2. 成长能力 (30分)
    revenue_growth = financial_data.get("revenue_growth", 0)
    profit_growth = financial_data.get("profit_growth", 0)

    if revenue_growth > 20:
        score += 15
        reasons.append(f"营收高增长({revenue_growth:.1f}%)")
    elif revenue_growth > 10:
        score += 10
        reasons.append(f"营收增长({revenue_growth:.1f}%)")
    elif revenue_growth > 0:
        score += 5
        reasons.append(f"营收微增({revenue_growth:.1f}%)")
    else:
        score -= 10
        reasons.append(f"营收下滑({revenue_growth:.1f}%)")

    if profit_growth > 20:
        score += 15
        reasons.append(f"利润高增长({profit_growth:.1f}%)")
    elif profit_growth > 10:
        score += 10
        reasons.append(f"利润增长({profit_growth:.1f}%)")
    elif profit_growth > 0:
        score += 5
        reasons.append(f"利润微增({profit_growth:.1f}%)")
    else:
        score -= 10
        reasons.append(f"利润下滑({profit_growth:.1f}%)")

    # 3. 偿债能力 (20分)
    debt_ratio = financial_data.get("debt_ratio", 0)
    current_ratio = financial_data.get("current_ratio", 0)

    if debt_ratio < 40:
        score += 10
        reasons.append(f"负债率低({debt_ratio:.1f}%)")
    elif debt_ratio < 60:
        score += 5
        reasons.append(f"负债率适中({debt_ratio:.1f}%)")
    else:
        score -= 10
        reasons.append(f"负债率高({debt_ratio:.1f}%)")

    if current_ratio > 2:
        score += 10
        reasons.append(f"流动比率优秀({current_ratio:.1f})")
    elif current_ratio > 1:
        score += 5
        reasons.append(f"流动比率良好({current_ratio:.1f})")
    else:
        score -= 5
        reasons.append(f"流动比率偏低({current_ratio:.1f})")

    score = max(0, min(100, score))

    return {
        "score": score,
        "reasons": reasons,
    }


def analyze_valuation(valuation_data: dict, financial_data: dict) -> dict:
    """分析估值水平.

    Args:
        valuation_data: 估值数据
        financial_data: 财务数据

    Returns:
        dict: 分析结果
    """
    score = 50
    reasons = []

    pe_ratio = valuation_data.get("pe_ratio", 0)
    pb_ratio = valuation_data.get("pb_ratio", 0)
    roe = financial_data.get("roe", 0)

    # PE 分析
    if pe_ratio > 0:
        if pe_ratio < 15:
            score += 15
            reasons.append(f"PE低估({pe_ratio:.1f})")
        elif pe_ratio < 25:
            score += 5
            reasons.append(f"PE合理({pe_ratio:.1f})")
        elif pe_ratio < 40:
            score -= 5
            reasons.append(f"PE偏高({pe_ratio:.1f})")
        else:
            score -= 15
            reasons.append(f"PE高估({pe_ratio:.1f})")

    # PB 分析
    if pb_ratio > 0:
        if pb_ratio < 1:
            score += 10
            reasons.append(f"PB低估({pb_ratio:.1f})")
        elif pb_ratio < 2:
            score += 5
            reasons.append(f"PB合理({pb_ratio:.1f})")
        elif pb_ratio < 3:
            score -= 5
            reasons.append(f"PB偏高({pb_ratio:.1f})")
        else:
            score -= 10
            reasons.append(f"PB高估({pb_ratio:.1f})")

    # PEG 分析 (PE/增长率)
    profit_growth = financial_data.get("profit_growth", 0)
    if pe_ratio > 0 and profit_growth > 0:
        peg = pe_ratio / profit_growth
        if peg < 1:
            score += 10
            reasons.append(f"PEG低估({peg:.1f})")
        elif peg < 2:
            score += 5
            reasons.append(f"PEG合理({peg:.1f})")
        else:
            score -= 5
            reasons.append(f"PEG偏高({peg:.1f})")

    score = max(0, min(100, score))

    return {
        "score": score,
        "reasons": reasons,
    }


def analyze_fundamental(symbol: str, name: str = "") -> FinancialAnalysis:
    """基本面分析主函数.

    Args:
        symbol: 股票代码
        name: 股票名称

    Returns:
        FinancialAnalysis: 分析结果
    """
    # 获取财务数据
    financial_data = get_financial_data(symbol)
    if financial_data is None:
        financial_data = {
            "roe": 0, "roa": 0, "net_margin": 0,
            "revenue_growth": 0, "profit_growth": 0,
            "debt_ratio": 0, "current_ratio": 0,
        }

    # 获取估值数据
    valuation_data = get_valuation_data(symbol)
    if valuation_data is None:
        valuation_data = {"pe_ratio": 0, "pb_ratio": 0}

    # 分析财务健康度
    health_result = analyze_financial_health(financial_data)

    # 分析估值水平
    valuation_result = analyze_valuation(valuation_data, financial_data)

    # 综合评分
    total_score = (health_result["score"] * 0.6 + valuation_result["score"] * 0.4)

    # 评级
    if total_score >= 75:
        grade = "A"
        signal = "BUY"
    elif total_score >= 60:
        grade = "B"
        signal = "BUY"
    elif total_score >= 45:
        grade = "C"
        signal = "HOLD"
    elif total_score >= 30:
        grade = "D"
        signal = "SELL"
    else:
        grade = "E"
        signal = "SELL"

    # 原因
    all_reasons = health_result["reasons"] + valuation_result["reasons"]
    reason = "; ".join(all_reasons[:3])

    return FinancialAnalysis(
        symbol=symbol,
        name=name,
        roe=financial_data.get("roe", 0),
        roa=financial_data.get("roa", 0),
        net_margin=financial_data.get("net_margin", 0),
        revenue_growth=financial_data.get("revenue_growth", 0),
        profit_growth=financial_data.get("profit_growth", 0),
        debt_ratio=financial_data.get("debt_ratio", 0),
        current_ratio=financial_data.get("current_ratio", 0),
        pe_ratio=valuation_data.get("pe_ratio", 0),
        pb_ratio=valuation_data.get("pb_ratio", 0),
        score=round(total_score, 1),
        grade=grade,
        signal=signal,
        reason=reason,
    )


def get_fundamental_signal(symbol: str, name: str = "") -> dict:
    """获取基本面信号.

    Returns:
        dict: {
            "signal": str,
            "confidence": float,
            "score": float,
            "grade": str,
            "reason": str,
        }
    """
    result = analyze_fundamental(symbol, name)

    return {
        "signal": result.signal,
        "confidence": result.score,
        "score": result.score,
        "grade": result.grade,
        "reason": result.reason,
    }
