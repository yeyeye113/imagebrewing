"""数据加载器: A股/期货行情拉取, 缓存, 并行预拉."""
from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

import pandas as pd

from ..data.base import _normalize
from ..log import get_logger
from .constants import _CACHE_MAX_SIZE, _CACHE_TTL_S, _LOADER_TIMEOUT_S, _PRICE_CACHE

logger = get_logger("pipeline")


def _load_stock_prices(code: str):
    from datetime import datetime as dt

    import akshare as ak
    end = dt.now().strftime("%Y%m%d")
    start = (dt.now() - timedelta(days=280)).strftime("%Y%m%d")
    prefix = "sh" if code.startswith(("6","68")) else "sz"
    tx = f"{prefix}{code}"
    for a in range(2):
        try:
            raw = ak.stock_zh_a_hist_tx(symbol=tx, start_date=start, end_date=end, adjust="qfq")
            if raw is not None and not raw.empty:
                break
        except Exception:
            time.sleep(0.3*(a+1))
    else:
        return None
    df = raw.copy(); df["date"] = pd.to_datetime(df["date"]); df = df.set_index("date").sort_index()
    df = df.rename(columns={c: c.lower() for c in df.columns})
    if "volume" not in df.columns and "amount" in df.columns:
        df["volume"] = (df["amount"]*10000)/df["close"].clip(lower=0.01)
    df = df.dropna(subset=["close"]); return _normalize(df) if len(df)>=60 else None


def _load_futures_prices(symbol: str):
    """加载期货行情数据, 支持多种合约格式."""
    import akshare as ak

    code = symbol.strip().upper()
    candidates = [
        f"{code}0",
        f"{code}2401",
        code,
        f"{code}M",
    ]

    raw = None
    for attempt_code in candidates:
        for a in range(2):
            try:
                raw = ak.futures_zh_daily_sina(symbol=attempt_code)
                if raw is not None and not raw.empty:
                    break
            except Exception:
                time.sleep(0.2 * (a + 1))
        if raw is not None and not raw.empty:
            break

    if raw is None or raw.empty:
        return None

    df = raw.rename(columns={c: c.lower() for c in raw.columns})
    keep = [c for c in ("date", "open", "high", "low", "close", "volume") if c in df.columns]
    if len(keep) < 4:
        return None
    df = df[keep]
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    df = df.dropna(subset=["close"])
    return _normalize(df) if len(df) >= 60 else None


def cached_loader(loader_fn: Callable[[str], pd.DataFrame | None]) -> Callable[[str], pd.DataFrame | None]:
    """进程内行情缓存，重复运行秒开."""
    def load(code: str) -> pd.DataFrame | None:
        now = time.time()
        hit = _PRICE_CACHE.get(code)
        if hit and now - hit[0] < _CACHE_TTL_S:
            return hit[1]
        df = loader_fn(code)
        if df is not None and not df.empty:
            if len(_PRICE_CACHE) >= _CACHE_MAX_SIZE:
                oldest_key = min(_PRICE_CACHE, key=lambda k: _PRICE_CACHE[k][0])
                del _PRICE_CACHE[oldest_key]
            _PRICE_CACHE[code] = (now, df)
        return df
    return load


def prefetch_prices(
    codes: list[str],
    loader_fn: Callable[[str], pd.DataFrame | None],
    max_workers: int = 12,
    timeout_s: float = _LOADER_TIMEOUT_S,
) -> dict[str, pd.DataFrame]:
    """并行预拉行情，单只超时跳过，避免整管线挂死."""
    out: dict[str, pd.DataFrame] = {}
    if not codes:
        return out
    workers = min(max_workers, max(2, len(codes)))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(loader_fn, c): c for c in codes}
        for fut in as_completed(futs):
            code = futs[fut]
            try:
                df = fut.result(timeout=timeout_s)
                if df is not None and not df.empty:
                    out[code] = df
            except Exception:
                pass
    return out


def estimate_pipeline_seconds(
    kind: str = "stock",
    pool_size: int = 50,
    top_n: int = 10,
    use_news: bool = False,
    profile="fast",
) -> float:
    """预估管线耗时 (秒)，供前端倒计时."""
    from .constants import PipelineProfile, resolve_pipeline_profile
    prof = profile if isinstance(profile, PipelineProfile) else resolve_pipeline_profile(
        profile if isinstance(profile, str) else "fast",
    )
    per_symbol = 0.45 if kind == "future" else 0.55
    pool = min(pool_size, prof.pool_cap)
    news_factor = 1.1 if use_news and not prof.force_no_news else 1.0
    scan = pool * per_symbol * news_factor * 0.12
    depth = max(top_n, 1) * 0.45
    overhead = 1.5 if kind == "stock" else 1.0
    return round(max(4.0, scan + depth + overhead), 0)
