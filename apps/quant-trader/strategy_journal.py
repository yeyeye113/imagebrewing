"""高手策略日志系统 — 信号记录、回填验证、胜率排行、自动优选、周期总结.

持久化:
  strategy_signals.jsonl   — 每次预测触发的策略信号
  strategy_summary.json    — 最新完整总结
  strategy_summary_history.jsonl — 历史总结快照
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


def _get(obj: Any, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def playbook_matches(playbook: dict, result: Any) -> bool:
    """按 playbook['match'] 规则判断标的是否符合该高手打法."""
    m = playbook.get("match") or {}
    if not m:
        return False

    signal = _get(result, "signal", "HOLD")
    if m.get("signal") and signal != m["signal"]:
        return False

    tech = float(_get(result, "tech_score") or _get(result, "round1_score") or 0)
    if m.get("min_tech_score") is not None and tech < float(m["min_tech_score"]):
        return False

    conf = float(_get(result, "confidence") or 0)
    if m.get("min_confidence") is not None and conf < float(m["min_confidence"]):
        return False

    for wr_key, min_wr in (m.get("min_win_rates") or {}).items():
        wr = _get(result, wr_key)
        if wr is None or float(wr) < float(min_wr):
            return False

    horizon_best = _get(result, "horizon_best", "")
    if m.get("horizon_best") and horizon_best != m["horizon_best"]:
        return False

    pred_key = m.get("prediction_contains")
    if pred_key:
        pred = _get(result, pred_key) or ""
        needle = m.get("prediction_text", "涨")
        if needle not in str(pred):
            return False

    return True


@dataclass
class StrategySignalLog:
    timestamp: str
    playbook_id: str
    playbook_name: str
    trader_id: str
    trader_name: str
    symbol: str
    name: str = ""
    type: str = "stock"
    tech_score: float = 0.0
    final_score: float = 0.0
    confidence: float = 0.0
    predicted_direction: str = "neutral"  # bullish | bearish | neutral
    horizon: str = "short"
    entry_price: float = 0.0
    actual_return_1w: float | None = None
    actual_return_1m: float | None = None
    direction_correct: bool | None = None
    filled: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> StrategySignalLog:
        fields = set(cls.__dataclass_fields__.keys())
        return cls(**{k: v for k, v in d.items() if k in fields})


@dataclass
class StrategyLeaderboardEntry:
    playbook_id: str
    playbook_name: str
    trader_id: str
    trader_name: str
    horizon: str
    n_signals: int = 0
    n_filled: int = 0
    n_wins: int = 0
    logged_win_rate: float | None = None
    historical_win_rate: float = 0.5
    effective_win_rate: float = 0.5
    rank: int = 0
    is_primary: bool = False
    trend: str = "stable"  # up | down | stable

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StrategySummaryReport:
    generated_at: str
    period_days: int
    primary_strategy: dict
    secondary_strategy: dict | None
    leaderboard: list[dict]
    insights: list[str]
    recommendations: list[str]
    n_signals_total: int
    n_filled_total: int
    global_logged_win_rate: float | None
    narrative: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class StrategyJournal:
    MIN_SAMPLES_FOR_LOGGED = 3

    def __init__(self, log_dir: str = "") -> None:
        base = Path(log_dir) if log_dir else Path(__file__).resolve().parent / "prediction_logs"
        base.mkdir(parents=True, exist_ok=True)
        self._dir = base
        self._signals_path = base / "strategy_signals.jsonl"
        self._summary_path = base / "strategy_summary.json"
        self._summary_hist_path = base / "strategy_summary_history.jsonl"

    def _load_all_signals(self, *, max_lines: int = 5000) -> list[StrategySignalLog]:
        if not self._signals_path.exists():
            return []
        lines = self._signals_path.read_text(encoding="utf-8").strip().splitlines()
        if len(lines) > max_lines:
            lines = lines[-max_lines:]
        out: list[StrategySignalLog] = []
        for line in lines:
            try:
                out.append(StrategySignalLog.from_dict(json.loads(line)))
            except Exception:
                continue
        return out

    def _trim_signals(self, max_lines: int = 3000) -> None:
        if not self._signals_path.exists():
            return
        lines = self._signals_path.read_text(encoding="utf-8").strip().splitlines()
        if len(lines) <= max_lines:
            return
        self._signals_path.write_text(
            "\n".join(lines[-max_lines:]) + "\n", encoding="utf-8"
        )

    def _append_signal(self, sig: StrategySignalLog) -> None:
        with self._signals_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(sig.to_dict(), ensure_ascii=False) + "\n")

    def _rewrite_signals(self, signals: list[StrategySignalLog]) -> None:
        with self._signals_path.open("w", encoding="utf-8") as f:
            for s in signals:
                f.write(json.dumps(s.to_dict(), ensure_ascii=False) + "\n")

    def _predicted_direction(self, result: Any) -> str:
        signal = _get(result, "signal", "HOLD")
        if signal == "BUY":
            return "bullish"
        if signal == "SELL":
            return "bearish"
        pred = _get(result, "prediction_7d") or _get(result, "prediction_3d") or ""
        if "涨" in str(pred):
            return "bullish"
        if "跌" in str(pred):
            return "bearish"
        return "neutral"

    def log_signals_from_results(
        self,
        results: list[Any],
        *,
        timestamp: str | None = None,
        playbooks: list[dict] | None = None,
    ) -> int:
        from .advisor import HIGH_WIN_RATE_PLAYBOOKS

        ts = timestamp or datetime.now().isoformat()
        books = playbooks or HIGH_WIN_RATE_PLAYBOOKS
        count = 0
        seen: set[tuple[str, str, str]] = set()
        for r in results:
            sym = _get(r, "symbol", "")
            if not sym:
                continue
            for pb in books:
                if not playbook_matches(pb, r):
                    continue
                key = (ts[:16], sym, pb["id"])
                if key in seen:
                    continue
                seen.add(key)
                sig = StrategySignalLog(
                    timestamp=ts,
                    playbook_id=pb["id"],
                    playbook_name=pb["name"],
                    trader_id=pb.get("trader_id", pb["id"]),
                    trader_name=pb.get("trader_name", pb.get("source", "")),
                    symbol=sym,
                    name=_get(r, "name", ""),
                    type=_get(r, "type", "stock"),
                    tech_score=float(_get(r, "tech_score") or _get(r, "round1_score") or 0),
                    final_score=float(_get(r, "final_score") or 0),
                    confidence=float(_get(r, "confidence") or 0),
                    predicted_direction=self._predicted_direction(r),
                    horizon=pb.get("horizon", "short"),
                    entry_price=float(_get(r, "last_price") or 0),
                )
                self._append_signal(sig)
                count += 1
        if count:
            self._trim_signals()
        return count

    @staticmethod
    def _best_prediction_match(sig: StrategySignalLog, candidates: list) -> Any | None:
        try:
            sig_ts = datetime.fromisoformat(sig.timestamp)
        except ValueError:
            return None
        best, best_secs = None, float("inf")
        for p in candidates:
            pts_raw = p.get("timestamp", "") if isinstance(p, dict) else getattr(p, "timestamp", "")
            if not pts_raw:
                continue
            try:
                pts = datetime.fromisoformat(pts_raw)
            except ValueError:
                continue
            diff = abs((sig_ts - pts).total_seconds())
            if diff <= 36 * 3600 and diff < best_secs:
                best_secs = diff
                best = p
        return best

    def sync_outcomes_from_predictions(self, prediction_logs: list[Any]) -> int:
        """用已回填的 prediction_log 更新策略信号实际结果."""
        signals = self._load_all_signals()
        if not signals:
            return 0

        pred_index: dict[str, list] = defaultdict(list)
        for p in prediction_logs:
            if isinstance(p, dict):
                if not p.get("filled"):
                    continue
                sym = p.get("symbol", "")
                pred_index[sym].append(p)
            else:
                if not getattr(p, "filled", False):
                    continue
                pred_index[getattr(p, "symbol", "")].append(p)

        updated = 0
        for sig in signals:
            if sig.filled:
                continue
            match = self._best_prediction_match(sig, pred_index.get(sig.symbol, []))
            if match is None:
                continue

            if isinstance(match, dict):
                ret_1w = match.get("actual_return_1w")
                ret_1m = match.get("actual_return_1m")
            else:
                ret_1w = getattr(match, "actual_return_1w", None)
                ret_1m = getattr(match, "actual_return_1m", None)

            use_ret = ret_1w if sig.horizon in ("short", "both") else (ret_1m if ret_1m is not None else ret_1w)
            if use_ret is None:
                continue

            sig.actual_return_1w = ret_1w
            sig.actual_return_1m = ret_1m
            if sig.predicted_direction == "bullish":
                sig.direction_correct = use_ret > 0
            elif sig.predicted_direction == "bearish":
                sig.direction_correct = use_ret < 0
            else:
                sig.direction_correct = abs(use_ret) < 0.02
            sig.filled = True
            updated += 1

        if updated:
            self._rewrite_signals(signals)
        return updated

    def compute_leaderboard(
        self,
        *,
        period_days: int = 90,
        playbooks: list[dict] | None = None,
    ) -> list[StrategyLeaderboardEntry]:
        from .advisor import HIGH_WIN_RATE_PLAYBOOKS

        books = {pb["id"]: pb for pb in (playbooks or HIGH_WIN_RATE_PLAYBOOKS)}
        cutoff = (datetime.now() - timedelta(days=period_days)).isoformat()
        signals = [s for s in self._load_all_signals() if s.timestamp >= cutoff]

        by_pb: dict[str, list[StrategySignalLog]] = defaultdict(list)
        for s in signals:
            by_pb[s.playbook_id].append(s)

        entries: list[StrategyLeaderboardEntry] = []
        for pb_id, pb in books.items():
            sigs = by_pb.get(pb_id, [])
            filled = [s for s in sigs if s.filled and s.direction_correct is not None]
            wins = sum(1 for s in filled if s.direction_correct)
            n_filled = len(filled)
            logged_wr = round(wins / n_filled, 4) if n_filled else None
            hist = float(pb.get("historical_win_rate", 0.5))

            if logged_wr is not None and n_filled >= self.MIN_SAMPLES_FOR_LOGGED:
                effective = logged_wr
            elif logged_wr is not None:
                effective = round(logged_wr * 0.35 + hist * 0.65, 4)
            else:
                effective = hist

            # 近期趋势: 最近一半 vs 前一半
            trend = "stable"
            if n_filled >= 4:
                mid = n_filled // 2
                recent = filled[-mid:]
                older = filled[:-mid]
                r_wr = sum(1 for s in recent if s.direction_correct) / max(len(recent), 1)
                o_wr = sum(1 for s in older if s.direction_correct) / max(len(older), 1)
                if r_wr - o_wr > 0.08:
                    trend = "up"
                elif o_wr - r_wr > 0.08:
                    trend = "down"

            entries.append(StrategyLeaderboardEntry(
                playbook_id=pb_id,
                playbook_name=pb["name"],
                trader_id=pb.get("trader_id", pb_id),
                trader_name=pb.get("trader_name", pb.get("source", "")),
                horizon=pb.get("horizon", "short"),
                n_signals=len(sigs),
                n_filled=n_filled,
                n_wins=wins,
                logged_win_rate=logged_wr,
                historical_win_rate=hist,
                effective_win_rate=effective,
                trend=trend,
            ))

        entries.sort(key=lambda e: (e.effective_win_rate, e.n_filled), reverse=True)
        for i, e in enumerate(entries, 1):
            e.rank = i
            e.is_primary = i == 1
        return entries

    def get_primary_strategy(self, horizon: str = "") -> StrategyLeaderboardEntry | None:
        board = self.compute_leaderboard()
        if horizon:
            filtered = [e for e in board if e.horizon == horizon or horizon == "blend"]
            if filtered:
                return filtered[0]
        return board[0] if board else None

    def generate_summary(self, *, period_days: int = 90, append_history: bool = False) -> StrategySummaryReport:

        board = self.compute_leaderboard(period_days=period_days)
        signals = self._load_all_signals()
        cutoff = (datetime.now() - timedelta(days=period_days)).isoformat()
        recent = [s for s in signals if s.timestamp >= cutoff]
        filled = [s for s in recent if s.filled]
        global_wr = None
        if filled:
            global_wr = round(
                sum(1 for s in filled if s.direction_correct) / len(filled), 4
            )

        primary = board[0].to_dict() if board else None
        secondary = board[1].to_dict() if len(board) > 1 else None

        insights: list[str] = []
        recommendations: list[str] = []

        if board:
            p = board[0]
            if p.n_filled >= self.MIN_SAMPLES_FOR_LOGGED:
                insights.append(
                    f"日志验证：{p.trader_name}「{p.playbook_name}」"
                    f"近{period_days}日胜率 {p.logged_win_rate:.0%}（{p.n_filled} 样本），"
                    f"综合有效胜率 {p.effective_win_rate:.0%}，当前排名第一。"
                )
            else:
                insights.append(
                    f"样本不足（{p.n_filled}<{self.MIN_SAMPLES_FOR_LOGGED}），"
                    f"暂用历史胜率 {p.historical_win_rate:.0%} 优选 {p.trader_name}「{p.playbook_name}」。"
                )

        rising = [e for e in board if e.trend == "up" and e.n_filled >= 2]
        falling = [e for e in board if e.trend == "down" and e.n_filled >= 2]
        if rising:
            insights.append(f"胜率上升：{', '.join(e.playbook_name for e in rising[:3])}。")
        if falling:
            insights.append(f"胜率回落：{', '.join(e.playbook_name for e in falling[:3])}，建议降权。")

        if primary:
            recommendations.append(
                f"当前主推：{primary.get('trader_name')} — {primary.get('playbook_name')} "
                f"（有效胜率 {float(primary.get('effective_win_rate') or 0):.0%}）"
            )
        if secondary:
            recommendations.append(
                f"备选策略：{secondary.get('trader_name')} — {secondary.get('playbook_name')}"
            )
        if global_wr is not None and global_wr < 0.45:
            recommendations.append("全局策略方向准确率偏低 → 提高技术面权重、收紧入场条件。")
        elif global_wr is not None and global_wr > 0.58:
            recommendations.append("全局策略表现良好 → 可适度沿用当前主推打法。")

        narrative_parts = [
            f"## 策略日志总结 ({datetime.now().strftime('%Y-%m-%d %H:%M')})",
            f"统计周期：近 {period_days} 日 | 信号 {len(recent)} 条 | 已验证 {len(filled)} 条",
        ]
        if global_wr is not None:
            narrative_parts.append(f"全局验证胜率：{global_wr:.0%}")
        narrative_parts.append("\n### 排行榜（按有效胜率）")
        for e in board[:8]:
            wr_s = f"{e.logged_win_rate:.0%}" if e.logged_win_rate is not None else "待验证"
            narrative_parts.append(
                f"{e.rank}. {e.trader_name}「{e.playbook_name}」"
                f" 有效{e.effective_win_rate:.0%} | 日志{wr_s} | 样本{e.n_filled} | {e.trend}"
            )
        narrative_parts.append("\n### 建议")
        narrative_parts.extend(f"- {r}" for r in recommendations)

        report = StrategySummaryReport(
            generated_at=datetime.now().isoformat(),
            period_days=period_days,
            primary_strategy=primary or {},
            secondary_strategy=secondary,
            leaderboard=[e.to_dict() for e in board],
            insights=insights,
            recommendations=recommendations,
            n_signals_total=len(recent),
            n_filled_total=len(filled),
            global_logged_win_rate=global_wr,
            narrative="\n".join(narrative_parts),
        )
        self._summary_path.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if append_history:
            with self._summary_hist_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(report.to_dict(), ensure_ascii=False) + "\n")
        return report

    def update_summary_light(self) -> dict:
        """轻量刷新：仅更新排行榜与优选，不写历史、不生成 narrative."""
        board = self.compute_leaderboard()
        primary = board[0].to_dict() if board else None
        secondary = board[1].to_dict() if len(board) > 1 else None
        payload = self.latest_summary() or {}
        payload.update({
            "generated_at": datetime.now().isoformat(),
            "primary_strategy": primary or {},
            "secondary_strategy": secondary,
            "leaderboard": [e.to_dict() for e in board],
        })
        if primary:
            p = board[0]
            if p.n_filled >= self.MIN_SAMPLES_FOR_LOGGED and p.logged_win_rate is not None:
                payload["insights"] = [
                    f"日志优选：{p.trader_name}「{p.playbook_name}」"
                    f" 有效胜率 {p.effective_win_rate:.0%}（{p.n_filled} 样本）",
                ]
        self._summary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return payload

    def latest_summary(self) -> dict | None:
        if not self._summary_path.exists():
            return None
        try:
            data = json.loads(self._summary_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def recent_signals(self, limit: int = 50) -> list[dict]:
        sigs = self._load_all_signals()
        return [s.to_dict() for s in reversed(sigs[-limit:])]

    def enrich_playbooks(self, playbooks: list[dict]) -> list[dict]:
        """为 playbook 附加日志胜率与排名."""
        board = {e.playbook_id: e for e in self.compute_leaderboard()}
        out = []
        for pb in playbooks:
            d = dict(pb)
            entry = board.get(pb["id"])
            if entry:
                d["rank"] = entry.rank
                d["logged_win_rate"] = entry.logged_win_rate
                d["effective_win_rate"] = entry.effective_win_rate
                d["n_filled"] = entry.n_filled
                d["trend"] = entry.trend
                d["is_primary"] = entry.is_primary
            else:
                d["rank"] = 99
                d["effective_win_rate"] = pb.get("historical_win_rate", 0.5)
                d["is_primary"] = False
            out.append(d)
        out.sort(key=lambda x: x.get("rank", 99))
        return out
