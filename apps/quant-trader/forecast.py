"""统一预测报告引擎 — 股票+期货 双轨预测 同格式 同顺序。

生成一份干净的预测报告:
  期货: ①时钟→②合约→③行情→④技术分析→⑤LLM→⑥风控→⑦建议

特性:
  - 每次运行拉取最新行情，不缓存
  - 完整日志系统 (logs/forecast_*.log)
  - 输出: JSON / 文本 / HTML 网页报告
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 自动加载 .env 文件 (如果存在)
_env_file = Path(__file__).resolve().parent.parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                v = v[1:-1]
            os.environ.setdefault(k.strip(), v)

import numpy as np
import pandas as pd

# ══════════════════════════════════════════════════════════════════
# 日志系统
# ══════════════════════════════════════════════════════════════════

_LOG_DIR = Path(os.environ.get("QT_LOG_DIR", "logs"))
_LOG_DIR.mkdir(parents=True, exist_ok=True)

_forecast_logger = logging.getLogger("quanttrader.forecast")
_forecast_logger.setLevel(logging.DEBUG)

# 文件处理器 — 按日期切割
_today = dt.date.today().strftime("%Y%m%d")
_fh = logging.FileHandler(_LOG_DIR / f"forecast_{_today}.log", encoding="utf-8")
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
_forecast_logger.addHandler(_fh)

# 控制台
_ch = logging.StreamHandler()
_ch.setLevel(logging.INFO)
_ch.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%H:%M:%S"))
_forecast_logger.addHandler(_ch)

log = _forecast_logger

# 清理旧日志 (>30天)
try:
    for f in _LOG_DIR.glob("forecast_*.log"):
        if (dt.datetime.now() - dt.datetime.fromtimestamp(f.stat().st_mtime)).days > 30:
            f.unlink(missing_ok=True)
except Exception:
    pass


def _archive_report(report: dict[str, Any]) -> None:
    """归档预测报告为 JSON。"""
    try:
        archive_dir = _LOG_DIR / "reports"
        archive_dir.mkdir(parents=True, exist_ok=True)
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        (archive_dir / f"forecast_{ts}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # 保留最近 50 份
        files = sorted(archive_dir.glob("forecast_*.json"))
        for old in files[:-50]:
            old.unlink(missing_ok=True)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════
# 统一预测结果
# ══════════════════════════════════════════════════════════════════


@dataclass
class ForecastStep:
    """单步预测中间结果。"""

    name: str  # 步骤名
    icon: str  # emoji
    status: str  # "ok" | "skip" | "error"
    data: dict[str, Any] = field(default_factory=dict)
    text: str = ""


@dataclass
class ForecastResult:
    """单标的预测报告。"""

    symbol: str
    name: str
    market: str  # "stock" | "future"
    timestamp: str
    steps: list[ForecastStep] = field(default_factory=list)
    signal: str = ""  # "BUY" / "SELL" / "HOLD" / "LONG" / "SHORT" / "NEUTRAL"
    confidence: float = 0.0
    reason: str = ""
    risk_level: str = "normal"
    suggestion: str = ""
    error: str = ""
    # 高低点预测
    forecast_price: float = 0.0  # LLM预测目标价
    high_point: float = 0.0  # 预测高点 (阻力位)
    low_point: float = 0.0  # 预测低点 (支撑位)
    stop_loss: float = 0.0  # 止损位
    take_profit: float = 0.0  # 止盈位
    # 时间轴计划 (新增)
    entry_zone: tuple[float, float] = (0.0, 0.0)  # 入场区间
    target_1: float = 0.0  # 第一目标
    target_2: float = 0.0  # 第二目标
    risk_reward: float = 0.0  # 风险收益比
    hold_days: int = 0  # 建议持有天数
    milestones: list[dict] = field(default_factory=list)  # 里程碑

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "market": self.market,
            "timestamp": self.timestamp,
            "steps": [
                {"name": s.name, "icon": s.icon, "status": s.status, "data": s.data, "text": s.text} for s in self.steps
            ],
            "signal": self.signal,
            "confidence": self.confidence,
            "reason": self.reason,
            "risk_level": self.risk_level,
            "suggestion": self.suggestion,
            "error": self.error,
            "forecast_price": self.forecast_price,
            "high_point": self.high_point,
            "low_point": self.low_point,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "entry_zone": list(self.entry_zone),
            "target_1": self.target_1,
            "target_2": self.target_2,
            "risk_reward": self.risk_reward,
            "hold_days": self.hold_days,
            "milestones": self.milestones,
        }

    def to_text(self) -> str:
        lines = [
            "╔══════════════════════════════════════════════╗",
            f"║  {self.name} ({self.symbol}) — {self.market}       ║",
            "╠══════════════════════════════════════════════╣",
        ]
        for s in self.steps:
            status_icon = {"ok": "✅", "skip": "⏭️", "error": "❌"}.get(s.status, "❓")
            lines.append(f"║  {status_icon} {s.icon} {s.name:<20s} {s.text[:22]:<22s} ║")

        if self.signal:
            sig_icon = {"BUY": "🟢", "LONG": "📈", "SELL": "🔴", "SHORT": "📉", "HOLD": "⏸️", "NEUTRAL": "⚖️"}.get(
                self.signal, "❓"
            )
            lines.append("╠══════════════════════════════════════════════╣")
            lines.append(f"║  {sig_icon} 信号: {self.signal:<6s} 置信度: {self.confidence:.0%}                   ║")
            lines.append(f"║  理由: {self.reason[:36]:<36s} ║")
        if self.suggestion:
            lines.append(f"║  📝 {self.suggestion[:36]:<36s} ║")
        lines.append("╚══════════════════════════════════════════════╝")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
# 统一预测流程
# ══════════════════════════════════════════════════════════════════


def _load_synthetic(
    symbol: str,
    days: int = 120,
    start_price: float = 100.0,
    trend: float = 0.02,
    vol: float = 0.18,
    recent_drift: float = 0.0,
    _rng=None,
):
    """模拟未来走势的数据生成器 — 每次都生成新数据，不缓存。

    用今天的日期做种子微调，确保每天的数据略有不同。
    """
    if _rng is None:
        today_seed = int(dt.date.today().strftime("%Y%m%d"))
        _rng = np.random.RandomState((hash(symbol) + today_seed) % 2**31)
    dt_val = 1.0 / 252.0
    shocks = _rng.randn(days)
    shocks[-5:] += recent_drift * 0.5 / max(vol, 0.01)
    daily = (trend - 0.5 * vol**2) * dt_val + vol * np.sqrt(dt_val) * shocks
    closes = start_price * np.exp(np.cumsum(daily))
    opens = np.concatenate([[start_price], closes[:-1]])
    highs = np.maximum(opens, closes) * (1 + np.abs(_rng.randn(days)) * 0.008)
    lows = np.minimum(opens, closes) * (1 - np.abs(_rng.randn(days)) * 0.008)
    volumes = _rng.randint(500000, 3000000, size=days)

    dates = pd.bdate_range(end=dt.date.today(), periods=days)
    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        },
        index=dates,
    )


def _run_future_forecast(code: str, llm_api_key: str = "", llm_provider: str = "deepseek") -> ForecastResult:
    """运��期货预测全流程。"""
    steps: list[ForecastStep] = []
    signal = "NEUTRAL"
    confidence = 0.0
    reason = ""
    risk_level = "normal"
    suggestion = ""

    try:
        from quanttrader.futures.contracts import (
            contract_info,
            dominant_contract,
            is_trading_now,
            next_expiry,
            session_label,
        )

        spec = contract_info(code)
        if not spec:
            return ForecastResult(
                symbol=code,
                name=code,
                market="future",
                timestamp=dt.datetime.now().isoformat(timespec="seconds"),
                steps=[],
                error=f"Unknown contract: {code}",
            )

        # ① Clock
        ses = session_label()
        trading = is_trading_now(code)
        dom = dominant_contract(code)
        exp = next_expiry(code)
        steps.append(
            ForecastStep(
                "市场时钟",
                "🕐",
                "ok",
                {
                    "session": ses,
                    "trading": trading,
                    "dominant": dom,
                    "expiry": str(exp),
                },
                f"{ses} {'交易中' if trading else '休市'} 主力{dom}",
            )
        )

        # ② Contract
        margin = spec.calc_margin(3000, 1)
        steps.append(
            ForecastStep(
                "合约筛选",
                "📋",
                "ok",
                {
                    "exchange": spec.exchange,
                    "size": spec.contract_size,
                    "margin_rate": spec.margin_rate,
                    "tick_value": spec.tick_value,
                },
                f"{spec.exchange} {spec.contract_size}吨/手 保证金{spec.margin_rate * 100:.0f}%",
            )
        )

        # ③ Price — 多源数据验证 + 历史数据补全
        prices = None
        verified_price = None

        # 多源数据验证
        try:
            from quanttrader.data.multi_source import MultiSourceValidator

            validator = MultiSourceValidator()
            verified_price = validator.get_verified_price(code)
            if verified_price:
                log.info(f"  {code}: 多源验证价格 ¥{verified_price:,.0f}")
        except Exception as e:
            log.warning(f"  {code}: 多源验证失败: {e}")

        # 历史数据获取
        try:
            from quanttrader.data.history import HistoryDataFetcher

            fetcher = HistoryDataFetcher()
            prices = fetcher.get_history(code, days=120)
            if prices is not None and len(prices) > 0:
                log.info(f"  {code}: 使用真实历史数据 ({len(prices)}天)")
        except Exception as e:
            log.warning(f"  {code}: 历史数据获取失败: {e}")

        # 降级: 新浪实时数据
        if prices is None or len(prices) < 20:
            try:
                from quanttrader.data.sina_futures import get_history

                prices = get_history(code, days=120)
                log.info(f"  {code}: 使用新浪实时数据")
            except Exception as e:
                log.warning(f"  {code}: 新浪数据获取失败: {e}")

        # 最终降级: 合成数据
        if prices is None or len(prices) < 20:
            prices = _load_synthetic(
                code, days=120, start_price=float(abs(hash(code)) % 3000 + 2000), trend=0.03, vol=0.20, recent_drift=0.5
            )
            log.warning(f"  {code}: 使用合成数据")

        # 使用验证价格修正
        if (
            verified_price
            and abs(verified_price - float(prices["close"].iloc[-1])) / float(prices["close"].iloc[-1]) > 0.01
        ):
            log.info(f"  {code}: 价格修正 {float(prices['close'].iloc[-1]):,.0f} → {verified_price:,.0f}")
            prices.iloc[-1, prices.columns.get_loc("close")] = verified_price

        price = float(prices["close"].iloc[-1])
        chg = float((price / float(prices["close"].iloc[-2]) - 1) * 100)
        sma20 = float(prices["close"].tail(20).mean())
        steps.append(
            ForecastStep(
                "行情数据",
                "📊",
                "ok",
                {
                    "price": price,
                    "change_pct": chg,
                    "bars": len(prices),
                    "sma20": sma20,
                    "data_source": "verified" if verified_price else "synthetic",
                },
                f"¥{price:.0f} {chg:+.1f}% SMA20:{sma20:.0f}",
            )
        )

        # ④ 技术分析（高低点等，见后续步骤）
        news_text = ""
        hl_result = None
        try:
            from quanttrader.analysis.highlow import find_highlows

            hl_result = find_highlows(prices, symbol=code)
            steps.append(
                ForecastStep(
                    "高低点分析",
                    "📐",
                    "ok",
                    {
                        "nearest_support": hl_result.nearest_support,
                        "nearest_resistance": hl_result.nearest_resistance,
                        "atr": hl_result.atr,
                        "trend": hl_result.trend,
                        "position_pct": hl_result.position_pct,
                    },
                    f"支撑{hl_result.nearest_support:,.0f} 阻力{hl_result.nearest_resistance:,.0f} ATR{hl_result.atr:,.0f}",
                )
            )
        except Exception as e:
            steps.append(ForecastStep("高低点分析", "📐", "skip", {}, str(e)[:40]))

        # ⑤a 高低点预测 (优化)
        hl_prediction = None
        try:
            from quanttrader.analysis.highlow_predictor import HighLowPredictor

            hl_predictor = HighLowPredictor()
            hl_prediction = hl_predictor.predict(prices, symbol=code)
            # 记录到tracker用于验证
            try:
                from quanttrader.tracker import record_hl_prediction
                record_hl_prediction(
                    symbol=code,
                    predicted_high=hl_prediction.predicted_high,
                    predicted_low=hl_prediction.predicted_low,
                    current_price=hl_prediction.current_price,
                    regime=hl_prediction.regime,
                    method_weights=hl_prediction.method_weights,
                )
            except Exception:
                pass
            steps.append(
                ForecastStep(
                    "高低点预测",
                    "🎯",
                    "ok",
                    {
                        "predicted_high": hl_prediction.predicted_high,
                        "predicted_low": hl_prediction.predicted_low,
                        "high_confidence": hl_prediction.high_confidence,
                        "low_confidence": hl_prediction.low_confidence,
                        "method": hl_prediction.method,
                    },
                    f"高点¥{hl_prediction.predicted_high:,.0f} 低点¥{hl_prediction.predicted_low:,.0f}",
                )
            )
        except Exception as e:
            steps.append(ForecastStep("高低点预测", "🎯", "skip", {}, str(e)[:40]))

        # ⑤a+ Edge 方向 setup（渐进精度门控）
        try:
            from quanttrader.edge_journal import edge_summary_for_display

            edge = edge_summary_for_display(prices)
            if edge.get("edge_active"):
                steps.append(
                    ForecastStep(
                        "Edge方向",
                        "🎯",
                        "ok",
                        edge,
                        f"{edge['edge_setup']} {edge['edge_score']:.0f}分 → {edge['edge_direction']}",
                    )
                )
            else:
                steps.append(ForecastStep("Edge方向", "🎯", "skip", {}, "无达标 setup"))
        except Exception as e:
            steps.append(ForecastStep("Edge方向", "🎯", "skip", {}, str(e)[:40]))

        # ⑤b 多周期共振分析
        multi_tf_result = None
        try:
            from quanttrader.analysis.multi_timeframe import MultiTimeframeAnalyzer

            mtf_analyzer = MultiTimeframeAnalyzer()
            multi_tf_result = mtf_analyzer.analyze(prices)
            steps.append(
                ForecastStep(
                    "多周期共振",
                    "🔄",
                    "ok",
                    {
                        "resonance": multi_tf_result.resonance,
                        "direction": multi_tf_result.resonance_direction,
                        "daily_trend": multi_tf_result.daily.trend,
                        "h4_trend": multi_tf_result.h4.trend,
                        "h1_trend": multi_tf_result.h1.trend,
                    },
                    f"{multi_tf_result.resonance}共振 {multi_tf_result.resonance_direction}",
                )
            )
        except Exception as e:
            steps.append(ForecastStep("多周期共振", "🔄", "skip", {}, str(e)[:40]))

        # ⑤c 量价背离检测
        divergence_result = None
        try:
            from quanttrader.analysis.divergence import DivergenceDetector

            div_detector = DivergenceDetector()
            divergence_result = div_detector.detect(prices)
            if divergence_result.divergence_type != "none":
                steps.append(
                    ForecastStep(
                        "量价背离",
                        "⚠️",
                        "ok",
                        {
                            "type": divergence_result.divergence_type,
                            "strength": divergence_result.strength,
                            "signal": divergence_result.signal,
                        },
                        divergence_result.description,
                    )
                )
        except Exception as e:
            steps.append(ForecastStep("量价背离", "⚠️", "skip", {}, str(e)[:40]))

        # ⑤d 资金流向分析
        money_flow_result = None
        try:
            from quanttrader.analysis.money_flow import MoneyFlowAnalyzer

            mf_analyzer = MoneyFlowAnalyzer()
            money_flow_result = mf_analyzer.analyze(prices)
            if money_flow_result.flow_direction != "neutral":
                steps.append(
                    ForecastStep(
                        "资金流向",
                        "💰",
                        "ok",
                        {
                            "direction": money_flow_result.flow_direction,
                            "strength": money_flow_result.flow_strength,
                            "volume_trend": money_flow_result.volume_trend,
                        },
                        money_flow_result.description,
                    )
                )
        except Exception as e:
            steps.append(ForecastStep("资金流向", "💰", "skip", {}, str(e)[:40]))

        # ⑤e 历史案例匹配
        pattern_result = None
        try:
            from quanttrader.analysis.pattern_match import PatternMatcher

            pattern_matcher = PatternMatcher()
            pattern_result = pattern_matcher.find_similar(prices, symbol=code)
            if pattern_result.similar_cases:
                steps.append(
                    ForecastStep(
                        "历史匹配",
                        "📚",
                        "ok",
                        {
                            "similar_count": len(pattern_result.similar_cases),
                            "avg_return": pattern_result.avg_return,
                            "win_rate": pattern_result.win_rate,
                            "direction": pattern_result.predicted_direction,
                        },
                        f"找到{len(pattern_result.similar_cases)}个相似案例，胜率{pattern_result.win_rate * 100:.0f}%",
                    )
                )
        except Exception as e:
            steps.append(ForecastStep("历史匹配", "📚", "skip", {}, str(e)[:40]))

        # ⑥ LLM (集成高低点分析)
        target_price = price
        stop_loss = 0.0
        take_profit = 0.0
        if llm_api_key:
            try:
                from quanttrader.ai.llm import LLMConfig
                from quanttrader.futures.strategy import futures_llm_decision

                cfg = LLMConfig(provider=llm_provider, api_key=llm_api_key)
                cfg.resolve()

                # 将高低点分析注入 extra_ctx
                hl_ctx = ""
                if hl_result:
                    hl_ctx = (
                        f"\n📐 高低点分析:\n"
                        f"最近支撑: ¥{hl_result.nearest_support:,.0f}\n"
                        f"最近阻力: ¥{hl_result.nearest_resistance:,.0f}\n"
                        f"ATR(14): ¥{hl_result.atr:,.0f}\n"
                        f"趋势: {hl_result.trend}\n"
                        f"位置: {hl_result.position_pct:.0f}% (0=支撑, 100=阻力)\n"
                        f"支撑位: {', '.join(f'¥{l.price:,.0f}' for l in hl_result.supports()[:3])}\n"
                        f"阻力位: {', '.join(f'¥{l.price:,.0f}' for l in hl_result.resistances()[:3])}"
                    )
                full_ctx = hl_ctx

                dec = futures_llm_decision(prices, code, cfg, news_text, full_ctx)
                sig_map = {1: "LONG", 0: "NEUTRAL", -1: "SHORT"}
                signal = sig_map.get(int(dec["signal"]), "NEUTRAL")
                confidence = float(dec.get("confidence", 0))
                reason = str(dec.get("reason", ""))[:200]

                # 提取价格目标
                if dec.get("target_price"):
                    target_price = float(dec["target_price"])
                if dec.get("stop_loss"):
                    stop_loss = float(dec["stop_loss"])
                if dec.get("take_profit"):
                    take_profit = float(dec["take_profit"])

                # ═══════════ 置信度校准 ═══════════
                try:
                    from quanttrader.confidence.calibrator import ConfidenceCalibrator

                    calibrator = ConfidenceCalibrator()
                    raw_conf = confidence
                    confidence = calibrator.calibrate(code, signal, confidence)
                    if confidence != raw_conf:
                        log.info(f"  {code}: 置信度校准 {raw_conf:.0%} → {confidence:.0%}")
                except Exception:
                    pass

                # ═══════════ 噪点过滤 ═══════════
                # 规则1: 贵金属 LONG 信号降级 — 新闻误导风险高
                if code in ("AU", "AG") and signal == "LONG":
                    # 降低置信度但不完全归零
                    confidence = confidence * 0.5
                    reason = f"[调整] 贵金属做多风险高，降低置信度。原始理由: {reason}"
                    log.warning(f"  {code}: 贵金属LONG降权50%")

                # 规则2: NEUTRAL 低置信度降级 — 信号太弱
                elif signal == "NEUTRAL" and confidence < 0.3:
                    confidence = 0.0
                    reason = f"[过滤] 观望信号置信度过低({confidence:.0%})，降级。原始理由: {reason}"

                # 规则3: 高置信度(≥75%)需趋势确认 — 趋势末端风险
                elif confidence >= 0.75 and hl_result:
                    if hl_result.position_pct > 80 and signal == "LONG":
                        confidence = 0.65
                        reason = f"[调整] 位置过高({hl_result.position_pct:.0f}%)，降低置信度。原始理由: {reason}"
                    elif hl_result.position_pct < 20 and signal == "SHORT":
                        confidence = 0.65
                        reason = f"[调整] 位置过低({hl_result.position_pct:.0f}%)，降低置信度。原始理由: {reason}"

                # 规则4: 能化板块需 EIA 数据确认
                if code in ("SC", "FU", "MA", "TA", "SA") and signal in ("LONG", "SHORT"):
                    # 检查是否临近 EIA 数据
                    from datetime import datetime

                    now = datetime.now()
                    # 周三 10:30 EIA 数据
                    if now.weekday() == 2 and 9 <= now.hour <= 11:
                        signal = "NEUTRAL"
                        confidence = 0.0
                        reason = f"[过滤] EIA数据前不操作。原始理由: {reason}"
                        log.warning(f"  {code}: EIA数据前降级为NEUTRAL")

                # ═══════════ 多周期共振调整 ═══════════
                if signal in ("LONG", "SHORT") and multi_tf_result:
                    try:
                        from quanttrader.analysis.multi_timeframe import MultiTimeframeAnalyzer

                        mtf_analyzer = MultiTimeframeAnalyzer()
                        _, tf_adjustment, tf_reasons = mtf_analyzer.get_signal_confirmation(signal, multi_tf_result)
                        if tf_adjustment != 0:
                            # 降低调整幅度 (从±20%改为±10%)
                            adjusted_tf = tf_adjustment * 0.5
                            confidence = max(0, min(1, confidence + adjusted_tf))
                            if tf_reasons:
                                reason = f"[多周期] {tf_reasons[0]} | {reason}"
                            log.info(f"  {code}: 多周期调整 {adjusted_tf:+.0%}")
                    except Exception:
                        pass

                # ═══════════ 量价背离调整 ═══════════
                if signal in ("LONG", "SHORT") and divergence_result:
                    try:
                        from quanttrader.analysis.divergence import DivergenceDetector

                        div_detector = DivergenceDetector()
                        div_adjustment, div_reasons = div_detector.get_signal_adjustment(divergence_result)
                        if div_adjustment != 0:
                            # 降低调整幅度 (从±15%改为±8%)
                            adjusted_div = div_adjustment * 0.5
                            confidence = max(0, min(1, confidence + adjusted_div))
                            if div_reasons:
                                reason = f"[背离] {div_reasons[0]} | {reason}"
                            log.info(f"  {code}: 背离调整 {adjusted_div:+.0%}")
                    except Exception:
                        pass

                # ═══════════ 资金流向调整 ═══════════
                if signal in ("LONG", "SHORT") and money_flow_result:
                    try:
                        from quanttrader.analysis.money_flow import MoneyFlowAnalyzer

                        mf_analyzer = MoneyFlowAnalyzer()
                        mf_adjustment, mf_reasons = mf_analyzer.get_signal_adjustment(money_flow_result)
                        if mf_adjustment != 0:
                            # 降低调整幅度 (从±15%改为±8%)
                            adjusted_mf = mf_adjustment * 0.5
                            confidence = max(0, min(1, confidence + adjusted_mf))
                            if mf_reasons:
                                reason = f"[资金] {mf_reasons[0]} | {reason}"
                            log.info(f"  {code}: 资金调整 {mf_adjustment:+.0%}")
                    except Exception:
                        pass

                # ═══════════ 历史案例调整 ═══════════
                if signal in ("LONG", "SHORT") and pattern_result:
                    try:
                        from quanttrader.analysis.pattern_match import PatternMatcher

                        pattern_matcher = PatternMatcher()
                        pat_adjustment, pat_reasons = pattern_matcher.get_signal_adjustment(pattern_result)
                        if pat_adjustment != 0:
                            # 降低调整幅度 (从±15%改为±8%)
                            adjusted_pat = pat_adjustment * 0.5
                            confidence = max(0, min(1, confidence + adjusted_pat))
                            if pat_reasons:
                                reason = f"[历史] {pat_reasons[0]} | {reason}"
                            log.info(f"  {code}: 历史调整 {pat_adjustment:+.0%}")
                    except Exception:
                        pass

                steps.append(
                    ForecastStep(
                        "LLM决策",
                        "🧠",
                        "ok",
                        {
                            "provider": dec.get("provider", ""),
                            "model": dec.get("model", ""),
                            "target_price": target_price,
                            "stop_loss": stop_loss,
                            "take_profit": take_profit,
                            "filtered": signal != sig_map.get(int(dec["signal"]), "NEUTRAL"),
                        },
                        f"{signal} conf={confidence:.0%} 目标{target_price:,.0f}",
                    )
                )
            except Exception as e:
                steps.append(ForecastStep("LLM决策", "🧠", "error", {}, str(e)[:40]))
        else:
            steps.append(ForecastStep("LLM决策", "🧠", "skip", {}, "无API密钥"))

        # ⑦ Risk — 动态止损 + 组合风险
        atr_val = hl_result.atr if hl_result and hl_result.atr > 0 else price * 0.02
        margin_used = spec.calc_margin(price, 1)

        # 动态止损计算
        dynamic_stop_price = 0.0
        try:
            from quanttrader.risk.dynamic_stop import DynamicStopLoss

            stop_calculator = DynamicStopLoss()
            stop_result = stop_calculator.calculate(
                entry_price=price,
                signal=signal,
                hl_result=hl_result,
                atr=atr_val,
                position_pct=hl_result.position_pct if hl_result else 50,
            )
            dynamic_stop_price = stop_result.stop_price
            steps.append(
                ForecastStep(
                    "动态止损",
                    "🛑",
                    "ok",
                    {
                        "stop_price": stop_result.stop_price,
                        "stop_type": stop_result.stop_type,
                        "distance": stop_result.distance,
                        "risk_reward": stop_result.risk_reward,
                    },
                    f"¥{stop_result.stop_price:,.0f} ({stop_result.description})",
                )
            )
        except Exception as e:
            dynamic_stop_price = price - 1.5 * atr_val if signal == "LONG" else price + 1.5 * atr_val
            steps.append(ForecastStep("动态止损", "🛑", "skip", {}, str(e)[:40]))

        steps.append(
            ForecastStep(
                "风控预检",
                "🛡️",
                "ok",
                {
                    "margin_per_lot": margin_used,
                    "leverage": 1 / spec.margin_rate if spec.margin_rate > 0 else 1,
                    "atr": atr_val,
                    "dynamic_stop": dynamic_stop_price,
                },
                f"每手保证金¥{margin_used:,.0f} ATR¥{atr_val:,.0f}",
            )
        )

        # ⑧ Suggestion (使用高低点支撑阻力)
        if signal == "LONG":
            if hl_result:
                suggestion = f"做多，入场区间¥{hl_result.nearest_support:,.0f}~¥{price:,.0f}，目标¥{hl_result.nearest_resistance:,.0f}，止损¥{hl_result.nearest_support - atr_val:,.0f}"
            else:
                suggestion = "可以考虑做多，止损设ATR×2，注意夜盘波动"
            risk_level = "normal"
        elif signal == "SHORT":
            if hl_result:
                suggestion = f"做空，入场区间¥{price:,.0f}~¥{hl_result.nearest_resistance:,.0f}，目标¥{hl_result.nearest_support:,.0f}，止损¥{hl_result.nearest_resistance + atr_val:,.0f}"
            else:
                suggestion = "可以考虑做空，止损设ATR×2，注意夜盘波动"
            risk_level = "normal"
        else:
            suggestion = "信号不明确，等待更佳时机"
        steps.append(ForecastStep("综合建议", "📝", "ok", {}, suggestion))

        # ⑨ 时间轴计划 (新增)
        timeline_plan = None
        if signal in ("LONG", "SHORT") and hl_result:
            try:
                from quanttrader.analysis.timeline import build_timeline

                direction = "long" if signal == "LONG" else "short"
                timeline_plan = build_timeline(hl_result, direction=direction, capital=100000)
                if timeline_plan and timeline_plan.milestones:
                    steps.append(
                        ForecastStep(
                            "时间轴计划",
                            "📅",
                            "ok",
                            {
                                "entry_zone": timeline_plan.entry_zone,
                                "target_1": timeline_plan.target_1,
                                "target_2": timeline_plan.target_2,
                                "stop_loss": timeline_plan.stop_loss,
                                "risk_reward": timeline_plan.risk_reward,
                                "hold_days": timeline_plan.hold_days,
                                "predicted_high": timeline_plan.predicted_high,
                                "predicted_low": timeline_plan.predicted_low,
                            },
                            f"高点¥{timeline_plan.predicted_high:,.0f} 低点¥{timeline_plan.predicted_low:,.0f} 持有{timeline_plan.hold_days}天",
                        )
                    )
            except Exception as e:
                steps.append(ForecastStep("时间轴计划", "📅", "skip", {}, str(e)[:40]))

    except Exception as e:
        result = ForecastResult(
            symbol=code,
            name=code,
            market="future",
            timestamp=dt.datetime.now().isoformat(timespec="seconds"),
            steps=steps,
            error=str(e),
        )
        return result

    # 从 steps 中提取高低点和时间轴
    support_price = 0
    resistance_price = 0
    atr_price = 0
    entry_zone = (0.0, 0.0)
    target_1 = 0.0
    target_2 = 0.0
    risk_reward = 0.0
    hold_days = 0
    milestones: list[dict] = []

    # 从步骤中提取数据
    for s in steps:
        if s.name == "高低点分析" and s.status == "ok":
            support_price = s.data.get("nearest_support", 0)
            resistance_price = s.data.get("nearest_resistance", 0)
            atr_price = s.data.get("atr", 0)
        if s.name == "高低点预测" and s.status == "ok":
            # 使用优化后的高低点预测
            predicted_high = s.data.get("predicted_high", 0)
            predicted_low = s.data.get("predicted_low", 0)
            if predicted_high > 0:
                resistance_price = predicted_high
            if predicted_low > 0:
                support_price = predicted_low
        if s.name == "时间轴计划" and s.status == "ok":
            entry_zone = s.data.get("entry_zone", (0.0, 0.0))
            target_1 = s.data.get("target_1", 0)
            target_2 = s.data.get("target_2", 0)
            risk_reward = s.data.get("risk_reward", 0)
            hold_days = s.data.get("hold_days", 0)

    return ForecastResult(
        symbol=code,
        name=spec.name,
        market="future",
        timestamp=dt.datetime.now().isoformat(timespec="seconds"),
        steps=steps,
        signal=signal,
        confidence=confidence,
        reason=reason,
        risk_level=risk_level,
        suggestion=suggestion,
        forecast_price=target_price,
        high_point=resistance_price if signal == "SHORT" else (price + atr_price if signal == "LONG" else price * 1.01),
        low_point=support_price if signal == "LONG" else (price - atr_price if signal == "SHORT" else price * 0.99),
        stop_loss=stop_loss
        if stop_loss
        else (price + 1.5 * atr_price if signal == "SHORT" else price - 1.5 * atr_price if signal == "LONG" else 0),
        take_profit=take_profit
        if take_profit
        else (support_price if signal == "SHORT" else resistance_price if signal == "LONG" else 0),
        entry_zone=entry_zone,
        target_1=target_1,
        target_2=target_2,
        risk_reward=risk_reward,
        hold_days=hold_days,
        milestones=milestones,
    )


# ══════════════════════════════════════════════════════════════════
# 批量运行
# ══════════════════════════════════════════════════════════════════


def run_forecast(
    stocks: list[str] | None = None,
    futures: list[str] | None = None,
    llm_api_key: str = "",
    llm_provider: str = "deepseek",
) -> list[ForecastResult]:
    """期货预测。stocks参数保留兼容但不再使用。"""
    # 自动 fallback: QT_LLM_KEY → DEEPSEEK_API_KEY
    if not llm_api_key:
        llm_api_key = os.environ.get("QT_LLM_KEY", "") or os.environ.get("DEEPSEEK_API_KEY", "")
    if not llm_provider:
        llm_provider = os.environ.get("QT_LLM_PROVIDER", "deepseek")

    results: list[ForecastResult] = []

    if futures:
        for code in futures[:16]:  # 最多16个，防止超时
            try:
                log.info(f"→ {code} 期货预测...")
                r = _run_future_forecast(code, llm_api_key=llm_api_key, llm_provider=llm_provider)
                results.append(r)
                log.info(f"  ✅ {code}: {r.signal} conf={r.confidence:.0%}")
            except Exception as e:
                log.error(f"  ❌ {code}: {e}")
                results.append(
                    ForecastResult(
                        symbol=code,
                        name=code,
                        market="future",
                        timestamp=dt.datetime.now().isoformat(timespec="seconds"),
                        steps=[],
                        error=str(e),
                    )
                )

    # 归档
    try:
        _archive_report(
            {
                "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
                "count": len(results),
                "results": [r.to_dict() for r in results],
            }
        )
    except Exception:
        pass

    # Tracing: 记录每条预测到追踪表 (自学习)
    try:
        from quanttrader.tracker import record_prediction

        for r in results:
            if r.steps:
                price = 0
                for s in r.steps:
                    if s.name == "行情数据":
                        price = s.data.get("price", 0)
                        break
                record_prediction(
                    symbol=r.symbol,
                    market=r.market,
                    signal=r.signal,
                    confidence=r.confidence,
                    forecast_price=price,
                    hexagram="",
                    hexagram_sent="",
                    news_sentiment="",
                    llm_reason=r.reason,
                )
    except Exception:
        pass

    total_ok = sum(1 for r in results if not r.error)
    buys = sum(1 for r in results if r.signal in ("BUY", "LONG"))
    sells = sum(1 for r in results if r.signal in ("SELL", "SHORT"))
    log.info("╔══════════════════════════════════════════╗")
    log.info(f"║  预测完成: {total_ok}/{len(results)} 标的 | 多{buys} 空{sells}        ║")
    log.info("╚══════════════════════════════════════════╝")

    return results


def run_default_forecast(llm_api_key: str = "", llm_provider: str = "deepseek") -> list[ForecastResult]:
    """跑默认标的集: 茅台+平安+铁矿石+螺纹钢+原油+黄金。"""
    return run_forecast(
        stocks=["600519", "000001"],
        futures=["I", "RB", "SC", "AU"],
        llm_api_key=llm_api_key,
        llm_provider=llm_provider,
    )


# ══════════════════════════════════════════════════════════════════
# HTML 网页报告生成
# ══════════════════════════════════════════════════════════════════


def _render_steps_html(steps: list[ForecastStep]) -> str:
    rows = []
    for s in steps:
        status_cls = {"ok": "ok", "skip": "skip", "error": "err"}.get(s.status, "skip")
        rows.append(
            f'<div class="step {status_cls}">'
            f'<span class="sicon">{s.icon}</span>'
            f'<span class="sname">{s.name}</span>'
            f'<span class="stext">{s.text[:30]}</span>'
            f"</div>"
        )
    return "\n".join(rows)


def _render_card_html(r: ForecastResult) -> str:
    sig_icon = {"BUY": "🟢", "LONG": "📈", "SELL": "🔴", "SHORT": "📉", "HOLD": "⏸️", "NEUTRAL": "⚖️"}.get(r.signal, "❓")
    market_badge = {"stock": "📈 股票", "future": "⛽ 期货"}.get(r.market, r.market)

    return f"""
    <div class="card {r.market}">
      <div class="card-header">
        <span class="symbol">{r.symbol}</span>
        <span class="name">{r.name}</span>
        <span class="badge">{market_badge}</span>
      </div>
      {_render_steps_html(r.steps)}
      <div class="card-footer">
        <span class="signal">{sig_icon} {r.signal}</span>
        <span class="conf">{r.confidence:.0%}</span>
        <span class="risk {"danger" if r.risk_level == "danger" else ""}">{r.risk_level}</span>
      </div>
      <div class="reason">{r.reason[:120]}</div>
      <div class="suggestion">{r.suggestion}</div>
    </div>"""


def generate_html_report(results: list[ForecastResult], title: str = "量化预测报告") -> str:
    """生成完整的 HTML 预测报告页。"""
    cards = "\n".join(_render_card_html(r) for r in results)
    stock_n = sum(1 for r in results if r.market == "stock")
    future_n = sum(1 for r in results if r.market == "future")
    buyn = sum(1 for r in results if r.signal in ("BUY", "LONG"))
    selln = sum(1 for r in results if r.signal in ("SELL", "SHORT"))

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{title}</title>
<style>
:root{{--bg:#080c14;--panel:#10172a;--border:#1a2744;--text:#e2e6f2;--muted:#8892b0;
  --green:#10b981;--red:#ef4444;--yellow:#f59e0b;--blue:#6366f1;}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:-apple-system,'Microsoft YaHei',sans-serif;background:var(--bg);color:var(--text);padding:20px}}
h1{{font-size:18px;margin:0 0 16px}}
.summary{{display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap}}
.sbox{{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:12px 18px;text-align:center;min-width:90px}}
.sbox .n{{font-size:24px;font-weight:700}}
.sbox .l{{font-size:11px;color:var(--muted);margin-top:4px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(380px,1fr));gap:14px}}
.card{{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:14px}}
.card-header{{display:flex;align-items:center;gap:8px;margin-bottom:10px}}
.card-header .symbol{{font-size:16px;font-weight:700;font-family:monospace}}
.card-header .name{{color:var(--muted);font-size:13px}}
.card-header .badge{{font-size:10px;padding:2px 8px;border-radius:10px;background:rgba(99,102,241,.15);color:var(--blue)}}
.step{{display:flex;align-items:center;gap:8px;padding:4px 0;font-size:13px;border-bottom:1px solid rgba(26,39,68,.5)}}
.step .sicon{{font-size:14px;width:22px;text-align:center}}
.step .sname{{width:70px;flex-shrink:0;color:var(--muted);font-size:12px}}
.step .stext{{flex:1;font-size:12px}}
.step.ok{{}} .step.skip{{opacity:.5}} .step.err{{color:var(--red)}}
.card-footer{{display:flex;align-items:center;gap:10px;margin-top:10px;padding-top:8px;border-top:1px solid var(--border)}}
.card-footer .signal{{font-weight:700;font-size:14px}}
.card-footer .conf{{color:var(--muted);font-size:12px}}
.card-footer .risk{{font-size:11px;padding:2px 8px;border-radius:10px;background:rgba(16,185,129,.1);color:var(--green)}}
.card-footer .risk.danger{{background:rgba(239,68,68,.1);color:var(--red)}}
.reason{{font-size:12px;color:var(--muted);margin-top:6px;line-height:1.5}}
.suggestion{{font-size:12px;color:var(--yellow);margin-top:4px;font-weight:500}}
.footer{{margin-top:20px;text-align:center;font-size:11px;color:var(--muted)}}
</style>
</head>
<body>
<h1>📊 {title}</h1>
<div class="summary">
  <div class="sbox"><div class="n">{len(results)}</div><div class="l">总标的</div></div>
  <div class="sbox"><div class="n">{stock_n}</div><div class="l">股票</div></div>
  <div class="sbox"><div class="n">{future_n}</div><div class="l">期货</div></div>
  <div class="sbox"><div class="n" style="color:var(--green)">{buyn}</div><div class="l">看多</div></div>
  <div class="sbox"><div class="n" style="color:var(--red)">{selln}</div><div class="l">看空</div></div>
  <div class="sbox"><div class="n" style="color:var(--muted)">{dt.datetime.now().strftime("%H:%M")}</div><div class="l">生成时间</div></div>
</div>
<div class="grid">{cards}</div>
<div class="footer">quant-trader 自动生成 · 模拟数据 · 仅供参考不构成投资建议</div>
</body>
</html>"""
