"""管线主引擎: 边拉行情边筛选, 深度分析, 公开 API."""
from __future__ import annotations

import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, as_completed, wait
from datetime import date

import pandas as pd

from ..log import get_logger
from ..screening_journal import ScreeningWeights
from .constants import (
    _STAGES_PENDING,
    FUTURES_POOL,
    PROFILE_FAST,
    STOCK_50,
    PipelineProfile,
    StageCallback,
    resolve_pipeline_profile,
)
from .dataclasses import PipelineResult
from .gates import check_trend, check_wuxing_gate, sector_preselect
from .helpers import (
    apply_round2_result,
    cached_loader,
    estimate_pipeline_seconds,
    news_for_symbol,
    refresh_row_depth_fields,
)
from .loaders import _load_futures_prices, _load_stock_prices
from .scoring import finalize, pick_elite, resonance_and_score

logger = get_logger("pipeline")

# ── SSE stage emit helpers ──────────────────────────────────────────


def result_to_stage_dict(r: PipelineResult, stage: str) -> dict:
    from .serialize import result_to_dict
    d = result_to_dict(r)
    if stage == "done":
        d["_partial"] = False
        d["_stage"] = "done"
        return d
    d["_partial"] = True
    d["_stage"] = stage
    if stage in ("prefetch", "screen", "news"):
        for k in ("prediction_3d", "prediction_5d", "prediction_7d", "prediction_30d"):
            if not d.get(k) or d[k] == "—":
                d[k] = _STAGES_PENDING
        if not d.get("final_score"):
            d["final_score"] = d.get("combined_score") or d.get("round1_score") or 0.0
        d["short_term_advice"] = d.get("short_term_advice") or _STAGES_PENDING
        d["long_term_advice"] = d.get("long_term_advice") or _STAGES_PENDING
        d["horizon_best"] = d.get("horizon_best") or "—"
        if d.get("confidence") is None or d["confidence"] == 0:
            d["confidence"] = None
    elif stage == "depth":
        for k, wr in (
            ("prediction_3d", "win_rate_3d"), ("prediction_5d", "win_rate_5d"),
            ("prediction_7d", "win_rate_7d"), ("prediction_30d", "win_rate_30d"),
        ):
            if d.get(wr) is None and (not d.get(k) or d[k] == _STAGES_PENDING):
                d[k] = _STAGES_PENDING
        if not d.get("final_score"):
            d["final_score"] = d.get("round2_score") or d.get("combined_score") or 0.0
    return d


def _preview_items(results: list[PipelineResult], top_n: int, stage: str) -> list[dict]:
    ranked = sorted(results, key=lambda x: x.combined_score, reverse=True)[:top_n]
    out: list[dict] = []
    for i, r in enumerate(ranked, 1):
        d = result_to_stage_dict(r, stage)
        if stage != "done":
            d["rank"] = i
        out.append(d)
    return out


def _emit_stage(
    on_stage: StageCallback | None,
    stage: str,
    results: list[PipelineResult],
    top_n: int,
    **meta,
) -> None:
    if not on_stage:
        return
    partial = stage != "done"
    step_map = {"accepted": 0, "prefetch": 0, "screen": 2, "news": 3, "depth": 5, "done": 6}
    on_stage(
        stage,
        _preview_items(results, top_n, stage),
        {"partial": partial, "step": step_map.get(stage, 0), **meta},
    )


# ── Screening one symbol ────────────────────────────────────────────

