"""交易建议卡 — 系统最终输出给用户看的东西。"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class TradeCard:
    """一张交易建议卡。"""
    # 基本信息
    id: str = ""
    symbol: str = ""
    direction: str = ""  # "BUY" / "SELL" / ""
    current_price: float = 0.0

    # v530预测
    pred_high: float = 0.0
    pred_low: float = 0.0
    upside_pct: float = 0.0
    downside_pct: float = 0.0
    range_pct: float = 0.0
    volatility: str = ""  # "low" / "normal" / "high"

    # SymbolFilter
    symbol_tier: str = ""
    win_rate: float = 0.0
    sample_size: int = 0
    avg_win: float = 0.0
    avg_loss: float = 0.0

    # ATR校验
    atr_stop_distance: float = 0.0
    v530_stop_distance: float = 0.0
    stop_status: str = ""

    # 评分
    score: float = 0.0
    rating: str = ""  # "A" / "B" / "C" / "D"
    rating_label: str = ""
    risk_reward: float = 0.0

    # 仓位建议
    position_suggestion: str = ""  # "15%" / "10%" / "5%" / "不做"

    # 最终建议
    final_suggestion: str = ""  # "强做多" / "可做多" / "观察" / "可做空" / "强做空" / "不做"
    reasons: list[str] = field(default_factory=list)

    # 元信息
    created_at: str = ""
    status: str = "pending"  # "pending" / "adopted" / "rejected" / "expired"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def to_markdown(self) -> str:
        """生成可读的Markdown格式建议卡。"""
        lines = []

        # 标题
        emoji = {"A": "🔥", "B": "✅", "C": "👀", "D": "⛔"}.get(self.rating, "")
        lines.append(f"## {emoji} {self.symbol} {self.direction} [{self.rating}] {self.rating_label}")
        lines.append("")

        # 基本信息
        lines.append(f"**当前价:** {self.current_price:,.1f}")
        lines.append("")

        # v530预测
        lines.append("### v530预测")
        lines.append(f"- 预测高点: {self.pred_high:,.1f} (上涨空间: {self.upside_pct:+.1f}%)")
        lines.append(f"- 预测低点: {self.pred_low:,.1f} (下跌风险: {self.downside_pct:+.1f}%)")
        lines.append(f"- 波动范围: {self.range_pct:.1f}% ({self.volatility})")
        lines.append("")

        # 方向过滤
        lines.append("### 方向过滤")
        lines.append(f"- 层级: {self.symbol_tier}")
        lines.append(f"- 历史胜率: {self.win_rate:.1f}%")
        lines.append(f"- 样本数: {self.sample_size}")
        lines.append(f"- 平均盈利: {self.avg_win:+.1f}% / 平均亏损: {self.avg_loss:+.1f}%")
        lines.append("")

        # 止损校验
        lines.append("### 止损校验")
        lines.append(f"- v530止损距离: {self.v530_stop_distance:.1f}%")
        lines.append(f"- ATR止损距离: {self.atr_stop_distance:.1f}%")
        lines.append(f"- 判断: {self.stop_status}")
        lines.append("")

        # 风险收益
        lines.append("### 风险收益")
        lines.append(f"- 止盈空间: {self.upside_pct:.1f}%")
        lines.append(f"- 止损空间: {self.downside_pct:.1f}%")
        lines.append(f"- 风险收益比: {self.risk_reward:.2f}")
        lines.append(f"- 交易评分: {self.score:.0f}/100")
        lines.append("")

        # 仓位建议
        lines.append("### 仓位建议")
        lines.append(f"- 建议仓位: {self.position_suggestion}")
        lines.append("")

        # 最终建议
        lines.append(f"### 💡 最终建议: {self.final_suggestion}")
        for r in self.reasons:
            lines.append(f"- {r}")
        lines.append("")

        return "\n".join(lines)


def build_trade_card(
    symbol: str,
    direction: str,
    current_price: float,
    pred_high: float,
    pred_low: float,
    range_pct: float,
    volatility: str,
    tier: str,
    win_rate: float,
    sample_size: int,
    avg_win: float = 0.0,
    avg_loss: float = 0.0,
    atr_stop_distance: float = 0.0,
    v530_stop_distance: float = 0.0,
    stop_status: str = "",
    score: float = 0.0,
    rating: str = "D",
    rating_label: str = "不做",
    reasons: list[str] | None = None,
) -> TradeCard:
    """构建交易建议卡。"""
    if direction == "BUY":
        upside_pct = (pred_high - current_price) / current_price * 100 if current_price > 0 else 0
        downside_pct = (current_price - pred_low) / current_price * 100 if current_price > 0 else 0
    elif direction == "SELL":
        upside_pct = (current_price - pred_low) / current_price * 100 if current_price > 0 else 0
        downside_pct = (pred_high - current_price) / current_price * 100 if current_price > 0 else 0
    else:
        upside_pct = 0
        downside_pct = 0

    risk_reward = upside_pct / downside_pct if downside_pct > 0 else 0

    # 仓位建议
    if rating == "A":
        position = "15%保证金"
    elif rating == "B":
        position = "10%保证金"
    elif rating == "C":
        position = "5%保证金"
    else:
        position = "不做"

    # 最终建议
    if direction == "BUY":
        if rating in ("A", "B"):
            suggestion = "可做多"
        elif rating == "C":
            suggestion = "观察"
        else:
            suggestion = "不做"
    elif direction == "SELL":
        if rating in ("A", "B"):
            suggestion = "可做空"
        elif rating == "C":
            suggestion = "观察"
        else:
            suggestion = "不做"
    else:
        suggestion = "不做"

    card_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{symbol}"

    return TradeCard(
        id=card_id,
        symbol=symbol,
        direction=direction,
        current_price=current_price,
        pred_high=pred_high,
        pred_low=pred_low,
        upside_pct=round(upside_pct, 2),
        downside_pct=round(downside_pct, 2),
        range_pct=round(range_pct, 2),
        volatility=volatility,
        symbol_tier=tier,
        win_rate=win_rate,
        sample_size=sample_size,
        avg_win=avg_win,
        avg_loss=avg_loss,
        atr_stop_distance=atr_stop_distance,
        v530_stop_distance=v530_stop_distance,
        stop_status=stop_status,
        score=score,
        rating=rating,
        rating_label=rating_label,
        risk_reward=round(risk_reward, 2),
        position_suggestion=position,
        final_suggestion=suggestion,
        reasons=reasons or [],
        created_at=datetime.now().isoformat(),
    )


def save_cards(cards: list[TradeCard], path: Path) -> None:
    """保存交易建议卡到JSON文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [c.to_dict() for c in cards]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_cards(path: Path) -> list[TradeCard]:
    """从JSON文件加载交易建议卡。"""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [TradeCard(**d) for d in data]
    except Exception:
        return []
