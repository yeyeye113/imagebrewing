"""A-share short-term scanner — filters 5000+ stocks to top N daily candidates.

Ranks by momentum, volume, and liquidity, with basic risk gating (ST, limit-up/down).
Designed to run via `python -m quanttrader.scanner` or the /api/scanner/run endpoint.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from ..data.akshare_cn import _to_yyyymmdd, normalize_cn_symbol
from ..engine.metrics import performance_summary

logger = logging.getLogger("quanttrader.scanner")

# ── Scoring constants ──────────────────────────────────────────────
# Weights for the composite score (sums to 1.0).
_W_MOMENTUM_5D = 0.30  # 5-day price change
_W_MOMENTUM_20D = 0.15  # 20-day price change
_W_VOLUME_RATIO = 0.25  # today's volume / 5-day avg volume
_W_LIQUIDITY = 0.20  # turnover rate (stability + attractiveness)
_W_TREND = 0.10  # close vs 10-day SMA

# Gates
_MIN_TURNOVER_PCT = 1.5  # minimum daily turnover rate (%)
_MIN_AMOUNT = 20_000_000  # minimum daily turnover amount (yuan, ~2kw)
_MAX_PRICE = 200  # max price (yuan) — keeps small-cap trades affordable
_MIN_PRICE = 3.0  # min price — filters extreme penny stocks

# Path for persisting scan results.
_RESULTS_DIR = Path(os.environ.get("QT_SCANNER_DIR", "logs"))
_RESULTS_FILE = "scanner_results.json"


@dataclass
class ScanResult:
    """One candidate with scores."""

    code: str
    name: str
    price: float
    change_pct: float
    score: float  # composite 0-100
    mom_5d: float
    mom_20d: float
    vol_ratio: float
    turnover: float
    amount: float  # daily turnover amount (yuan)
    trend_pct: float  # close vs SMA10
    pe: float = 0.0
    industry: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "price": self.price,
            "change_pct": round(self.change_pct, 2),
            "score": round(self.score, 1),
            "mom_5d": round(self.mom_5d, 2),
            "mom_20d": round(self.mom_20d, 2),
            "vol_ratio": round(self.vol_ratio, 2),
            "turnover": round(self.turnover, 2),
            "amount": self.amount,
            "trend_pct": round(self.trend_pct, 2),
            "pe": round(self.pe, 1),
            "industry": self.industry,
        }


@dataclass
class ScanReport:
    timestamp: str
    candidates: list[ScanResult] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "stats": self.stats,
            "candidates": [c.to_dict() for c in self.candidates],
        }


# ── Data helpers ──────────────────────────────────────────────────


def _safe_float(val: Any) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _fetch_spot() -> pd.DataFrame:
    """Fetch the full A-share spot board.

    Tries Sina API first (unblocked), falls back to akshare (eastmoney) so the
    scanner works even when eastmoney is blocked by the operator / firewall.
    """
    import os

    # Append domains to no_proxy without deleting any env vars
    for _key in ("no_proxy", "NO_PROXY"):
        _cur = os.environ.get(_key, "")
        if "eastmoney.com" not in _cur:
            os.environ[_key] = _cur + ",eastmoney.com,push2his.eastmoney.com,push2.eastmoney.com,sina.com.cn,sinajs.cn,"

    import pandas as pd
    import requests

    session = requests.Session()
    session.trust_env = False  # ignore system proxy; no_proxy above for subprocesses

    # ── Try Sina API first (less likely to be firewalled) ──────────────
    try:
        # Fetch all A-share symbols via Sina
        resp = session.get(
            "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
            "Market_Center.getHQNodeData?page=1&num=5000&sort=symbol&asc=1&node=hs_a",
            timeout=20,
        )
        if resp.status_code == 200 and len(resp.text) > 100:
            data = resp.json()
            rows = []
            for item in data:
                try:
                    price = float(item.get("trade", 0))
                    prev_close = float(item.get("settlement", price))
                    chg = ((price - prev_close) / prev_close * 100) if prev_close > 0 else 0.0
                    rows.append(
                        {
                            "code": str(item.get("symbol", "")),
                            "name": str(item.get("name", "")),
                            "price": price,
                            "change_pct": chg,
                            "turnover": float(item.get("turnoverratio", 0)),
                            "amount": float(item.get("amount", 0)),
                            "vol_ratio": 1.0,  # placeholder; real vol_ratio computed from hist in scan()
                            "pe": float(item.get("per", 0)),
                            "industry": "",  # Sina spot API 无行业字段
                        }
                    )
                except (ValueError, TypeError):
                    continue
            if len(rows) >= 100:
                return pd.DataFrame(rows).dropna(subset=["price"])
    except Exception:
        pass  # fall through to akshare

    # ── Fallback: akshare (eastmoney) ─────────────────────────────────
    import akshare as ak

    raw = ak.stock_zh_a_spot_em()
    return raw


def _fetch_hist_batch(codes: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
    """Fetch daily OHLCV for a batch of A-share codes."""
    from ..data.akshare_cn import AkShareDataFeed
    from ..data.base import BarRequest

    feed = AkShareDataFeed(retries=2)
    results: dict[str, pd.DataFrame] = {}
    for code in codes:
        try:
            df = feed.history(BarRequest(symbol=code, start=start, end=end, interval="1d"))
            if not df.empty and len(df) >= 5:
                results[code] = df
        except Exception:
            continue
    return results


# ── Filtering ─────────────────────────────────────────────────────


def _gate(df: pd.DataFrame) -> pd.DataFrame:
    """Remove stocks that fail basic liquidity / price / risk gates."""
    df = df.copy()
    # Rename common columns from akshare.
    rename = {
        "代码": "code",
        "名称": "name",
        "最新价": "price",
        "涨跌幅": "change_pct",
        "换手率": "turnover",
        "量比": "vol_ratio",
        "成交额": "amount",
        "市盈率-动态": "pe",
        "所属行业": "industry",
    }
    for old, new in rename.items():
        if old in df.columns:
            df[new] = df[old] if new in ("code", "name", "industry") else pd.to_numeric(df[old], errors="coerce")
    # Fallback columns.
    if "vol_ratio" not in df.columns:
        df["vol_ratio"] = 1.0
    if "amount" not in df.columns:
        df["amount"] = 0.0

    # Filter numeric columns.
    df = df[df["price"].between(_MIN_PRICE, _MAX_PRICE)]
    df = df[df["turnover"] >= _MIN_TURNOVER_PCT]
    df = df[df["amount"] >= _MIN_AMOUNT]
    # Exclude ST / *ST.
    if "name" in df.columns:
        df = df[~df["name"].str.contains("ST|退市|N ", na=False)]
    # Exclude limit-up / limit-down (change ≈ ±9.9% or more).
    df = df[df["change_pct"].abs() <= 9.5]
    return df.dropna(subset=["price", "turnover", "change_pct"])


def _score(row: dict[str, Any], hist: pd.DataFrame | None) -> float:
    """Compute composite momentum/liquidity score (0-100).

    Uses raw component values; rank percentiles applied in scan().
    """
    score = 0.0

    # --- 5d momentum ---
    mom_5d = row.get("mom_5d", 0.0)
    score += min(max(mom_5d / 0.15, -1), 1) * _W_MOMENTUM_5D * 100

    # -- 20d momentum ---
    mom_20d = row.get("mom_20d", 0.0)
    score += min(max(mom_20d / 0.25, -1), 1) * _W_MOMENTUM_20D * 100

    # --- Volume ratio ---
    vr = row.get("vol_ratio", 1.0)
    vol_score = min((vr - 0.3) / 2.0, 1.5) if vr > 0.3 else -0.5
    score += max(vol_score, -1) * _W_VOLUME_RATIO * 100

    # --- Liquidity (turnover) ---
    to = row.get("turnover", 0.0)
    liq_score = min((to - _MIN_TURNOVER_PCT) / 10.0, 1.0)
    score += max(liq_score, 0) * _W_LIQUIDITY * 100

    # --- Trend (close vs SMA10) ---
    trend_pct = row.get("trend_pct", 0.0)
    trend_score = min(max(trend_pct / 0.05, -1), 1)
    score += trend_score * _W_TREND * 100

    # --- Direction bonus (上涨奖励) ---
    chg = row.get("change_pct", 0.0)
    if chg > 5:
        score += 8
    elif chg > 2:
        score += 5
    elif chg > 0:
        score += 2

    return float(max(round(score, 1), 0.0))


def _rank_percentile_scores(results: list[ScanResult]) -> None:
    """Apply rank percentile normalization to push top stocks toward 100.

    Modifies results in-place: each stock's score becomes a weighted sum
    of its rank percentile across all dimensions.
    """
    if len(results) < 2:
        return

    n = len(results)

    # Sort by each dimension and assign percentile rank (1.0 = best)
    def _pct_ranks(items: list, key, reverse=True):
        sorted_items = sorted(enumerate(items), key=lambda x: key(x[1]), reverse=reverse)
        ranks = [0.0] * len(items)
        for rank, (orig_idx, _) in enumerate(sorted_items):
            ranks[orig_idx] = 1.0 - rank / max(n - 1, 1)
        return ranks

    # Compute percentile ranks for each dimension
    r_score = _pct_ranks(results, lambda r: r.score)  # raw composite
    r_mom5 = _pct_ranks(results, lambda r: r.mom_5d)  # 5d momentum
    r_mom20 = _pct_ranks(results, lambda r: r.mom_20d)  # 20d momentum
    r_vol = _pct_ranks(results, lambda r: r.vol_ratio)  # volume ratio
    r_turn = _pct_ranks(results, lambda r: r.turnover)  # turnover
    r_trend = _pct_ranks(results, lambda r: r.trend_pct)  # trend

    # Weighted rank percentile → final score (0-100)
    # Raw composite (30) + 5d mom rank (20) + 20d mom rank (10) + vol rank (15) + turnover rank (15) + trend rank (10)
    for i, r in enumerate(results):
        final = r_score[i] * 30 + r_mom5[i] * 20 + r_mom20[i] * 10 + r_vol[i] * 15 + r_turn[i] * 15 + r_trend[i] * 10
        # Direction boost: 上涨 stocks get a rank bonus
        if r.change_pct > 3:
            final = min(final + 5, 100)
        elif r.change_pct > 0:
            final = min(final + 2, 100)
        r.score = round(final, 1)


# ── Main scanning pipeline ─────────────────────────────────────────


def scan(top_n: int = 30) -> ScanReport:
    """Run the full scan and return ranked candidates."""
    logger.info("Fetching A-share spot board...")
    raw = _fetch_spot()
    logger.info(f"Got {len(raw)} stocks, applying gates...")

    gated = _gate(raw)
    logger.info(f"After gates: {len(gated)} stocks")
    if gated.empty:
        return ScanReport(
            timestamp=dt.datetime.now().isoformat(timespec="seconds"), stats={"raw": len(raw), "gated": 0}
        )

    # Sort by preliminary momentum (change_pct + vol_ratio rough) to grab top-N for detailed scoring.
    gated["_prelim"] = gated["change_pct"].abs() + gated["vol_ratio"].fillna(1).clip(0, 5)
    prelim = gated.nlargest(min(top_n * 4, len(gated)), "_prelim")

    codes = prelim["code"].dropna().tolist()
    logger.info(f"Fetching history for {len(codes)} candidates...")
    now = dt.datetime.now()
    start = (now - dt.timedelta(days=120)).strftime("%Y-%m-%d")
    end = now.strftime("%Y-%m-%d")
    hists = _fetch_hist_batch(codes, start=start, end=end)

    results: list[ScanResult] = []
    for _, row in prelim.iterrows():
        code = row.get("code", "")
        name = row.get("name", "")
        price = _safe_float(row.get("price"))
        change_pct = _safe_float(row.get("change_pct"))
        turnover = _safe_float(row.get("turnover"))
        vol_ratio = _safe_float(row.get("vol_ratio", 1.0))
        amount = _safe_float(row.get("amount", 0.0))
        pe = _safe_float(row.get("pe", 0.0))
        industry = str(row.get("industry", ""))

        hist = hists.get(code)
        mom_5d, mom_20d, trend_pct = change_pct, 0.0, 0.0

        if hist is not None and len(hist) >= 10:
            closes = hist["close"]
            if len(closes) >= 21:
                mom_20d = float((closes.iloc[-1] / closes.iloc[-21] - 1) * 100)
                mom_5d = (
                    float((closes.iloc[-1] / closes.iloc[-min(len(closes), 6)] - 1) * 100)
                    if len(closes) >= 6
                    else change_pct
                )
            sma10 = closes.iloc[-10:].mean() if len(closes) >= 10 else closes.iloc[-1]
            trend_pct = float((closes.iloc[-1] / sma10 - 1) * 100) if sma10 > 0 else 0.0

        # Volume ratio from spot; fallback compute from hist.
        if hist is not None and len(hist) >= 6:
            avg_vol = hist["volume"].iloc[-6:-1].mean()
            today_vol = hist["volume"].iloc[-1]
            if avg_vol > 0 and today_vol > 0:
                vol_ratio = float(today_vol / avg_vol)

        row_data = {
            "mom_5d": mom_5d,
            "mom_20d": mom_20d,
            "vol_ratio": vol_ratio,
            "turnover": turnover,
            "trend_pct": trend_pct,
        }
        score = _score(row_data, hist)

        results.append(
            ScanResult(
                code=code,
                name=name,
                price=price,
                change_pct=change_pct,
                score=score,
                mom_5d=mom_5d,
                mom_20d=mom_20d,
                vol_ratio=vol_ratio,
                turnover=turnover,
                amount=amount,
                trend_pct=trend_pct,
                pe=pe,
                industry=industry,
            )
        )

    results.sort(key=lambda r: r.score, reverse=True)

    # ── 排名百分位归一化: 拉开分差，top stocks 接近 100 ──
    _rank_percentile_scores(results)
    results.sort(key=lambda r: r.score, reverse=True)

    top = results[:top_n]

    # Summary stats.
    stats = {
        "raw": len(raw),
        "gated": len(gated),
        "scored": len(results),
        "top": len(top),
        "avg_score": round(sum(r.score for r in top) / max(len(top), 1), 1),
        "avg_price": round(sum(r.price for r in top) / max(len(top), 1), 2),
    }

    report = ScanReport(timestamp=dt.datetime.now().isoformat(timespec="seconds"), candidates=top, stats=stats)

    # Persist.
    try:
        _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        (_RESULTS_DIR / _RESULTS_FILE).write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass

    logger.info(f"Scan complete: {len(top)} candidates, avg score {stats['avg_score']}")
    return report


def latest_report() -> ScanReport | None:
    """Load persisted scan results."""
    path = _RESULTS_DIR / _RESULTS_FILE
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    candidates = [ScanResult(**c) for c in data.get("candidates", [])]
    return ScanReport(timestamp=data.get("timestamp", ""), candidates=candidates, stats=data.get("stats", {}))


# ── CLI ────────────────────────────────────────────────────────────


def main():
    import argparse

    from .common import ScanConfig
    from .engine import run as engine_run

    parser = argparse.ArgumentParser(description="A-share short-term scanner")
    parser.add_argument("-n", "--top", type=int, default=12, help="Number of candidates (default: 12)")
    parser.add_argument("-j", "--json", action="store_true", help="Print JSON to stdout")
    parser.add_argument("-s", "--serve", action="store_true", help="Run continuously (every 120s)")
    parser.add_argument("--ai", action="store_true", help="Enable LLM analysis on top candidates")
    parser.add_argument("--ai-top", type=int, default=5, help="Number of top candidates for AI analysis (default: 5)")
    args = parser.parse_args()

    def _run_once():
        cfg = ScanConfig(top_n=args.top, use_ai=args.ai, ai_top_n=args.ai_top)
        picks = engine_run(config=cfg)
        if args.json:
            import json as _json
            print(_json.dumps([p.to_dict() for p in picks], ensure_ascii=False, indent=2))
        else:
            print(f"\n{'=' * 80}")
            print(f"  📡 A-share Scanner — {len(picks)} candidates" + (" (AI增强)" if args.ai else ""))
            print(f"{'=' * 80}")
            for i, p in enumerate(picks[:15], 1):
                up = "🟢" if p.chg_pct >= 0 else "🔴"
                ai_tag = ""
                if p.ai_action:
                    ai_icon = {"buy": "🟢", "sell": "🔴", "hold": "🟡"}.get(p.ai_action, "⚪")
                    ai_tag = f" {ai_icon}AI:{p.ai_action}({p.ai_confidence:.0%})"
                print(
                    f"  {i:2}. {p.code} {p.name:<8s} ¥{p.price:>7.2f} {up} {p.chg_pct:>+5.1f}%  "
                    f"score:{p.score:>5.1f}  vol:{p.vol_ratio:.1f}x  mom5:{p.mom_5d:>+5.1f}%  "
                    f"{p.industry}{ai_tag}"
                )
            if args.ai:
                print(f"\n  💡 AI分析: top {args.ai_top} 只已通过LLM研判")
            print()

    if args.serve:
        print("⏳ Continuous scanner mode — every 120s (Ctrl+C to stop)", flush=True)
        import time
        while True:
            try:
                _run_once()
            except Exception as e:
                logger.exception(f"Scan failed: {e}")
            time.sleep(120)
    else:
        _run_once()


if __name__ == "__main__":
    main()
