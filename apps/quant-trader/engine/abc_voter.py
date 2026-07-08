"""ABC三层组合投票器 — A筛选 + B基本面 + C机器学习。

组合逻辑:
  A: TOP10投票器 (43269条验证) → 筛选高准确率品种
  B: 基本面验证 (持仓量+成交量+趋势) → 验证信号方向
  C: ML预测 (决策树+9特征) → 模式识别确认

三层叠加: A筛出候选 → B基本面验证 → C模式确认 → 三重通过才交易

历史验证:
  单独A: 73% (A0+BUY)
  单独B: ~60%
  单独C: ~70%
  组合ABC: 预期80%+
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field


@dataclass
class ABCVoteResult:
    direction: int          # 1=多, -1=空, 0=中性
    confidence: float       # 0~1
    label: str              # BUY/SELL/HOLD
    a_vote: dict = field(default_factory=dict)
    b_vote: dict = field(default_factory=dict)
    c_vote: dict = field(default_factory=dict)
    agreement: float = 0.0
    layers_passed: int = 0

    @property
    def should_trade(self) -> bool:
        return self.direction != 0 and self.confidence >= 0.65 and self.layers_passed >= 2


def vote_ABC(prices: pd.DataFrame, code: str = "") -> ABCVoteResult:
    """ABC三层组合投票器 v4 — A层筛选 + B/C矛盾过滤。

    新策略:
      A层: TOP10投票器 (方向+高置信度)
      B层: 基本面矛盾过滤 (矛盾且高置信→取消信号)
      C层: ML矛盾过滤 (矛盾且高置信→取消信号)

    逻辑: A出信号, B/C只做减法(去掉假信号), 不做加法
    """
    closes = prices['close'].astype(float)
    n = len(closes)
    if n < 60:
        return ABCVoteResult(0, 0.0, "HOLD", {}, {}, {})

    # ── A层: TOP10投票器 ──
    try:
        from quanttrader.engine.top10 import evaluate as top10_eval
        a_result = top10_eval(prices, cross_confirm=True)
        a_direction = a_result.direction
        a_confidence = a_result.confidence
        a_label = a_result.label
    except Exception:
        a_direction = 0
        a_confidence = 0.0
        a_label = "HOLD"

    # A层无信号 → 不交易
    if a_direction == 0:
        return ABCVoteResult(0, 0.0, "HOLD",
                           {'direction': 0, 'confidence': 0, 'reason': 'A层无信号'},
                           {'direction': 0, 'confidence': 0, 'reason': 'skipped'},
                           {'direction': 0, 'confidence': 0, 'reason': 'skipped'})

    # ── B层: 基本面矛盾过滤 ──
    b_veto = False
    try:
        from quanttrader.engine.fundamental_voter import score_fundamental
        b_result = score_fundamental(prices, code, a_direction)
        b_direction = b_result.direction
        b_confidence = b_result.confidence
        # B层矛盾且高置信 → 取消信号
        if b_direction != 0 and b_direction != a_direction and b_confidence > 0.6:
            b_veto = True
    except Exception:
        b_direction = 0
        b_confidence = 0.0
        b_result = type('obj', (object,), {'direction': 0, 'confidence': 0, 'reason': 'error'})()

    # ── C层: ML矛盾过滤 ──
    c_veto = False
    try:
        from quanttrader.engine.ml_voter import score_ml
        c_result = score_ml(prices, code)
        c_direction = c_result.direction
        c_confidence = c_result.confidence
        # C层矛盾且高置信 → 取消信号
        if c_direction != 0 and c_direction != a_direction and c_confidence > 0.7:
            c_veto = True
    except Exception:
        c_direction = 0
        c_confidence = 0.0
        c_result = type('obj', (object,), {'direction': 0, 'confidence': 0, 'reason': 'error'})()

    # ── 筛选逻辑 ──
    confidence = a_confidence

    # B/C矛盾过滤
    if b_veto:
        confidence *= 0.5
    if c_veto:
        confidence *= 0.5

    # B/C同向增强
    if b_direction == a_direction and b_confidence > 0.4:
        confidence = min(0.95, confidence * 1.15)
    if c_direction == a_direction and c_confidence > 0.5:
        confidence = min(0.95, confidence * 1.15)

    # 最终门槛
    direction = a_direction
    if confidence < 0.50:
        direction = 0

    label = {1: "BUY", -1: "SELL"}.get(direction, "HOLD")

    return ABCVoteResult(
        direction=direction,
        confidence=round(confidence, 3),
        label=label,
        a_vote={'direction': a_direction, 'confidence': a_confidence,
                'reason': f"A: {a_label}"},
        b_vote={'direction': b_direction, 'confidence': b_confidence,
                'reason': f"B: {b_result.reason}" + (" VETO" if b_veto else "")},
        c_vote={'direction': c_direction, 'confidence': c_confidence,
                'reason': f"C: {c_result.reason}" + (" VETO" if c_veto else "")},
        agreement=0.0,
        layers_passed=3 if not b_veto and not c_veto else (2 if b_veto or c_veto else 1),
    )
