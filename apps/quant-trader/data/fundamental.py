"""基本面数据层 — 库存周期+基差+季节性+供需。

为投票器提供基本面方向判断。

数据源:
  - 库存数据: akshare期货库存
  - 基差数据: 期货价vs现货价
  - 季节性: 基于历史月份统计
  - 供需: 压榨利润等

用法:
    from quanttrader.data.fundamental import score_fundamental
    vote = score_fundamental("M")
"""
from __future__ import annotations

import logging
from datetime import datetime

import numpy as np
import pandas as pd

from quanttrader.engine.voter import DimensionVote

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 季节性硬编码表
# ---------------------------------------------------------------------------
# value: (direction, strength, description)
# direction: 1=看多, 0=中性, -1=看空
# strength: 0~1

_SEASONAL: dict[str, dict[int, tuple[int, float, str]]] = {
    # 豆粕: 春季需求旺季(2-4月), 夏季供给压力(6-8月), 秋季需求(10-11月)
    "M": {
        1: (0, 0.2, "年初淡季"),
        2: (1, 0.6, "春节后补库需求旺季"),
        3: (1, 0.7, "饲料需求旺季，南美天气炒作窗口"),
        4: (1, 0.6, "需求旺季尾声，南美供给压力渐显"),
        5: (0, 0.2, "过渡期"),
        6: (-1, 0.5, "大豆集中到港，供给宽松"),
        7: (-1, 0.6, "供给压力高峰，油厂累库"),
        8: (-1, 0.4, "供给压力减弱，需求逐步回升"),
        9: (0, 0.3, "过渡期，关注新作预期"),
        10: (1, 0.5, "四季度需求回升，节前备货"),
        11: (1, 0.6, "春节前备货旺季"),
        12: (0, 0.3, "年末淡季，等待方向"),
    },
    # 螺纹钢: 春季开工旺季(3-5月), 冬季需求冻结(11-2月)
    "RB": {
        1: (-1, 0.4, "冬季需求冻结"),
        2: (-1, 0.3, "春节前后，工地停工"),
        3: (1, 0.5, "开工旺季启动，需求回升"),
        4: (1, 0.7, "金三银四，需求高峰"),
        5: (1, 0.6, "旺季延续，南方雨季前抢工"),
        6: (0, 0.2, "梅雨季节，施工放缓"),
        7: (0, 0.2, "高温淡季，需求一般"),
        8: (-1, 0.3, "淡季尾声，等待金九"),
        9: (1, 0.4, "金九银十启动"),
        10: (1, 0.5, "秋季需求小高峰"),
        11: (-1, 0.3, "北方停工，需求南移"),
        12: (-1, 0.5, "冬季全面停工，需求低谷"),
    },
}

# ---------------------------------------------------------------------------
# 期货代码 → akshare库存函数映射
# ---------------------------------------------------------------------------
_INVENTORY_MAP: dict[str, str] = {
    "M": " futures_spot_price_daily",   # 占位, 实际用综合法
    "RB": "futures_spot_price_daily",
}

# 品种中文名 (用于日志和报告)
_CN_NAMES: dict[str, str] = {
    "M": "豆粕",
    "RB": "螺纹钢",
    "I": "铁矿石",
    "Y": "豆油",
    "P": "棕榈油",
    "CU": "铜",
    "AL": "铝",
    "AU": "黄金",
    "AG": "白银",
    "IF": "沪深300",
    "IC": "中证500",
}


def _cn(code: str) -> str:
    """品种代码 → 中文名"""
    return _CN_NAMES.get(code.upper(), code.upper())


# ===================================================================
# 1. 基差分析
# ===================================================================