def _screen_one_symbol(
    code, name, sector, element,
    prices: pd.DataFrame, kind: str, use_wuxing: bool,
    round1_min_score: float, sw: ScreeningWeights,
    div_reading=None, bazi_reading=None,
) -> tuple[PipelineResult | None, dict[str, int]]:
    stats = {"resonance": 0, "trend": 0, "wuxing": 0}

    passed_t, trend_s = check_trend(prices, kind=kind)
    if not passed_t:
        return None, stats
    stats["trend"] = 1

    passed_r, ind = resonance_and_score(prices, kind=kind)
    if not passed_r:
        return None, stats
    stats["resonance"] = 1
    if ind is None or ind["score"] < round1_min_score or ind.get("signal") != "BUY":
        return None, stats

    if use_wuxing:
        passed_w, wuxing_info = check_wuxing_gate(
            code, name, sector, element, kind=kind,
            div_reading=div_reading, bazi_reading=bazi_reading,
        )
        if kind != "future" and not passed_w:
            return None, stats
    else:
        passed_w, wuxing_info = True, {}
    stats["wuxing"] = 1

    r = PipelineResult(
        symbol=code, name=name, type=kind, sector=sector, element=element,
        round1_score=ind["score"],
        sma_score=ind.get("sma_score", 50), rsi_score=ind.get("rsi_score", 50),
        boll_score=ind.get("boll_score", 50), mom_score=ind.get("mom_score", 50),
        signal=ind.get("signal", "HOLD"), last_price=ind.get("last_price", 0),
        combined_score=ind["score"],
        passed_resonance=passed_r, passed_trend=passed_t,
        passed_wuxing_gate=passed_w,
    )

    if use_wuxing and wuxing_info:
        wx = wuxing_info.get("wuxing", {})
        bz_info = wuxing_info.get("bazi", {})
        div = wuxing_info.get("divination")
        r.wuxing_score = wx.get("score", 50)
        r.wuxing_element = wx.get("element", "")
        r.wuxing_relation = wx.get("relation", "")
        if isinstance(bz_info, dict):
            r.bazi_score = bz_info.get("score", 50)
            r.bazi_chang_sheng = bz_info.get("chang_sheng", "")
            r.bazi_nayin = bz_info.get("nayin", "")
        if div:
            r.divination_score = div.combined_score
            r.divination_bias = div.overall_bias
            r.divination_reading = f"{div.hexagram_name} | {div.qimen_door}门"
        r.combined_score = (
            ind["score"] * 0.88
            + trend_s * 0.07
            + r.wuxing_score * sw.wuxing
            + r.divination_score * sw.meta
        )
    else:
        r.combined_score = ind["score"] * 0.92 + trend_s * 0.08

    return r, stats


# ── News batch ──────────────────────────────────────────────────────

def _apply_news_batch(results: list[PipelineResult], use_news: bool, sw: ScreeningWeights) -> None:
    if not use_news:
        for r in results:
            r.news_score, r.news_label = 50.0, "—"
        return

    def _one(r: PipelineResult) -> None:
        ns = news_for_symbol(r.symbol)
        r.news_score = ns["score"]
        r.news_label = ns["label"]
        r.news_count = ns["count"]
        if ns["sentiment_raw"] < -0.5:
            r.combined_score *= 0.85
        elif ns["sentiment_raw"] > 0.3:
            r.combined_score = min(100.0, r.combined_score + 2.0)
        r.combined_score = r.combined_score * (1.0 - sw.news) + r.news_score * sw.news

    workers = min(8, max(1, len(results)))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(_one, results))


# ── Edge-collect & prefetch ─────────────────────────────────────────

def _collect_screen_futures(
    screen_futs, all_results, stats, on_stage, top_n, last_emit,
) -> list:
    pending = []
    changed = False
    for fut in screen_futs:
        if not fut.done():
            pending.append(fut)
            continue
        try:
            r, st = fut.result()
            stats["resonance"] += st["resonance"]
            stats["trend"] += st["trend"]
            stats["wuxing"] += st["wuxing"]
            if r is not None:
                all_results.append(r)
                changed = True
        except Exception:
            pass
    if changed and on_stage:
        now = time.time()
        if len(all_results) == 1 or now - last_emit[0] >= 0.3:
            last_emit[0] = now
            _emit_stage(on_stage, "screen", all_results, top_n, n_surv=len(all_results))
    return pending


