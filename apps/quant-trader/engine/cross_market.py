"""跨品种联动确认 — 相关品种信号叠加增强置信度。

核心原理: 同产业链品种走势一致时，信号更可靠。

例子:
  M豆粕看多 + A豆一看多 + Y豆油看多 = 三重确认 → 置信度+15%
  M豆粕看多 + A豆一看空 = 分化 → 不交易

相关品种映射:
  M(豆粕)   → [A(豆一), Y(豆油), P(棕榈油), RM(菜粕)]
  RB(螺纹)  → [HC(热卷), I(铁矿), J(焦炭)]
  CU(铜)    → [AL(铝), ZN(锌), NI(镍)]
"""
from __future__ import annotations

from typing import ClassVar

import pandas as pd

from quanttrader.engine.voter import DimensionVote

# ══════════════════════════════════════════════════════════════════
# 相关品种映射
# ══════════════════════════════════════════════════════════════════

# 品种组: 产业链关联的品种集合，组内任一品种都能找到同组其他品种
_CHAIN_GROUPS: list[list[str]] = [
    ["M", "A", "Y", "P", "RM"],     # 油脂蛋白链
    ["RB", "HC", "I", "J", "JM"],   # 黑色系
    ["CU", "AL", "ZN", "NI"],       # 有色金属
    ["FU", "BU", "SC", "PG"],       # 能化链
    ["TA", "MA", "EG", "EB", "PP"], # 化工链
    ["SA", "FG"],                    # 玻璃纯碱
    ["AU", "AG"],                    # 贵金属
    ["CF", "SR", "AP"],              # 农产品
    ["IF", "IH", "IC"],             # 股指期货
]