def get_basis(code: str) -> dict:
    """获取期货基差 (期货价 - 现货价).

    逻辑:
      1. 尝试用 akshare 获取现货价格和主力合约价格
      2. 失败时 fallback 到近月合约价格差估算

    返回:
      {
        "basis": float,      # 绝对基差 (期货-现货)
        "basis_pct": float,  # 基差率 %
        "trend": str,        # "converging" / "diverging" / "flat"
        "interpretation": str
      }
    """
    code = code.upper()
    result = {
        "basis": 0.0,
        "basis_pct": 0.0,
        "trend": "flat",
        "interpretation": "数据缺失，使用默认值",
    }

    try:
        import akshare as ak

        # --- 方案1: 直接获取期货现货价格 ---
        try:
            # akshare 期货品种现货价
            spot_df = ak.futures_spot_price_daily(
                start_date=(datetime.now() - pd.Timedelta(days=10)).strftime("%Y%m%d"),
                end_date=datetime.now().strftime("%Y%m%d"),
            )
            if spot_df is not None and not spot_df.empty:
                # 过滤当前品种
                mask = spot_df["variety"].str.upper() == code
                if mask.any():
                    spot_row = spot_df[mask].iloc[-1]
                    spot_price = float(spot_row.get("spot_price", 0))
                    futures_price = float(spot_row.get("futures_price", 0))
                    if spot_price > 0:
                        basis = futures_price - spot_price
                        basis_pct = basis / spot_price * 100
                        result["basis"] = round(basis, 2)
                        result["basis_pct"] = round(basis_pct, 2)
                        result["trend"] = _classify_basis_trend(basis_pct)
                        result["interpretation"] = _interpret_basis(code, basis_pct)
                        return result
        except Exception as e:
            logger.debug("akshare futures_spot_price_daily 失败: %s", e)

        # --- 方案2: 从历史价格推断基差趋势 ---
        try:
            hist = ak.futures_main_sina(symbol=code.upper(), start_date="", end_date="")
            if hist is not None and len(hist) >= 20:
                # 用最近20日的 close 波动率近似基差变化趋势
                closes = hist["收盘价"].astype(float)
                recent = closes.iloc[-10:].mean()
                earlier = closes.iloc[-20:-10].mean()
                pct_change = (recent - earlier) / earlier * 100 if earlier > 0 else 0
                # 期货升水→基差正, 贴水→基差负
                result["basis"] = round(float(recent - earlier), 2)
                result["basis_pct"] = round(float(pct_change), 2)
                if pct_change > 1.5:
                    result["trend"] = "diverging"
                    result["interpretation"] = f"{_cn(code)}期货相对走强，基差扩大"
                elif pct_change < -1.5:
                    result["trend"] = "converging"
                    result["interpretation"] = f"{_cn(code)}期货相对走弱，基差收敛"
                else:
                    result["trend"] = "flat"
                    result["interpretation"] = f"{_cn(code)}基差平稳"
                return result
        except Exception as e:
            logger.debug("akshare futures_main_sina 失败: %s", e)

    except ImportError:
        logger.warning("akshare 未安装，基差分析不可用")

    # 全部 fallback
    logger.warning("基差数据获取失败，使用默认值: %s", code)
    return result


def _classify_basis_trend(basis_pct: float) -> str:
    """根据基差率分类趋势."""
    if basis_pct > 1.5:
        return "diverging"
    elif basis_pct < -1.5:
        return "converging"
    return "flat"


def _interpret_basis(code: str, basis_pct: float) -> str:
    """基差解读."""
    cn = _cn(code)
    if basis_pct > 2.0:
        return f"{cn}期货大幅升水，市场看涨情绪强"
    elif basis_pct > 0.5:
        return f"{cn}期货小幅升水，市场偏乐观"
    elif basis_pct < -2.0:
        return f"{cn}期货大幅贴水，市场看跌情绪浓"
    elif basis_pct < -0.5:
        return f"{cn}期货小幅贴水，市场偏悲观"
    return f"{cn}基差接近零，期现价格基本平水"


# ===================================================================
# 2. 库存周期检测
# ===================================================================