def _prefetch_and_screen(
    filtered_syms, load_fn, *, kind, use_wuxing,
    round1_min_score, sw, div_reading, bazi_reading,
    top_n, on_stage, profile: PipelineProfile,
):
    sym_by_code = {c: (c, n, s, e) for c, n, s, e in filtered_syms}
    codes = list(sym_by_code.keys())
    prices_map: dict[str, pd.DataFrame] = {}
    all_results: list[PipelineResult] = []
    stats = {"resonance": 0, "trend": 0, "wuxing": 0}
    last_emit = [0.0]

    _emit_stage(on_stage, "accepted", [], top_n, profile=profile.name, prices_total=len(codes))

    screen_futs = []
    deadline = time.time() + profile.prefetch_max_wait
    load_futs_map = {}

    with ThreadPoolExecutor(max_workers=profile.screen_workers) as screen_ex:
        with ThreadPoolExecutor(max_workers=profile.loader_workers) as load_ex:
            load_futs_map = {load_ex.submit(load_fn, c): c for c in codes}
            pending = set(load_futs_map.keys())

            while pending and time.time() < deadline:
                if (
                    len(all_results) >= max(top_n, profile.early_min_results)
                    and len(prices_map) >= profile.early_min_prices
                ):
                    logger.info("[%s] 行情早停: loaded=%d results=%d", kind, len(prices_map), len(all_results))
                    break

                timeout = min(0.35, max(0.05, deadline - time.time()))
                done, pending = wait(pending, timeout=timeout, return_when=FIRST_COMPLETED)
                for fut in done:
                    code = load_futs_map[fut]
                    try:
                        df = fut.result(timeout=profile.loader_timeout)
                    except Exception:
                        df = None
                    if df is not None and not df.empty:
                        prices_map[code] = df
                        _emit_stage(on_stage, "prefetch", all_results, top_n,
                                    prices_loaded=len(prices_map), prices_total=len(codes))
                        _, name, sector, element = sym_by_code[code]
                        screen_futs.append(screen_ex.submit(
                            _screen_one_symbol,
                            code, name, sector, element,
                            df, kind, use_wuxing, round1_min_score, sw,
                            div_reading, bazi_reading,
                        ))
                screen_futs = _collect_screen_futures(screen_futs, all_results, stats, on_stage, top_n, last_emit)

        drain_deadline = time.time() + 6.0
        while screen_futs and time.time() < drain_deadline:
            screen_futs = _collect_screen_futures(screen_futs, all_results, stats, on_stage, top_n, last_emit)
            if screen_futs:
                time.sleep(0.04)

    return all_results, prices_map, stats


# ── Main pipeline ───────────────────────────────────────────────────