class CrossMarketAnalyzer:
    """跨品种联动分析器。

    用法:
        analyzer = CrossMarketAnalyzer("M")
        result = analyzer.analyze()
        # result["agreement_pct"] — 同向品种占比
        # result["confidence"]   — 联动置信度
    """

    def __init__(self, code: str) -> None:
        self.code = code.upper()

    def _get_related_codes(self) -> list[str]:
        """返回同产业链的关联品种代码列表。"""
        for group in _CHAIN_GROUPS:
            if self.code in group:
                return [c for c in group if c != self.code]
        return []

    # 模块级缓存: {code: DataFrame}，避免重复网络请求（类级共享，故显式标注 ClassVar）
    _price_cache: ClassVar[dict[str, pd.DataFrame]] = {}

    def _fetch_prices(self, code: str, days: int = 30) -> pd.DataFrame | None:
        """获取指定品种的历史价格数据。有缓存，失败返回 None。

        原实现调用已禁用的 sina_futures.get_history(恒抛 NotImplementedError 被吞)，
        导致跨品种维度永远拿不到数据、恒投中性票。改用 akshare 主力连续真实数据源
        (与 tracker/verify_hl_predictions 同源)；无 akshare 时该源会回退合成数据，
        合成数据不可参与生产投票，此处显式拒绝并返回 None。
        """
        cache_key = f"{code}_{days}"
        if cache_key in self._price_cache:
            return self._price_cache[cache_key]
        try:
            from quanttrader.data.futures_history import get_futures_history
            from quanttrader.data.synthetic_futures_provider import is_synthetic

            df = get_futures_history(code, days=days)
            if df is None or len(df) < 5 or is_synthetic(df):
                return None
            self._price_cache[cache_key] = df
            return df
        except Exception:
            return None

    @staticmethod
    def _compute_trend(prices: pd.DataFrame) -> int:
        """判断趋势方向。SMA5 vs SMA10。

        Returns:
            1=上升, -1=下降, 0=持平
        """
        try:
            closes = prices["close"].astype(float)
            if len(closes) < 5:
                return 0
            sma5 = float(closes.tail(5).mean())
            sma10 = float(closes.tail(10).mean()) if len(closes) >= 10 else float(closes.mean())
            diff_pct = (sma5 - sma10) / sma10 * 100 if sma10 != 0 else 0
            if diff_pct > 0.15:
                return 1
            elif diff_pct < -0.15:
                return -1
            return 0
        except Exception:
            return 0

    def analyze(self, days: int = 30, prices: pd.DataFrame | None = None) -> dict:
        """主分析入口。获取所有关联品种数据，计算趋势一致性。

        Args:
            days: 回看天数
            prices: 主品种价格数据 (外部传入，不在此函数内获取)

        Returns:
            {
                "primary": str,
                "related": {code: {"trend": int, "ret_5d": float}},
                "agreement_pct": float,
                "direction": int,
                "confidence": float,
                "description": str,
            }
        """
        related_codes = self._get_related_codes()

        # 主品种趋势来自外部传入的 prices DataFrame
        if prices is None or len(prices) < 5:
            return self._neutral_result("主品种数据不足")

        primary_trend = self._compute_trend(prices)

        # 相关品种数据
        related_info: dict[str, dict] = {}
        valid_count = 0
        agree_count = 0

        for code in related_codes:
            df = self._fetch_prices(code, days=days)
            if df is None:
                continue

            valid_count += 1
            trend = self._compute_trend(df)

            # 5日收益率
            ret_5d = 0.0
            try:
                closes = df["close"].astype(float)
                if len(closes) >= 6:
                    ret_5d = (float(closes.iloc[-1]) / float(closes.iloc[-6]) - 1) * 100
            except Exception:
                pass

            related_info[code] = {"trend": trend, "ret_5d": round(ret_5d, 2)}

            if trend == primary_trend and trend != 0:
                agree_count += 1

        if valid_count == 0:
            return self._neutral_result("无相关品种数据")

        # 一致性百分比
        agreement_pct = agree_count / valid_count if valid_count > 0 else 0.0

        # 方向: 主品种趋势
        direction = primary_trend

        # 置信度: 基础0.5 + 一致性加成 (最高+0.35) + 三重确认加成 (+0.05)
        confidence = 0.50 + agreement_pct * 0.35
        if agree_count >= 2:
            confidence += 0.05
        confidence = round(min(0.90, confidence), 3)

        # 描述
        agree_names = [c for c, info in related_info.items() if info["trend"] == direction and direction != 0]
        disagree_names = [c for c, info in related_info.items() if info["trend"] == -direction and direction != 0]
        dir_label = "看多" if direction == 1 else ("看空" if direction == -1 else "震荡")

        parts = [f"主品种{self.code}{dir_label}"]
        if agree_names:
            parts.append(f"同向:{','.join(agree_names)}")
        if disagree_names:
            parts.append(f"分歧:{','.join(disagree_names)}")
        parts.append(f"一致率{agreement_pct:.0%}")

        return {
            "primary": self.code,
            "related": related_info,
            "agreement_pct": round(agreement_pct, 3),
            "direction": direction,
            "confidence": confidence,
            "description": " | ".join(parts),
        }

    def _neutral_result(self, reason: str) -> dict:
        """返回中性结果。"""
        return {
            "primary": self.code,
            "related": {},
            "agreement_pct": 0.0,
            "direction": 0,
            "confidence": 0.0,
            "description": reason,
        }


def score_cross_market(prices: pd.DataFrame, code: str = "") -> DimensionVote:
    """跨品种联动评分。

    创建 CrossMarketAnalyzer，运行分析，返回 DimensionVote。

    Args:
        prices: 主品种价格数据
        code: 主品种代码 (如 "M")

    Returns:
        DimensionVote(name="跨品种", weight=0.7)
    """
    if not code:
        # 尝试从 DataFrame 推断
        code = ""

    analyzer = CrossMarketAnalyzer(code)
    result = analyzer.analyze(prices=prices)

    direction = result["direction"]
    confidence = result["confidence"]
    description = result["description"]

    # 无数据时返回中性
    if confidence == 0.0:
        return DimensionVote(
            name="跨品种", direction=0, confidence=0.0,
            weight=0.7, reason=description,
        )

    return DimensionVote(
        name="跨品种", direction=direction, confidence=confidence,
        weight=0.7, reason=description,
    )