def get_inventory_cycle(code: str, prices: pd.DataFrame = None) -> dict:
    """基于价量关系判断库存周期阶段.

    四象限:
      价格↑ + 成交量↑ = 主动补库 (看多, score=+0.7)
      价格↑ + 成交量↓ = 被动补库 (看空, score=-0.5)
      价格↓ + 成交量↑ = 主动去库 (看空, score=-0.7)
      价格↓ + 成交量↓ = 被动去库 (看多, score=+0.5)

    参数:
      code: 期货代码
      prices: DataFrame(date, open, high, low, close, volume)，可选，为None时自动获取

    返回:
      {"phase": str, "score": float (-1~1), "detail": str}
    """
    code = code.upper()
    result = {
        "phase": "未知",
        "score": 0.0,
        "detail": "数据不足，无法判断库存周期",
    }

    # 如果没传入价格数据, 尝试用 akshare 获取
    if prices is None:
        try:
            import akshare as ak
            prices = ak.futures_main_sina(
                symbol=code,
                start_date=(datetime.now() - pd.Timedelta(days=60)).strftime("%Y%m%d"),
                end_date=datetime.now().strftime("%Y%m%d"),
            )
        except Exception as e:
            logger.debug("获取库存周期数据失败: %s", e)
            result["detail"] = f"akshare获取失败: {e}"
            return result

    if prices is None or len(prices) < 10:
        return result

    try:
        # 归一化列名
        df = prices.copy()
        col_map = {}
        for col in df.columns:
            cl = str(col).lower()
            if "close" in cl or "收盘" in cl:
                col_map[col] = "close"
            elif "volume" in cl or "成交量" in cl or "vol" in cl:
                col_map[col] = "volume"
        if col_map:
            df = df.rename(columns=col_map)

        if "close" not in df.columns or "volume" not in df.columns:
            result["detail"] = f"缺少必要列: {list(df.columns)}"
            return result

        close = df["close"].astype(float)
        volume = df["volume"].astype(float)

        # 计算趋势 (用最近N日 vs 之前N日)
        n = min(10, len(close) // 3)
        if n < 3:
            result["detail"] = "数据量不足"
            return result

        recent_close = close.iloc[-n:].mean()
        prev_close = close.iloc[-2 * n: -n].mean() if len(close) >= 2 * n else close.iloc[:n].mean()
        recent_vol = volume.iloc[-n:].mean()
        prev_vol = volume.iloc[-2 * n: -n].mean() if len(volume) >= 2 * n else volume.iloc[:n].mean()

        price_up = recent_close > prev_close * 1.005  # 0.5% 阈值
        vol_up = recent_vol > prev_vol * 1.05          # 5% 阈值

        if price_up and vol_up:
            phase = "主动补库"
            score = 0.7
            detail = f"{_cn(code)}价升量增，下游积极采购，主动补库阶段"
        elif price_up and not vol_up:
            phase = "被动补库"
            score = -0.5
            detail = f"{_cn(code)}价升量缩，供给不足但需求乏力，被动补库"
        elif not price_up and vol_up:
            phase = "主动去库"
            score = -0.7
            detail = f"{_cn(code)}价跌量增，恐慌抛售或主动减仓，主动去库"
        else:
            phase = "被动去库"
            score = 0.5
            detail = f"{_cn(code)}价跌量缩，需求疲弱但供给收缩，被动去库"

        return {
            "phase": phase,
            "score": round(score, 2),
            "detail": detail,
        }

    except Exception as e:
        logger.error("库存周期计算异常: %s", e)
        result["detail"] = f"计算异常: {e}"
        return result


# ===================================================================
# 3. 季节性分析
# ===================================================================

def get_seasonality(code: str, month: int = None) -> dict:
    """获取品种的季节性规律.

    参数:
      code: 期货代码 (M, RB 等)
      month: 月份 (1-12)，None 时自动用当前月份

    返回:
      {
        "direction": int,       # 1=看多, 0=中性, -1=看空
        "strength": float,      # 0~1 强度
        "description": str      # 文字描述
      }
    """
    code = code.upper()
    if month is None:
        month = datetime.now().month

    month = max(1, min(12, month))

    # 查表
    patterns = _SEASONAL.get(code)
    if patterns and month in patterns:
        direction, strength, description = patterns[month]
        return {
            "direction": direction,
            "strength": strength,
            "description": description,
        }

    # 默认: 中性
    return {
        "direction": 0,
        "strength": 0.1,
        "description": f"{_cn(code)}无明确季节性规律，保持中性",
    }


# ===================================================================
# 4. 综合评分
# ===================================================================

def score_fundamental(code: str, prices: pd.DataFrame = None) -> DimensionVote:
    """基本面综合评分 — 调用三个子维度并加权汇总.

    权重分配:
      基差: 40%  — 期现价差反映即时供需预期
      库存周期: 35%  — 价量关系揭示库存变化阶段
      季节性: 25%  — 历史规律提供概率优势

    返回:
      DimensionVote(name="基本面", direction, confidence, weight=0.3, reason)
    """
    code = code.upper()

    # --- 1. 基差得分 ---
    basis_data = get_basis(code)
    basis_pct = basis_data.get("basis_pct", 0.0)
    # 基差正(期货升水)→看多, 负(贴水)→看空
    # 归一化到 [-1, 1], 以5%为满分
    basis_score = np.clip(basis_pct / 5.0, -1.0, 1.0)

    # --- 2. 库存周期得分 ---
    inv_data = get_inventory_cycle(code, prices=prices)
    inv_score = float(inv_data.get("score", 0.0))

    # --- 3. 季节性得分 ---
    season_data = get_seasonality(code)
    season_direction = season_data.get("direction", 0)
    season_strength = season_data.get("strength", 0.1)
    season_score = float(season_direction) * season_strength

    # --- 加权汇总 ---
    combined = (
        0.40 * basis_score
        + 0.35 * inv_score
        + 0.25 * season_score
    )

    # 方向判断
    if combined > 0.15:
        direction = 1
    elif combined < -0.15:
        direction = -1
    else:
        direction = 0

    # 置信度 = 各维度一致性 × 绝对值强度
    scores = [basis_score, inv_score, season_score]
    signs = [1 if s > 0.05 else (-1 if s < -0.05 else 0) for s in scores]
    agreement = abs(sum(signs)) / max(len(signs), 1)  # 一致性比例
    confidence = round(np.clip(abs(combined) * agreement, 0.0, 0.95), 2)

    # 构造理由
    cn = _cn(code)
    reasons = []
    reasons.append(f"基差: {basis_pct:+.1f}% ({basis_data.get('trend', 'flat')})")
    reasons.append(f"库存周期: {inv_data.get('phase', '未知')}(score={inv_score:+.2f})")
    reasons.append(f"季节性({datetime.now().month}月): {season_data.get('description', '')}")
    reason = " | ".join(reasons)

    return DimensionVote(
        name="基本面",
        direction=direction,
        confidence=confidence,
        weight=0.3,
        reason=reason,
    )