def _run_pipeline(
    symbols, loader_fn, kind="stock", top_n=10,
    use_news=True, use_wuxing=True, wuxing_weight=0.05,
    round1_min_score=72.0, min_final_score=78.0,
    weights: ScreeningWeights | None = None,
    on_stage=None, profile=None,
):
    sw = (weights or ScreeningWeights()).normalized()
    prof = profile or PROFILE_FAST
    if prof.force_no_news:
        use_news = False
    if prof.force_no_wuxing:
        use_wuxing = False
    # 新闻/五行融合已从产品面下线
    use_news = False
    use_wuxing = False
    t0 = time.time(); today = date.today()
    all_results: list[PipelineResult] = []
    pipeline_log: dict = {"profile": prof.name}

    if top_n <= 0:
        pipeline_log["elapsed_s"] = 0; pipeline_log["skipped"] = True
        pipeline_log["estimate_s"] = 0
        return [], pipeline_log

    pipeline_log["estimate_s"] = estimate_pipeline_seconds(kind, len(symbols), top_n, use_news, prof)

    # Step 0: 标的池预筛（按容量裁剪）
    logger.info("[%s] Step 0/6: 标的预筛 (profile=%s)...", kind, prof.name)
    filtered_syms, sector_summary = sector_preselect(symbols, use_wuxing, max_symbols=prof.pool_cap)
    pipeline_log["sector_preselect"] = sector_summary
    logger.info("[%s] 预筛: %d → %d 只", kind, len(symbols), len(filtered_syms))

    load_fn = cached_loader(loader_fn)

    # Step 1-3: 边拉行情边筛选
    all_results, prices_map, gate_stats = _prefetch_and_screen(
        filtered_syms, load_fn,
        kind=kind, use_wuxing=use_wuxing, round1_min_score=round1_min_score,
        sw=sw, div_reading=None, bazi_reading=None,
        top_n=top_n, on_stage=on_stage, profile=prof,
    )
    n_resonance = gate_stats["resonance"]
    n_trend = gate_stats["trend"]
    n_wuxing = gate_stats["wuxing"]

    _emit_stage(on_stage, "screen", all_results, top_n, n_surv=len(all_results), gates=gate_stats)

    pipeline_log["gates"] = {"resonance": n_resonance, "trend": n_trend, "wuxing": n_wuxing}
    n_surv = len(all_results)
    logger.info("[%s] 三关通过: %d 只 (共振%d 趋势%d 预筛%d)", kind, n_surv, n_resonance, n_trend, n_wuxing)
    if not all_results:
        pipeline_log["elapsed_s"] = round(time.time() - t0, 1)
        _emit_stage(on_stage, "done", [], top_n, elapsed_s=pipeline_log["elapsed_s"])
        return [], pipeline_log

    # Step 4: 新闻
    all_results.sort(key=lambda x: x.combined_score, reverse=True)
    news_n = max(top_n * 2, top_n + 3)
    news_targets = all_results[:news_n]
    news_ids = {id(r) for r in news_targets}
    logger.info("[%s] Step 4/6: 新闻过滤 (%d/%d 只)...", kind, len(news_targets), len(all_results))
    _apply_news_batch(news_targets, use_news, sw)
    if use_news:
        for r in all_results:
            if id(r) not in news_ids:
                r.news_score, r.news_label, r.news_count = 50.0, "—", 0
    all_results.sort(key=lambda x: x.combined_score, reverse=True)
    _emit_stage(on_stage, "news", all_results, top_n, n_surv=len(all_results))

    # Step 5: 深度分析
    for r in all_results[:top_n]:
        r.selected_top10 = True
    top10 = [r for r in all_results if r.selected_top10]
    logger.info("[%s] Top %d: %s", kind, len(top10),
                ", ".join(f"{r.name}({r.combined_score:.0f})" for r in top10[:5]))

    logger.info("[%s] Step 5/6: 深度分析 (%d 只)...", kind, len(top10))
    r2_workers = min(10, max(1, len(top10)))
    with ThreadPoolExecutor(max_workers=r2_workers) as ex:
        futs = [ex.submit(apply_round2_result, r, prices_map, load_fn) for r in top10]
        completed_indices = set()
        for fut in as_completed(futs):
            try:
                fut.result()
            except Exception:
                pass
            for idx, f in enumerate(futs):
                if f is fut and idx not in completed_indices:
                    completed_indices.add(idx)
                    refresh_row_depth_fields(top10[idx])
                    break
            _emit_stage(on_stage, "depth", all_results, top_n,
                        n_depth_done=sum(1 for r in top10 if r.round2_score is not None),
                        n_depth_total=len(top10))

    for r in all_results:
        if not r.selected_top10:
            r.round2_score = r.win_rate_3d = r.win_rate_5d = r.win_rate_7d = r.win_rate_30d = None

    # Step 6: 综合排名
    all_results = finalize(all_results, sw)
    picked = pick_elite(all_results, top_n, min_final=min_final_score)
    for i, r in enumerate(picked, 1):
        r.rank = i
    pipeline_log["elite_count"] = len(picked)
    pipeline_log["min_final_score"] = min_final_score
    pipeline_log["weights"] = sw.to_dict()
    elapsed = time.time() - t0
    pipeline_log["elapsed_s"] = round(elapsed, 1)
    high_conf = sum(1 for r in picked if r.confidence >= 0.85)
    logger.info("[%s] 完成 %.1fs | 优质输出 %d 只 | 高置信度(≥85%%): %d 只", kind, elapsed, len(picked), high_conf)
    _emit_stage(on_stage, "done", picked, top_n, elapsed_s=pipeline_log["elapsed_s"])
    return picked, pipeline_log


# ── Precise mode ────────────────────────────────────────────────────

def _precise_pred_to_pipeline_result(pred, rank=0) -> PipelineResult:
    return PipelineResult(
        symbol=pred.symbol, name=pred.name, type="stock",
        round1_score=pred.confidence, sma_score=pred.multi_factor_composite,
        rsi_score=0, boll_score=0, mom_score=0,
        signal=pred.direction_label, last_price=pred.last_price,
        news_score=50, news_label="", news_count=0,
        wuxing_score=50, wuxing_element="", wuxing_relation="",
        combined_score=pred.confidence, selected_top10=True,
        round2_score=pred.confidence,
        win_rate_3d=None, win_rate_5d=None, win_rate_7d=None, win_rate_30d=None,
        avg_return_3d=None, avg_return_5d=None, avg_return_7d=None, avg_return_30d=None,
        sharpe_round2=None, final_score=pred.confidence,
        prediction_3d=pred.prediction_3d, prediction_5d="—",
        prediction_7d=pred.prediction_7d, prediction_30d=pred.prediction_30d,
        confidence=pred.confidence, rank=rank, correction_factor=1.0, corrected=False,
        passed_resonance=pred.layers_agree >= 5, passed_trend=pred.layers_agree >= 6,
        passed_wuxing_gate=True,
        bazi_score=50, bazi_chang_sheng="", bazi_nayin="",
        divination_score=50, divination_bias="", divination_reading="",
        meta_score=0, tech_score=pred.multi_factor_composite,
        short_term_advice=pred.prediction_3d, long_term_advice=pred.prediction_30d,
        horizon_best="medium",
    )


