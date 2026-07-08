"""Prediction Log Engine — 预测快照持久化 + 偏差分析 + 自适应矫正.

Records every `/predict` snapshot, backfills actual returns later,
and computes per-symbol calibration factors to reduce systematic bias.

纯 Python，零第三方依赖（numpy/pandas 仅用于统计计算，可选回退）。
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


# ── Data structures ──────────────────────────────────────────────────

@dataclass
class PredictionLog:
    """A single prediction snapshot, optionally backfilled with actuals.

    Fields mirror ``RankedSymbol.to_dict()`` so a single dict drives both
    ``PredictionLog`` (JSONL persistence) and Pydantic response models.
    """
    timestamp: str           # ISO-8601
    symbol: str
    name: str = ""
    type: str = "stock"      # "stock" | "future"
    # ── core scores (RankedSymbol.to_dict) ──────────────────────
    score: float = 0.0
    signal: str = "HOLD"
    sma_score: float = 0.0
    rsi_score: float = 0.0
    boll_score: float = 0.0
    mom_score: float = 0.0
    last_price: float = 0.0
    change_1w_pct: float = 0.0
    change_1m_pct: float = 0.0
    sharpe: float = 0.0
    total_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    # ── v0.5 enhanced fields ───────────────────────────────────
    news_sentiment: float = 0.0         # −1..+1
    news_label: str = ""                # bullish/bearish/neutral
    wuxing_score: float = 50.0          # 0–100
    wuxing_element: str = ""
    wuxing_relation: str = ""
    corrected_score: float = 0.0        # 偏差矫正后的最终得分
    # ── backfilled fields ──────────────────────────────────────
    actual_price_1w: float | None = None
    actual_price_1m: float | None = None
    actual_return_1w: float | None = None
    actual_return_1m: float | None = None
    deviation_1w: float | None = None
    deviation_1m: float | None = None
    filled: bool = False

    def to_dict(self) -> dict:
        d = {f: getattr(self, f) for f in self.__dataclass_fields__.keys()}
        return d

    @classmethod
    def from_dict(cls, d: dict) -> PredictionLog:
        fields = set(cls.__dataclass_fields__.keys())
        return cls(**{k: v for k, v in d.items() if k in fields})


@dataclass
class DeviationStats:
    """Per-symbol forecast-accuracy statistics."""
    symbol: str
    name: str = ""
    type: str = "stock"
    n_samples: int = 0
    # 1-week
    rmse_1w: float = 0.0
    mae_1w: float = 0.0
    direction_accuracy_1w: float = 0.0   # 预测方向 vs 实际方向
    mean_bias_1w: float = 0.0             # 正=高估, 负=低估
    # 1-month
    rmse_1m: float = 0.0
    mae_1m: float = 0.0
    direction_accuracy_1m: float = 0.0
    mean_bias_1m: float = 0.0
    # Calibration
    calibration_factor: float = 1.0       # 矫正系数 (0.5~2.0)
    last_updated: str = ""

    def to_dict(self) -> dict:
        return {f: getattr(self, f) for f in self.__dataclass_fields__.keys()}


# ── Helpers ──────────────────────────────────────────────────────────

def _score_to_return(score: float) -> float:
    """Map a 0-100 bullish score to an expected 1-week return (decimal).

    50=neutral→0%, 100=max bullish→+5%, 0=max bearish→-5%.
    """
    return (score - 50.0) / 1000.0  # 0.05 per 50 points


def _actual_to_score(actual_return: float) -> float:
    """Inverse map: observed 1-week return → equivalent score."""
    return max(0.0, min(100.0, actual_return * 1000.0 + 50.0))


def _ensure_dir(path: str) -> Path:
    """Ensure a directory exists and return its Path."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _safe_mean(values: list[float]) -> float:
    """Mean of a list, returning 0.0 if empty."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def _safe_rmse(values: list[float]) -> float:
    """RMSE of a list of errors."""
    if not values:
        return 0.0
    return math.sqrt(sum(v * v for v in values) / len(values))


def _safe_mae(values: list[float]) -> float:
    """MAE of a list of errors."""
    if not values:
        return 0.0
    return sum(abs(v) for v in values) / len(values)


# ── Prediction Logger ────────────────────────────────────────────────

class PredictionLogger:
    """Writes prediction snapshots to daily JSONL files."""

    def __init__(self, log_dir: str = "") -> None:
        if not log_dir:
            # Default: quanttrader/prediction_logs/ (sibling to this file)
            log_dir = str(Path(__file__).resolve().parent / "prediction_logs")
        self.log_dir = _ensure_dir(log_dir)

    # ── file helpers ─────────────────────────────────────────────

    def _file_for_date(self, date_str: str) -> Path:
        """Return the JSONL path for a given date string ``YYYY-MM-DD``."""
        return self.log_dir / f"predictions_{date_str}.jsonl"

    def _all_log_files(self) -> list[Path]:
        """Return all prediction log files sorted by date."""
        return sorted(
            self.log_dir.glob("predictions_*.jsonl"),
            key=lambda p: p.name,
        )

    # ── write ─────────────────────────────────────────────────────

    def log_predictions(
        self,
        stocks: list,
        futures: list,
        timestamp: str | None = None,
    ) -> int:
        """Persist a batch of ranked symbols to today's JSONL file.

        Accepts **dicts** (from ``to_dict()``) or ``RankedSymbol`` objects.
        Returns the number of entries written.
        """
        if timestamp is None:
            timestamp = datetime.now().isoformat()
        date_str = timestamp[:10]
        path = self._file_for_date(date_str)
        count = 0

        # Normalise to dicts once.
        def _as_dict(r):
            if isinstance(r, dict):
                return r
            # RankedSymbol → dict via to_dict()
            if hasattr(r, "to_dict"):
                return r.to_dict()
            # fallback: copy known fields
            d = {}
            for f in PredictionLog.__dataclass_fields__:
                k = f
                if hasattr(r, k):
                    d[k] = getattr(r, k)
            return d

        with open(path, "a", encoding="utf-8") as f:
            for items, kind in [(stocks, "stock"), (futures, "future")]:
                for r in items:
                    d = _as_dict(r)
                    log = PredictionLog(
                        timestamp=timestamp,
                        symbol=d.get("symbol", ""),
                        name=d.get("name", ""),
                        type=kind,
                        score=d.get("score", 0),
                        signal=d.get("signal", "HOLD"),
                        sma_score=d.get("sma_score", 0),
                        rsi_score=d.get("rsi_score", 0),
                        boll_score=d.get("boll_score", 0),
                        mom_score=d.get("mom_score", 0),
                        last_price=d.get("last_price", 0),
                        change_1w_pct=d.get("change_1w_pct", 0),
                        change_1m_pct=d.get("change_1m_pct", 0),
                        sharpe=d.get("sharpe", 0),
                        total_return_pct=d.get("total_return_pct", 0),
                        max_drawdown_pct=d.get("max_drawdown_pct", 0),
                        news_sentiment=d.get("news_sentiment", 0),
                        news_label=d.get("news_label", ""),
                        wuxing_score=d.get("wuxing_score", 50),
                        wuxing_element=d.get("wuxing_element", ""),
                        wuxing_relation=d.get("wuxing_relation", ""),
                        corrected_score=d.get("corrected_score", 0),
                    )
                    f.write(json.dumps(log.to_dict(), ensure_ascii=False) + "\n")
                    count += 1
        return count

    # ── read ───────────────────────────────────────────────────────

    def get_recent_predictions(
        self,
        symbol: str = "",
        n: int = 50,
        kind: str = "",
    ) -> list[PredictionLog]:
        """Query the most recent N prediction entries, optionally filtered by symbol/type."""
        results: list[PredictionLog] = []
        for path in reversed(self._all_log_files()):
            try:
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if symbol and d.get("symbol", "") != symbol:
                            continue
                        if kind and d.get("type", "") != kind:
                            continue
                        # Deduplicate: if the same (timestamp, symbol) appears
                        # multiple times (from append-only fills), keep the last.
                        entry = PredictionLog.from_dict(d)
                        for j, prev in enumerate(results):
                            if prev.symbol == entry.symbol and prev.timestamp == entry.timestamp:
                                results[j] = entry  # replace with newer
                                break
                        else:
                            results.append(entry)
                        # After dedup, check limit.
                        if len(results) >= n:
                            # Trim any overshoot
                            results.sort(key=lambda e: e.timestamp, reverse=True)
                            results = results[:n]
                            break
                if len(results) >= n:
                    break
            except OSError:
                pass
        return results

    def get_predictions_for_symbol(
        self,
        symbol: str,
        filled_only: bool = False,
    ) -> list[PredictionLog]:
        """Return all predictions for a given symbol, newest first.

        Deduplicates by (timestamp, symbol), keeping the most recent occurrence.
        """
        seen: dict[tuple[str, str], PredictionLog] = {}
        for path in self._all_log_files():
            try:
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if d.get("symbol", "") != symbol:
                            continue
                        entry = PredictionLog.from_dict(d)
                        if filled_only and not entry.filled:
                            continue
                        seen[(entry.timestamp, entry.symbol)] = entry  # most recent wins
            except OSError:
                pass
        return sorted(seen.values(), key=lambda e: e.timestamp, reverse=True)

    def get_unfilled(self) -> list[PredictionLog]:
        """Return all entries where ``filled`` is False (deduplicated, newest wins)."""
        seen: dict[tuple[str, str], PredictionLog] = {}
        for path in self._all_log_files():
            try:
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        entry = PredictionLog.from_dict(d)
                        key = (entry.timestamp, entry.symbol)
                        if key in seen:
                            if entry.filled and not seen[key].filled:
                                seen[key] = entry  # filled version wins
                            continue
                        seen[key] = entry
            except OSError:
                pass
        return [e for e in seen.values() if not e.filled]

    def get_filled_predictions(self, n: int = 500) -> list[PredictionLog]:
        """Return filled entries only, newest first (deduplicated)."""
        seen: dict[tuple[str, str], PredictionLog] = {}
        for path in self._all_log_files():
            try:
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        entry = PredictionLog.from_dict(d)
                        if not entry.filled:
                            continue
                        seen[(entry.timestamp, entry.symbol)] = entry
            except OSError:
                pass
        ordered = sorted(seen.values(), key=lambda e: e.timestamp, reverse=True)
        return ordered[:n]

    # ── backfill ───────────────────────────────────────────────────

    def fill_actuals(self) -> dict:
        """Scan unfilled logs and backfill actual returns.

        For each unfilled entry, attempt to load the latest price with akshare
        (A-shares) or akshare futures, then compute the actual 1w/1m returns
        and deviations.

        Returns a summary dict: ``{n_processed, n_filled, n_skipped, n_errors}``.
        """
        unfilled = self.get_unfilled()
        if not unfilled:
            return {"n_processed": 0, "n_filled": 0, "n_skipped": 0, "n_errors": 0}

        summary = {"n_processed": len(unfilled), "n_filled": 0, "n_skipped": 0, "n_errors": 0}

        # Only import akshare when needed — may not be installed.
        try:
            import akshare as ak  # noqa: F401
        except ImportError:
            summary["n_skipped"] = len(unfilled)
            return summary

        from datetime import datetime as dt

        for entry in unfilled:
            try:
                ts = dt.fromisoformat(entry.timestamp)
                # Need at least 30 days since prediction to backfill 1m
                age_days = (dt.now() - ts).days

                current_price = None
                price_1w = None
                price_1m = None

                if entry.type == "stock":
                    prices = _load_stock_bars(entry.symbol, ts)
                    if prices is not None and len(prices) >= 5:
                        # Map timestamp to the correct row index
                        dates = prices.index
                        # Find the bar closest to (and before/at) prediction time
                        idx = _find_nearest_idx(dates, ts)
                        if idx is not None:
                            current_price = float(prices["close"].iloc[idx])
                            if idx + 5 < len(prices):
                                price_1w = float(prices["close"].iloc[min(idx + 5, len(prices) - 1)])
                            if idx + 20 < len(prices):
                                price_1m = float(prices["close"].iloc[min(idx + 20, len(prices) - 1)])

                elif entry.type == "future":
                    prices = _load_future_bars(entry.symbol, ts)
                    if prices is not None and len(prices) >= 5:
                        dates = prices.index
                        idx = _find_nearest_idx(dates, ts)
                        if idx is not None:
                            current_price = float(prices["close"].iloc[idx])
                            if idx + 5 < len(prices):
                                price_1w = float(prices["close"].iloc[min(idx + 5, len(prices) - 1)])
                            if idx + 20 < len(prices):
                                price_1m = float(prices["close"].iloc[min(idx + 20, len(prices) - 1)])

                if current_price is None or current_price <= 0:
                    # Not enough data yet — skip, will retry later
                    summary["n_skipped"] += 1
                    continue

                entry.actual_price_1w = price_1w
                entry.actual_price_1m = price_1m

                if price_1w and current_price > 0:
                    entry.actual_return_1w = round(float(price_1w / current_price - 1.0), 6)
                    predicted_ret = _score_to_return(entry.score)
                    actual_score_equiv = _actual_to_score(entry.actual_return_1w)
                    entry.deviation_1w = round(entry.score - actual_score_equiv, 2)

                if price_1m and current_price > 0:
                    entry.actual_return_1m = round(float(price_1m / current_price - 1.0), 6)
                    # For 1m, same logic but tolerance is wider
                    actual_score_equiv_1m = _actual_to_score(entry.actual_return_1m)
                    entry.deviation_1m = round(entry.score - actual_score_equiv_1m, 2)

                entry.filled = True
                summary["n_filled"] += 1

                # Append the filled entry (append-only, no lock needed).
                self._append_entry_to_file(entry)

            except Exception:
                summary["n_errors"] += 1

        return summary

    def _append_entry_to_file(self, entry: PredictionLog) -> None:
        """Append a single entry back to its daily JSONL file as a new line.

        Uses append-only semantics to avoid read-modify-write races.
        Multiple fill calls for the same entry add extra lines; downstream
        readers use the *last* occurrence (most recent wins).
        """
        date_str = entry.timestamp[:10]
        path = self._file_for_date(date_str)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

    # ── global stats ───────────────────────────────────────────────

    def global_stats(self) -> dict:
        """Return aggregate statistics across all filled predictions."""
        filled: list[PredictionLog] = []
        for path in self._all_log_files():
            try:
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if d.get("filled"):
                            filled.append(PredictionLog.from_dict(d))
            except OSError:
                pass

        if not filled:
            return {"n_total": 0, "n_filled": 0, "avg_rmse_1w": 0, "avg_mae_1w": 0}

        deviations_1w = [p.deviation_1w for p in filled if p.deviation_1w is not None]
        direction_correct = 0
        direction_total = 0
        for rec in filled:
            if rec.actual_return_1w is None:
                continue
            direction_total += 1
            pred_up = rec.score > 50
            actual_up = rec.actual_return_1w > 0
            if pred_up == actual_up:
                direction_correct += 1

        return {
            "n_total": len(filled),
            "n_filled": len(filled),
            "avg_rmse_1w": round(_safe_rmse(deviations_1w), 2),
            "avg_mae_1w": round(_safe_mae(deviations_1w), 2),
            "mean_bias_1w": round(_safe_mean(deviations_1w), 2),
            "direction_accuracy_1w": round(direction_correct / max(direction_total, 1), 4),
        }


# ── Deviation Tracker ────────────────────────────────────────────────

class DeviationTracker:
    """Analyzes prediction-vs-actual deviation and computes calibration factors."""

    MIN_SAMPLES = 3  # Minimum filled entries before calibration kicks in

    def __init__(self, logger: PredictionLogger) -> None:
        self.logger = logger

    def compute_symbol_deviation(self, symbol: str) -> DeviationStats:
        """Compute forecast-accuracy statistics for one symbol."""
        entries = self.logger.get_predictions_for_symbol(symbol, filled_only=True)

        stats = DeviationStats(symbol=symbol)
        if not entries:
            return stats

        stats.name = entries[0].name
        stats.type = entries[0].type
        stats.n_samples = len(entries)

        devs_1w = [e.deviation_1w for e in entries if e.deviation_1w is not None]
        devs_1m = [e.deviation_1m for e in entries if e.deviation_1m is not None]

        if devs_1w:
            stats.rmse_1w = round(_safe_rmse(devs_1w), 2)
            stats.mae_1w = round(_safe_mae(devs_1w), 2)
            stats.mean_bias_1w = round(_safe_mean(devs_1w), 2)

        if devs_1m:
            stats.rmse_1m = round(_safe_rmse(devs_1m), 2)
            stats.mae_1m = round(_safe_mae(devs_1m), 2)
            stats.mean_bias_1m = round(_safe_mean(devs_1m), 2)

        # Direction accuracy 1w
        direction_correct = 0
        direction_total = 0
        for e in entries:
            if e.actual_return_1w is None:
                continue
            direction_total += 1
            if (e.score > 50 and e.actual_return_1w > 0) or \
               (e.score <= 50 and e.actual_return_1w <= 0):
                direction_correct += 1
        if direction_total > 0:
            stats.direction_accuracy_1w = round(direction_correct / direction_total, 4)

        # Direction accuracy 1m
        direction_correct_1m = 0
        direction_total_1m = 0
        for e in entries:
            if e.actual_return_1m is None:
                continue
            direction_total_1m += 1
            if (e.score > 50 and e.actual_return_1m > 0) or \
               (e.score <= 50 and e.actual_return_1m <= 0):
                direction_correct_1m += 1
        if direction_total_1m > 0:
            stats.direction_accuracy_1m = round(direction_correct_1m / direction_total_1m, 4)

        # Calibration factor
        stats.calibration_factor = round(
            self.calibration_factor(symbol, entries), 4
        )
        stats.last_updated = datetime.now().isoformat()

        return stats

    def calibration_factor(
        self,
        symbol: str,
        entries: list[PredictionLog] | None = None,
    ) -> float:
        """Compute the calibration factor for a symbol.

        Factor ∈ [0.5, 2.0], where:
        - 1.0  = no systematic bias
        - >1.0 = model under-predicts (factor > 1 boosts scores)
        - <1.0 = model over-predicts (factor < 1 dampens scores)

        Requires at least ``MIN_SAMPLES`` filled entries.
        """
        if entries is None:
            entries = self.logger.get_predictions_for_symbol(symbol, filled_only=True)
        if len(entries) < self.MIN_SAMPLES:
            return 1.0

        # Core idea: if mean_bias is positive (over-predict), factor < 1
        #            if mean_bias is negative (under-predict), factor > 1
        devs_1w = [e.deviation_1w for e in entries if e.deviation_1w is not None]
        if not devs_1w:
            return 1.0

        mean_bias = _safe_mean(devs_1w)
        # deviation = score - actual_score_equiv
        # If mean_bias = +10 (over-predict by 10 pts), we want to dampen by ~10%
        # factor = 1.0 - mean_bias / 100  (10 pts bias → 0.9 factor)
        raw_factor = 1.0 - mean_bias / 100.0

        # Also consider direction accuracy: poor accuracy → pull toward 0.8
        direction_correct = 0
        direction_total = 0
        for e in entries:
            if e.actual_return_1w is None:
                continue
            direction_total += 1
            if (e.score > 50 and e.actual_return_1w > 0) or \
               (e.score <= 50 and e.actual_return_1w <= 0):
                direction_correct += 1
        dir_acc = direction_correct / max(direction_total, 1)

        # Blend: trust factor proportional to direction accuracy
        # If dir_acc is 0.5 (random), pull factor toward 0.8
        accuracy_anchor = 0.5 + 0.3 * dir_acc  # range ~0.65–0.8
        blended = raw_factor * dir_acc + accuracy_anchor * (1 - dir_acc)

        return max(0.5, min(2.0, blended))

    def compute_global_stats(self) -> dict:
        """Aggregate deviation statistics across all symbols."""
        all_entries: list[PredictionLog] = []
        # Scan all log files for filled entries
        for path in self.logger._all_log_files():
            try:
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if d.get("filled"):
                            all_entries.append(PredictionLog.from_dict(d))
            except OSError:
                pass

        if not all_entries:
            return {"n_total": 0, "n_filled": 0, "avg_rmse_1w": 0, "avg_mae_1w": 0}

        devs_1w = [e.deviation_1w for e in all_entries if e.deviation_1w is not None]

        direction_correct = 0
        direction_total = 0
        for e in all_entries:
            if e.actual_return_1w is None:
                continue
            direction_total += 1
            if (e.score > 50 and e.actual_return_1w > 0) or \
               (e.score <= 50 and e.actual_return_1w <= 0):
                direction_correct += 1

        # Per-type breakdown
        stocks = [e for e in all_entries if e.type == "stock"]
        futures = [e for e in all_entries if e.type == "future"]

        def _type_stats(entries):
            d = [e.deviation_1w for e in entries if e.deviation_1w is not None]
            dc = 0
            dt = 0
            for e in entries:
                if e.actual_return_1w is None:
                    continue
                dt += 1
                if (e.score > 50 and e.actual_return_1w > 0) or \
                   (e.score <= 50 and e.actual_return_1w <= 0):
                    dc += 1
            return {
                "count": len(entries),
                "rmse_1w": round(_safe_rmse(d), 2),
                "mae_1w": round(_safe_mae(d), 2),
                "direction_accuracy": round(dc / max(dt, 1), 4),
            }

        return {
            "n_total": len(all_entries),
            "n_filled": len(all_entries),
            "avg_rmse_1w": round(_safe_rmse(devs_1w), 2),
            "avg_mae_1w": round(_safe_mae(devs_1w), 2),
            "mean_bias_1w": round(_safe_mean(devs_1w), 2),
            "direction_accuracy": round(direction_correct / max(direction_total, 1), 4),
            "by_type": {
                "stock": _type_stats(stocks),
                "future": _type_stats(futures),
            },
        }


# ── Correction logic ─────────────────────────────────────────────────

def apply_correction(
    r,
    tracker: DeviationTracker,
    correction_weight: float = 0.3,
) -> dict:
    """Apply per-symbol calibration to a single RankedSymbol (or dict).

    Returns a dict with the original fields plus ``corrected_score``,
    ``correction_factor``, ``calibrated``, and adjusted sub-scores.

    ``correction_weight`` controls how aggressive the correction is:
    - 0.0 = no correction (corrected_score == original score)
    - 1.0 = full correction
    """
    symbol = r.symbol if hasattr(r, "symbol") else r.get("symbol", "")
    original_score = r.score if hasattr(r, "score") else r.get("score", 0)

    # Get calibration factor
    cf = tracker.calibration_factor(symbol)

    # Build result dict from RankedSymbol or dict
    result = {
        "symbol": symbol,
        "name": r.name if hasattr(r, "name") else r.get("name", ""),
        "score": original_score,
        "signal": r.signal if hasattr(r, "signal") else r.get("signal", "HOLD"),
        "sma_score": r.sma_score if hasattr(r, "sma_score") else r.get("sma_score", 50),
        "rsi_score": r.rsi_score if hasattr(r, "rsi_score") else r.get("rsi_score", 50),
        "boll_score": r.boll_score if hasattr(r, "boll_score") else r.get("boll_score", 50),
        "mom_score": r.mom_score if hasattr(r, "mom_score") else r.get("mom_score", 50),
        "last_price": r.last_price if hasattr(r, "last_price") else r.get("last_price", 0),
        "change_1w_pct": r.change_1w_pct if hasattr(r, "change_1w_pct") else r.get("change_1w_pct", 0),
        "change_1m_pct": r.change_1m_pct if hasattr(r, "change_1m_pct") else r.get("change_1m_pct", 0),
        "sharpe": r.sharpe if hasattr(r, "sharpe") else r.get("sharpe", 0),
        "total_return_pct": r.total_return_pct if hasattr(r, "total_return_pct") else r.get("total_return_pct", 0),
        "max_drawdown_pct": r.max_drawdown_pct if hasattr(r, "max_drawdown_pct") else r.get("max_drawdown_pct", 0),
        # Correction fields
        "correction_factor": cf,
        "calibrated": cf != 1.0 and correction_weight > 0,
    }

    if correction_weight > 0 and cf != 1.0:
        # Blend: corrected = original * (1 - w) + (original * cf) * w
        corrected = original_score * (1.0 - correction_weight) + original_score * cf * correction_weight
        result["corrected_score"] = round(max(0.0, min(100.0, corrected)), 1)
        # Also adjust sub-scores proportionally
        for key in ("sma_score", "rsi_score", "boll_score", "mom_score"):
            original_sub = result.get(key, 50)
            sub_corrected = original_sub * (1.0 - correction_weight) + original_sub * cf * correction_weight
            result[f"corrected_{key}"] = round(max(0.0, min(100.0, sub_corrected)), 1)
    else:
        result["corrected_score"] = original_score

    return result


# ── Internal helpers for backfilling ──────────────────────────────────

def _find_nearest_idx(dates, target_ts: datetime) -> int | None:
    """Find the index of the bar closest to (and ≤) the target timestamp."""
    import pandas as pd
    if isinstance(target_ts, str):
        target_ts = datetime.fromisoformat(target_ts)
    target = pd.Timestamp(target_ts)
    for i in range(len(dates) - 1, -1, -1):
        if dates[i] <= target:
            return i
    return None


def _load_stock_bars(code: str, from_ts: datetime) -> pd.DataFrame | None:
    """Load A-share daily bars from around the prediction date."""
    import time as _time

    try:
        import akshare as ak
        import pandas as pd
    except ImportError:
        return None

    end = (from_ts + timedelta(days=60)).strftime("%Y%m%d")
    start = (from_ts - timedelta(days=10)).strftime("%Y%m%d")

    prefix = "sh" if code.startswith(("6", "68")) else "sz"
    tx_code = f"{prefix}{code}"

    for attempt in range(3):
        try:
            raw = ak.stock_zh_a_hist_tx(
                symbol=tx_code, start_date=start, end_date=end, adjust="qfq",
            )
            if raw is not None and not raw.empty:
                break
        except Exception:
            _time.sleep(0.6 * (attempt + 1))
    else:
        return None

    keep = [c for c in ("date", "open", "high", "low", "close", "volume") if c in raw.columns]
    df = raw[keep].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df.dropna(subset=["close"]) if len(df) >= 5 else None


def _load_future_bars(symbol: str, from_ts: datetime) -> pd.DataFrame | None:
    """Load futures daily bars from around the prediction date."""
    import time as _time

    try:
        import akshare as ak
        import pandas as pd
    except ImportError:
        return None

    code = f"{symbol}0"
    for attempt in range(3):
        try:
            raw = ak.futures_zh_daily_sina(symbol=code)
            if raw is not None and not raw.empty:
                break
        except Exception:
            _time.sleep(0.6 * (attempt + 1))
    else:
        return None

    df = raw.rename(columns={c: c.lower() for c in raw.columns})
    keep = [c for c in ("date", "open", "high", "low", "close", "volume") if c in df.columns]
    df = df[keep].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df.dropna(subset=["close"]) if len(df) >= 5 else None
