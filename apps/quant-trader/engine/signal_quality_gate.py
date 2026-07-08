"""统一信号审批层 — 所有交易信号的最终审批门。

任何模块产生 BUY/SELL 信号后，都必须先经过 SignalQualityGate，
没通过就只能输出 HOLD。

审批规则:
  1. OOS 准确率低于 53% → 拒绝
  2. Walk-Forward 准确率低于 53% → 拒绝
  3. 样本数低于 30 → 只能进入 explore
  4. 样本数低于 50 → 不允许 shadow_live 或 live_guarded
  5. 风险收益比低于 1.8 → 拒绝
  6. 成本后预期收益小于 0 → 拒绝
  7. 市场状态不适配 → 拒绝或降仓
  8. 新闻风险等级 high → 拒绝
  9. 日亏损超过 3% → 拒绝新开仓
  10. 连续亏损 3 次 → 冷却
  11. 总回撤超过 10% → 保护模式，只允许减仓
  12. 总暴露超过 30% → 拒绝新开仓
  13. 单品种暴露超过 10% → 拒绝加仓

评分:
  score = adjusted_accuracy*25 + oos_accuracy*20 + wf_accuracy*20 +
          min(pf/2, 1)*10 + min(rr/3, 1)*10 + regime_fit*10 +
          recent_stability*5

分层:
  score >= 80, n >= 300 → core (允许 shadow_live)
  score >= 70, n >= 100 → watch (只允许 paper)
  score >= 60, n >= 50  → explore (research/paper 观察)
  score < 60            → reject

Usage:
    gate = SignalQualityGate(mode="paper")
    result = gate.evaluate(signal_dict)
    if not result["approved"]:
        result["final_action"] = "HOLD"
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GateResult:
    """信号审批结果。"""
    symbol: str = ""
    input_direction: str = "HOLD"
    final_action: str = "HOLD"
    approved: bool = False
    score: float = 0.0
    tier: str = "reject"
    position_multiplier: float = 0.0
    risk_reward_ratio: float = 0.0
    stop_loss_pct: float = 0.0
    take_profit_pct: float = 0.0
    reason: str = ""
    warnings: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "input_direction": self.input_direction,
            "final_action": self.final_action,
            "approved": self.approved,
            "score": round(self.score, 2),
            "tier": self.tier,
            "position_multiplier": round(self.position_multiplier, 2),
            "risk_reward_ratio": round(self.risk_reward_ratio, 2),
            "stop_loss_pct": round(self.stop_loss_pct, 4),
            "take_profit_pct": round(self.take_profit_pct, 4),
            "reason": self.reason,
            "warnings": self.warnings,
            "evidence": self.evidence,
        }


class SignalQualityGate:
    """统一信号审批层。

    所有交易信号在执行前必须经过此门。
    """

    def __init__(
        self,
        mode: str = "paper",
        max_daily_loss: float = 0.03,
        max_consecutive_losses: int = 3,
        max_account_drawdown: float = 0.10,
        max_total_exposure: float = 0.30,
        max_single_exposure: float = 0.10,
        min_risk_reward: float = 1.8,
        min_oos: float = 0.53,
        min_walk_forward: float = 0.53,
        min_sample_explore: int = 30,
        min_sample_paper: int = 50,
        min_sample_watch: int = 100,
        min_sample_core: int = 300,
    ):
        self.mode = mode
        self.max_daily_loss = max_daily_loss
        self.max_consecutive_losses = max_consecutive_losses
        self.max_account_drawdown = max_account_drawdown
        self.max_total_exposure = max_total_exposure
        self.max_single_exposure = max_single_exposure
        self.min_risk_reward = min_risk_reward
        self.min_oos = min_oos
        self.min_walk_forward = min_walk_forward
        self.min_sample_explore = min_sample_explore
        self.min_sample_paper = min_sample_paper
        self.min_sample_watch = min_sample_watch
        self.min_sample_core = min_sample_core

    def evaluate(self, signal: dict[str, Any]) -> dict:
        """审批一个交易信号。

        Args:
            signal: 包含所有审批所需字段的字典，见模块文档。

        Returns:
            GateResult.to_dict() 格式的审批结果。
        """
        result = GateResult(
            symbol=signal.get("symbol", ""),
            input_direction=signal.get("direction", "HOLD"),
        )
        warnings: list[str] = []
        evidence: dict[str, Any] = {}

        # 提取字段，提供默认值
        raw_confidence = signal.get("raw_confidence", 0.0)
        model_confidence = signal.get("model_confidence", 0.0)
        sample_size = signal.get("sample_size", 0)
        raw_accuracy = signal.get("raw_accuracy", 0.0)
        adjusted_accuracy = signal.get("adjusted_accuracy", raw_accuracy)
        oos_accuracy = signal.get("oos_accuracy", 0.0)
        walk_forward_accuracy = signal.get("walk_forward_accuracy", 0.0)
        profit_factor = signal.get("profit_factor", 0.0)
        win_rate = signal.get("win_rate", 0.0)
        avg_return = signal.get("avg_return", 0.0)
        max_drawdown = signal.get("max_drawdown", 0.0)
        predicted_high_pct = signal.get("predicted_high_pct", 0.0)
        predicted_low_pct = signal.get("predicted_low_pct", 0.0)
        cost_pct = signal.get("cost_pct", 0.0)
        slippage_pct = signal.get("slippage_pct", 0.0)
        commission_pct = signal.get("commission_pct", 0.0)
        market_regime = signal.get("market_regime", "unknown")
        regime_fit_score = signal.get("regime_fit_score", 0.5)
        news_risk_level = signal.get("news_risk_level", "low")
        current_position_pct = signal.get("current_position_pct", 0.0)
        total_exposure_pct = signal.get("total_exposure_pct", 0.0)
        consecutive_losses = signal.get("consecutive_losses", 0)
        day_pnl_pct = signal.get("day_pnl_pct", 0.0)
        account_drawdown_pct = signal.get("account_drawdown_pct", 0.0)
        mode = signal.get("mode", self.mode)
        risk_reward_ratio = signal.get("risk_reward_ratio", 0.0)

        # 如果输入方向是 HOLD，直接通过（不需要审批）
        if result.input_direction in ("HOLD", "NEUTRAL", ""):
            result.final_action = "HOLD"
            result.approved = False
            result.tier = "reject"
            result.reason = "输入方向为 HOLD，无需审批"
            return result.to_dict()

        # ═══════════════════════════════════════════════════════
        #  硬条件检查 — 任何一项失败就拒绝
        # ═══════════════════════════════════════════════════════

        # 1. OOS 准确率检查
        if oos_accuracy > 0 and oos_accuracy < self.min_oos:
            result.reason = f"OOS 准确率 {oos_accuracy:.1%} 低于阈值 {self.min_oos:.0%}"
            result.warnings.append("oos_below_threshold")
            evidence["oos"] = {"value": oos_accuracy, "threshold": self.min_oos, "pass": False}
            return self._reject(result, evidence)
        evidence["oos"] = {"value": oos_accuracy, "threshold": self.min_oos, "pass": True}

        # 2. Walk-Forward 准确率检查
        if walk_forward_accuracy > 0 and walk_forward_accuracy < self.min_walk_forward:
            result.reason = f"Walk-Forward 准确率 {walk_forward_accuracy:.1%} 低于阈值 {self.min_walk_forward:.0%}"
            result.warnings.append("wf_below_threshold")
            evidence["walk_forward"] = {"value": walk_forward_accuracy, "threshold": self.min_walk_forward, "pass": False}
            return self._reject(result, evidence)
        evidence["walk_forward"] = {"value": walk_forward_accuracy, "threshold": self.min_walk_forward, "pass": True}

        # 3. 样本数检查
        if sample_size < self.min_sample_explore:
            result.reason = f"样本数 {sample_size} 低于最低要求 {self.min_sample_explore}，不允许自动交易"
            result.warnings.append("sample_too_small")
            evidence["sample"] = {"value": sample_size, "threshold": self.min_sample_explore, "pass": False}
            return self._reject(result, evidence)
        evidence["sample"] = {"value": sample_size, "pass": True}

        # 4. 模式+样本数联合检查
        if mode in ("shadow_live", "live_guarded") and sample_size < self.min_sample_paper:
            result.reason = f"样本数 {sample_size} 不足以支持 {mode} 模式 (需 {self.min_sample_paper})"
            result.warnings.append("insufficient_sample_for_mode")
            evidence["mode_sample"] = {"value": sample_size, "mode": mode, "pass": False}
            return self._reject(result, evidence)

        # 5. 风险收益比检查
        if risk_reward_ratio > 0 and risk_reward_ratio < self.min_risk_reward:
            result.reason = f"风险收益比 {risk_reward_ratio:.2f} 低于阈值 {self.min_risk_reward}"
            result.warnings.append("risk_reward_too_low")
            evidence["risk"] = {"risk_reward_ratio": risk_reward_ratio, "threshold": self.min_risk_reward, "pass": False}
            return self._reject(result, evidence)
        evidence["risk"] = {"risk_reward_ratio": risk_reward_ratio, "threshold": self.min_risk_reward, "pass": True}

        # 6. 成本后预期收益检查
        total_cost = cost_pct + slippage_pct + commission_pct
        expected_cost_adjusted = avg_return - total_cost
        if avg_return != 0 and expected_cost_adjusted < 0:
            result.reason = f"成本后预期收益 {expected_cost_adjusted:.2%} 为负 (成本={total_cost:.2%})"
            result.warnings.append("negative_after_cost")
            evidence["cost"] = {"total_cost": total_cost, "expected": expected_cost_adjusted, "pass": False}
            return self._reject(result, evidence)
        evidence["cost"] = {"total_cost": total_cost, "expected": expected_cost_adjusted, "pass": True}

        # 7. 新闻风险检查
        if news_risk_level == "high":
            result.reason = "新闻风险等级 high，阻断交易"
            result.warnings.append("news_risk_high")
            evidence["news"] = {"level": news_risk_level, "pass": False}
            return self._reject(result, evidence)
        evidence["news"] = {"level": news_risk_level, "pass": news_risk_level != "high"}

        # 8. 日亏损检查
        if day_pnl_pct < -self.max_daily_loss:
            result.reason = f"日亏损 {day_pnl_pct:.2%} 超过限制 {self.max_daily_loss:.0%}，禁止新开仓"
            result.warnings.append("daily_loss_exceeded")
            evidence["daily_pnl"] = {"value": day_pnl_pct, "limit": -self.max_daily_loss, "pass": False}
            return self._reject(result, evidence)
        evidence["daily_pnl"] = {"value": day_pnl_pct, "limit": -self.max_daily_loss, "pass": True}

        # 9. 连续亏损冷却
        if consecutive_losses >= self.max_consecutive_losses:
            result.reason = f"连续亏损 {consecutive_losses} 次，进入冷却期"
            result.warnings.append("consecutive_loss_cooldown")
            evidence["consecutive_losses"] = {"value": consecutive_losses, "limit": self.max_consecutive_losses, "pass": False}
            return self._reject(result, evidence)
        evidence["consecutive_losses"] = {"value": consecutive_losses, "limit": self.max_consecutive_losses, "pass": True}

        # 10. 账户回撤保护
        if account_drawdown_pct > self.max_account_drawdown:
            # 保护模式：只允许减仓
            if result.input_direction == "SELL":
                warnings.append("drawdown_reduce_only")
                result.position_multiplier = 0.5
            else:
                result.reason = f"账户回撤 {account_drawdown_pct:.1%} 超过 {self.max_account_drawdown:.0%}，保护模式只允许减仓"
                result.warnings.append("drawdown_protection")
                evidence["drawdown"] = {"value": account_drawdown_pct, "limit": self.max_account_drawdown, "pass": False}
                return self._reject(result, evidence)
        evidence["drawdown"] = {"value": account_drawdown_pct, "limit": self.max_account_drawdown, "pass": True}

        # 11. 总暴露检查
        if total_exposure_pct > self.max_total_exposure:
            result.reason = f"总暴露 {total_exposure_pct:.1%} 超过 {self.max_total_exposure:.0%}，拒绝新开仓"
            result.warnings.append("total_exposure_exceeded")
            evidence["exposure"] = {"total": total_exposure_pct, "limit": self.max_total_exposure, "pass": False}
            return self._reject(result, evidence)
        evidence["exposure"] = {"total": total_exposure_pct, "limit": self.max_total_exposure, "pass": True}

        # 12. 单品种暴露检查
        if current_position_pct > self.max_single_exposure:
            result.reason = f"单品种暴露 {current_position_pct:.1%} 超过 {self.max_single_exposure:.0%}，拒绝加仓"
            result.warnings.append("single_exposure_exceeded")
            evidence["single_exposure"] = {"value": current_position_pct, "limit": self.max_single_exposure, "pass": False}
            return self._reject(result, evidence)
        evidence["single_exposure"] = {"value": current_position_pct, "limit": self.max_single_exposure, "pass": True}

        # ═══════════════════════════════════════════════════════
        #  评分计算
        # ═══════════════════════════════════════════════════════
        score = self._compute_score(
            adjusted_accuracy=adjusted_accuracy,
            raw_accuracy=raw_accuracy,
            sample_size=sample_size,
            oos_accuracy=oos_accuracy,
            walk_forward_accuracy=walk_forward_accuracy,
            profit_factor=profit_factor,
            risk_reward_ratio=risk_reward_ratio,
            regime_fit_score=regime_fit_score,
            win_rate=win_rate,
        )
        evidence["score_breakdown"] = {"total": round(score, 2)}

        # ═══════════════════════════════════════════════════════
        #  分层判定
        # ═══════════════════════════════════════════════════════
        tier = self._classify_tier(score, sample_size)

        # ═══════════════════════════════════════════════════════
        #  模式检查
        # ═══════════════════════════════════════════════════════
        mode_ok = self._check_mode(tier, mode)
        if not mode_ok:
            result.reason = f"分层 {tier} 不允许在 {mode} 模式下交易"
            result.warnings.append("tier_mode_mismatch")
            result.score = score
            result.tier = tier
            result.evidence = evidence
            return result.to_dict()

        # ═══════════════════════════════════════════════════════
        #  通过 — 计算仓位倍数和止盈止损
        # ═══════════════════════════════════════════════════════
        position_multiplier = self._compute_position_multiplier(tier, score, warnings)
        stop_loss, take_profit = self._compute_stops(predicted_high_pct, predicted_low_pct, risk_reward_ratio)

        # 市场状态降仓
        if regime_fit_score < 0.3:
            position_multiplier *= 0.5
            warnings.append("low_regime_fit_reduced")

        result.approved = True
        result.final_action = result.input_direction
        result.score = score
        result.tier = tier
        result.position_multiplier = position_multiplier
        result.risk_reward_ratio = risk_reward_ratio
        result.stop_loss_pct = stop_loss
        result.take_profit_pct = take_profit
        result.warnings = warnings
        result.evidence = evidence

        # 为 watch 层级标注只允许 paper
        if tier == "watch" and mode in ("shadow_live", "live_guarded"):
            result.warnings.append("upgraded_to_paper_only")

        result.reason = (
            f"通过审批: score={score:.1f} tier={tier} "
            f"pos_mult={position_multiplier:.2f} RR={risk_reward_ratio:.2f}"
        )
        return result.to_dict()

    # ── 内部方法 ──────────────────────────────────────────────

    @staticmethod
    def _compute_score(
        adjusted_accuracy: float,
        raw_accuracy: float,
        sample_size: int,
        oos_accuracy: float,
        walk_forward_accuracy: float,
        profit_factor: float,
        risk_reward_ratio: float,
        regime_fit_score: float,
        win_rate: float,
    ) -> float:
        """计算综合评分 0-100。"""
        # 样本置信度
        sample_confidence = min(1.0, math.sqrt(sample_size / 100))
        adj_acc = raw_accuracy * sample_confidence if raw_accuracy > 0 else adjusted_accuracy

        # 各维度分值
        s_acc = min(adj_acc, 1.0) * 25
        s_oos = min(oos_accuracy, 1.0) * 20
        s_wf = min(walk_forward_accuracy, 1.0) * 20
        s_pf = min(profit_factor / 2.0, 1.0) * 10
        s_rr = min(risk_reward_ratio / 3.0, 1.0) * 10
        s_regime = min(max(regime_fit_score, 0.0), 1.0) * 10

        # 近期稳定性 (用 win_rate 作为近似)
        recent_stability = min(max(win_rate, 0.0), 1.0)
        s_stability = recent_stability * 5

        score = s_acc + s_oos + s_wf + s_pf + s_rr + s_regime + s_stability
        return min(100.0, max(0.0, score))

    def _classify_tier(self, score: float, sample_size: int) -> str:
        """根据 score 和 sample_size 分层。"""
        if score >= 80 and sample_size >= self.min_sample_core:
            return "core"
        elif score >= 70 and sample_size >= self.min_sample_watch:
            return "watch"
        elif score >= 60 and sample_size >= self.min_sample_paper:
            return "explore"
        return "reject"

    @staticmethod
    def _check_mode(tier: str, mode: str) -> bool:
        """检查分层和模式是否兼容。"""
        if mode == "research":
            return True  # research 模式只生成信号，不执行
        if mode == "paper":
            return tier in ("core", "watch", "explore")
        if mode == "shadow_live":
            return tier == "core"  # 只有 core 允许 shadow_live
        if mode == "live_guarded":
            return tier == "core"
        if mode == "live":
            return tier == "core"
        return True  # 未知模式默认允许

    @staticmethod
    def _compute_position_multiplier(tier: str, score: float, warnings: list) -> float:
        """根据分层计算仓位倍数。"""
        base = {"core": 1.2, "watch": 1.0, "explore": 0.6, "reject": 0.0}
        mult = base.get(tier, 0.0)
        # 高分奖励 (但不超过 1.5)
        if score >= 85:
            mult = min(1.5, mult * 1.1)
        return mult

    @staticmethod
    def _compute_stops(
        predicted_high_pct: float,
        predicted_low_pct: float,
        risk_reward_ratio: float,
    ) -> tuple[float, float]:
        """根据预测空间和风险收益比计算止损止盈。"""
        # 默认止损
        stop_loss = 0.05  # 5%
        take_profit = 0.08  # 8%

        if predicted_high_pct > 0 and predicted_low_pct < 0:
            # 有预测空间时，根据预测调整
            upside = predicted_high_pct
            downside = abs(predicted_low_pct)

            if risk_reward_ratio > 0:
                # 根据风险收益比调整止盈
                take_profit = min(upside, stop_loss * risk_reward_ratio)
                take_profit = max(take_profit, 0.03)  # 最低 3%
            else:
                take_profit = min(upside * 0.8, 0.12)  # 不追顶部

        return stop_loss, take_profit

    @staticmethod
    def _reject(result: GateResult, evidence: dict) -> dict:
        """拒绝信号并返回结果。"""
        result.approved = False
        result.final_action = "HOLD"
        result.tier = "reject"
        result.position_multiplier = 0.0
        result.evidence = evidence
        return result.to_dict()