def _run_v2_pipeline(kind: str, top_n=3, on_stage=None, profile: str = "precise"):
    """11 层引擎批量预测 (precise / research / explore)."""
    import time as _time

    from ..prediction_engine_v2 import (
        OOS_BENCHMARK,
        predict_futures_precise,
        predict_stocks_precise,
        resolve_profile_thresholds,
    )
    t0 = _time.time()
    label = "高精度" if profile == "precise" else "研究档"
    if on_stage:
        on_stage(f"L1-L11 {label}筛选中…", [], {"status": "running", "profile": profile})
    if kind == "stock":
        preds = predict_stocks_precise(top_n=top_n, profile=profile)
        pool_len = len(STOCK_50)
    else:
        preds = predict_futures_precise(top_n=top_n, profile=profile)
        pool_len = len(FUTURES_POOL)
    results = [_precise_pred_to_pipeline_result(p, i + 1) for i, p in enumerate(preds)]
    elapsed = _time.time() - t0
    min_c, min_a, mode = resolve_profile_thresholds(profile)
    meta = {
        "elapsed_s": round(elapsed, 2),
        "mode": profile,
        "output_mode": mode,
        "total_candidates": pool_len,
        "passed_filter": len(results),
        "min_confidence": min_c,
        "min_agree_layers": min_a,
    }
    # OOS 实证基准 + 免责声明对所有档位（尤其 precise/production「高精度」）都必须透出：
    # 实测 OOS≈随机、confidence_corr≈0，若只在 research 档附带，用户会把 precise 的
    # 85% 置信度误当真实命中率——这正是最需要提示风险的地方，故一律附带。
    meta["oos_benchmark"] = OOS_BENCHMARK
    meta["confidence_disclaimer"] = OOS_BENCHMARK.get("disclaimer", "")
    meta["confidence_is_calibrated"] = False
    if on_stage:
        on_stage(f"{label}筛选完成", [r.__dict__ for r in results], meta)
    return results, meta


def _run_precise_stock_pipeline(top_n=3, on_stage=None):
    return _run_v2_pipeline("stock", top_n, on_stage, profile="precise")


def _run_precise_futures_pipeline(top_n=3, on_stage=None):
    return _run_v2_pipeline("future", top_n, on_stage, profile="precise")


def _run_research_stock_pipeline(top_n=10, on_stage=None):
    return _run_v2_pipeline("stock", top_n, on_stage, profile="research")


def _run_research_futures_pipeline(top_n=10, on_stage=None):
    return _run_v2_pipeline("future", top_n, on_stage, profile="research")

# ── Public API ──────────────────────────────────────────────────────

def run_stock_pipeline(top_n=10, use_news=True, use_wuxing=True, wuxing_weight=0.05,
                       round1_min_score=72.0, min_final_score=78.0,
                       weights=None, on_stage=None, profile=None):
    if top_n <= 0:
        return [], {"elapsed_s": 0, "skipped": True, "estimate_s": 0}
    prof = profile if isinstance(profile, PipelineProfile) else resolve_pipeline_profile(
        profile if isinstance(profile, str) else None,
    )
    if prof.name == "precise":
        return _run_precise_stock_pipeline(top_n, on_stage)
    if prof.name == "research":
        return _run_research_stock_pipeline(top_n, on_stage)
    return _run_pipeline(STOCK_50, _load_stock_prices, "stock", top_n, use_news, use_wuxing,
                         wuxing_weight, round1_min_score, min_final_score, weights, on_stage, prof)


def run_futures_pipeline(top_n=10, use_news=True, use_wuxing=True, wuxing_weight=0.05,
                         round1_min_score=70.0, min_final_score=76.0,
                         weights=None, on_stage=None, profile=None):
    if top_n <= 0:
        return [], {"elapsed_s": 0, "skipped": True, "estimate_s": 0}
    prof = profile if isinstance(profile, PipelineProfile) else resolve_pipeline_profile(
        profile if isinstance(profile, str) else None,
    )
    if prof.name == "precise":
        return _run_precise_futures_pipeline(top_n, on_stage)
    if prof.name == "research":
        return _run_research_futures_pipeline(top_n, on_stage)
    return _run_pipeline(FUTURES_POOL, _load_futures_prices, "future", top_n, use_news, use_wuxing,
                         wuxing_weight, round1_min_score, min_final_score, weights, on_stage, prof)
