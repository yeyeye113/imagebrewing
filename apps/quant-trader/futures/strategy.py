"""期货 LLM 策略 — 多空双向 + 夜盘 + 合约期限 + 基差分析。

与股票 LLM 策略的区别：
- 双向交易：可以做多也可以做空
- 夜盘感知：21:00-02:30 的走势也计入分析
- 期限结构：近月/远月价差暗含市场预期
- 保证金约束：杠杆下的止损距离必须更紧
- 交割提醒：临近到期日的流动性衰减
"""

from __future__ import annotations

import json
import re

import pandas as pd

from .contracts import (
    contract_info,
    dominant_contract,
    session_label,
    trading_session,
)

# ══════════════════════════════════════════════════════════════════
# LLM Prompt — 期货专用
# ══════════════════════════════════════════════════════════════════

_FUTURES_SYSTEM_PROMPT = (
    "You are a professional Chinese futures trader with deep knowledge of the domestic "
    "commodity and financial futures markets (SHFE, DCE, CZCE, CFFEX, INE, GFEX). "
    "Given OHLCV price history for a single futures contract, decide the desired "
    "directional position: LONG, SHORT, or FLAT.\n\n"
    "Reply with STRICT JSON only, no prose:\n"
    '{"signal": 1|0|-1, "confidence": 0.0-1.0, "reason": "<=300 chars", '
    '"target_price": <float>, "stop_loss": <float>, "take_profit": <float>}\n\n'
    "signal: 1 = go LONG (buy to open), 0 = FLAT/neutral, -1 = go SHORT (sell to open).\n\n"
    "Price target rules:\n"
    "- target_price: best estimate for next bar close based on technicals.\n"
    "- Use pivot points, ATR, Bollinger Bands to estimate.\n"
    "- stop_loss: entry ± 1.5×ATR (direction-dependent).\n"
    "- take_profit: entry ± 2×ATR (direction-dependent).\n"
    "- If signal=0: target_price=current, stop_loss=0, take_profit=0.\n\n"
    "Decision framework for futures:\n"
    "- Trend (40%): SMA alignment across 5/10/20/60 period. Above all = bullish; below all = bearish.\n"
    "- Volume/OI (20%): Rising OI + rising price = strong trend. Falling OI + rising price = weak.\n"
    "- Volatility regime (15%): High vol → smaller size. Night session vol often differs from day.\n"
    "- Term structure (15%): Backwardation (spot > futures) → supply tightness, bullish bias.\n"
    "  Contango (futures > spot) → oversupply, bearish bias.\n"
    "- Key levels (10%): Recent swing highs/lows, round numbers, pre-market gaps.\n"
    "- CONTEXT: domestic futures have T+0, bidirectional, 5-20× leverage.\n"
    "  Always prefer a tight stop. Confidence below 0.6 = flat.\n"
    "- DOMINANT CONTRACT: check the current most-active contract month.\n"
    "- NIGHT SESSION: if current time is after 15:00, consider night session movements.\n"
    "- EXPIRY: if within 10 days of delivery month, reduce position, avoid new entries.\n"
    "- NEWS: 如果提供了近期新闻，分析其对供需的边际影响。\n"
    "  高影响新闻(🔥) > 中等(📌) > 低。库存/天气/宏观政策优先考虑。\n\n"
    "CRITICAL ANTI-PATTERNS (from backtesting, MUST FOLLOW):\n"
    "- OVERSOLD BOUNCE: If price >5% below SMA10, do NOT chase shorts. "
    "Oversold bounces are common. Reduce SHORT confidence by 0.15.\n"
    "- NEWS vs TECHNICALS: If bullish news (Fed pause, supply cuts) conflicts with "
    "bearish price action (below all MAs), TECHNICALS WIN. Reduce confidence by 0.2.\n"
    "- ENERGY TRAP: For SC/FU/MA/TA/SA, do not open positions right before EIA data.\n"
    "- HIGH CONFIDENCE CAP: When 5-bar return >2% AND all MAs aligned, cap confidence at 0.7. "
    "Strong trends are reversal-prone.\n"
    "- TREND EXHAUSTION: Declining volume + new price extremes = weakening trend. "
    "Do not give high confidence to trend-following."
)


def _build_futures_prompt(
    prices: pd.DataFrame,
    code: str,
    lookback: int = 60,
    news_text: str = "",
    extra_ctx: str = "",
) -> str:
    """构建期货专用用户 prompt。"""
    if prices is None or prices.empty or len(prices) < 2:
        raise ValueError(f"价格数据不足: {code} 需要至少2根K线，实际 {0 if prices is None else len(prices)} 根")
    bars = prices.tail(lookback)
    closes = bars["close"].astype(float)
    opens = bars["open"].astype(float) if "open" in bars.columns else closes
    highs = bars["high"].astype(float) if "high" in bars.columns else closes
    lows = bars["low"].astype(float) if "low" in bars.columns else closes
    volumes = bars["volume"].astype(float) if "volume" in bars.columns else pd.Series(0, index=closes.index)

    spec = contract_info(code)
    last = float(closes.iloc[-1])
    prev = float(closes.iloc[-2]) if len(closes) >= 2 else last
    chg = (last / prev - 1) * 100

    # Multi-period returns
    ret_5 = (closes.iloc[-1] / closes.iloc[-6] - 1) * 100 if len(closes) >= 6 else 0.0
    ret_10 = (closes.iloc[-1] / closes.iloc[-11] - 1) * 100 if len(closes) >= 11 else 0.0
    ret_20 = (closes.iloc[-1] / closes.iloc[-21] - 1) * 100 if len(closes) >= 21 else 0.0

    # MAs
    sma5 = float(closes.tail(5).mean())
    sma10 = float(closes.tail(10).mean())
    sma20 = float(closes.tail(20).mean()) if len(closes) >= 20 else float(closes.mean())
    sma60 = float(closes.tail(60).mean()) if len(closes) >= 60 else sma20

    # Trend alignment
    if sma5 > sma10 > sma20 > sma60:
        trend = "strong_bull"
    elif sma5 < sma10 < sma20 < sma60:
        trend = "strong_bear"
    elif sma5 > sma10 > sma20:
        trend = "bullish"
    elif sma5 < sma10 < sma20:
        trend = "bearish"
    else:
        trend = "mixed"

    # Volatility
    pct = closes.pct_change().dropna()
    vol_20 = float(pct.tail(20).std() * 100) if len(pct) >= 2 else 0.0
    vol_5 = float(pct.tail(5).std() * 100) if len(pct) >= 5 else vol_20

    # Range
    recent_high = float(highs.tail(10).max())
    recent_low = float(lows.tail(10).min())
    range_pct = (recent_high / recent_low - 1) * 100 if recent_low > 0 else 0.0

    # Volume / OI trend
    vol_last = float(volumes.iloc[-1])
    vol_mean = float(volumes.tail(20).mean()) if len(volumes) >= 20 else 0
    vol_ratio = vol_last / vol_mean if vol_mean > 0 else 1.0

    # ── 高级技术指标 ──
    # RSI (14-bar)
    delta = closes.diff()
    gain = delta.clip(lower=0).tail(14)
    loss = (-delta.clip(upper=0)).tail(14)
    avg_gain = float(gain.mean()) if len(gain) >= 14 else 0
    avg_loss = float(loss.mean()) if len(loss) >= 14 else 0
    rs = avg_gain / avg_loss if avg_loss > 0 else 100
    rsi = 100 - (100 / (1 + rs))

    # Bollinger Bands (20, 2)
    bb_mid = sma20
    bb_std = float(closes.tail(20).std()) if len(closes) >= 20 else 0
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    bb_pct = (last - bb_lower) / (bb_upper - bb_lower) if bb_upper != bb_lower else 0.5

    # ATR (14-bar)
    if len(bars) >= 14:
        tr_list = []
        for i in range(-14, 0):
            h = float(highs.iloc[i])
            l = float(lows.iloc[i])
            pc = float(closes.iloc[i - 1])
            tr_list.append(max(h - l, abs(h - pc), abs(l - pc)))
        atr = sum(tr_list) / len(tr_list)
    else:
        atr = float(highs.iloc[-1] - lows.iloc[-1])

    # MACD (12, 26, 9)
    if len(closes) >= 26:
        ema12 = float(closes.ewm(span=12).mean().iloc[-1])
        ema26 = float(closes.ewm(span=26).mean().iloc[-1])
        macd_line = ema12 - ema26
        signal_line = float(closes.ewm(span=12).mean().subtract(closes.ewm(span=26).mean()).ewm(span=9).mean().iloc[-1])
        macd_hist = macd_line - signal_line
    else:
        macd_line = signal_line = macd_hist = 0

    # Pivot Points (classic)
    pivot_h = float(highs.iloc[-1])
    pivot_l = float(lows.iloc[-1])
    pivot_c = last
    pivot = (pivot_h + pivot_l + pivot_c) / 3
    r1 = 2 * pivot - pivot_l
    s1 = 2 * pivot - pivot_h
    r2 = pivot + (pivot_h - pivot_l)
    s2 = pivot - (pivot_h - pivot_l)

    # Session info
    session = session_label()
    is_night = trading_session() == "night"

    # Contract info
    dom = dominant_contract(code)
    spec_name = spec.name if spec else code
    margin = spec.calc_margin(last, 1) if spec else 0.0
    tick_val = spec.tick_value_per_lot if spec else 0.0

    lines = [
        f"FUTURES: {spec_name} ({code}) — dominant contract: {dom}",
        f"Exchange: {spec.exchange if spec else '?'} | "
        f"Contract size: {spec.contract_size if spec else '?'} | "
        f"Tick value: ¥{tick_val:.0f} | Margin/lot: ¥{margin:,.0f}",
        f"Current session: {session} {'🌙 NIGHT' if is_night else ''}",
        f"Latest: {last:.2f} ({chg:+.2f}% from prev) | "
        f"High: {recent_high:.2f} Low: {recent_low:.2f} | "
        f"Range: {range_pct:.1f}%",
        f"Returns: 5bar={ret_5:+.2f}% 10bar={ret_10:+.2f}% 20bar={ret_20:+.2f}%",
        f"MAs: SMA5={sma5:.2f} SMA10={sma10:.2f} SMA20={sma20:.2f} SMA60={sma60:.2f}",
        f"Trend: {trend} | Vol(20d): {vol_20:.2f}% (5d: {vol_5:.2f}%)",
        f"RSI(14): {rsi:.1f} {'⚠️OVERBOUGHT' if rsi > 70 else '⚠️OVERSOLD' if rsi < 30 else ''}",
        f"Bollinger(20,2): Upper={bb_upper:.2f} Mid={bb_mid:.2f} Lower={bb_lower:.2f} | %B={bb_pct:.2f}",
        f"ATR(14): {atr:.2f} ({atr / last * 100:.2f}%)",
        f"MACD: Line={macd_line:.2f} Signal={signal_line:.2f} Hist={macd_hist:.2f}",
        f"Pivot: R2={r2:.2f} R1={r1:.2f} P={pivot:.2f} S1={s1:.2f} S2={s2:.2f}",
        f"Volume: last={vol_last:.0f} mean20={vol_mean:.0f} ratio={vol_ratio:.1f}x",
        f"Recent closes (10): {[round(c, 2) for c in closes.tail(10).tolist()]}",
    ]

    # 超买超卖 + 趋势耗尽警告
    dist_from_sma10 = (last / sma10 - 1) * 100 if sma10 > 0 else 0.0
    if abs(dist_from_sma10) > 5:
        direction = "BELOW" if dist_from_sma10 < 0 else "ABOVE"
        lines.append(
            f"⚠️ OVEREXTENDED: Price {abs(dist_from_sma10):.1f}% {direction} SMA10 — "
            f"mean reversion risk HIGH. Do not chase."
        )
    if abs(ret_5) > 2:
        lines.append(f"⚠️ STRONG 5-BAR MOVE ({ret_5:+.1f}%): Trend exhaustion likely. Cap confidence at 0.7.")
    if vol_last < vol_mean * 0.7 and trend in ("strong_bull", "strong_bear"):
        lines.append(f"⚠️ VOLUME DIVERGENCE: Declining volume during {trend} — trend weakening.")

    if news_text:
        lines.append(f"\n📰 期货新闻:\n{news_text[:1200]}")
    if extra_ctx:
        lines.append(f"\n📐 技术分析补充:\n{extra_ctx}")

    return "\n".join(lines)


def _parse_futures_response(content: str) -> dict:
    """解析 LLM 的期货决策响应。"""
    data = None
    try:
        data = json.loads(content)
    except Exception:
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
            except Exception:
                data = None
    if not isinstance(data, dict):
        low = content.lower()
        sig = 1 if "long" in low else (-1 if "short" in low else 0)
        return {"signal": sig, "confidence": 0.3, "reason": content.strip()[:200]}

    raw = data.get("signal", 0)
    if isinstance(raw, str):
        low = raw.strip().lower()
        sig = 1 if low in ("1", "buy", "long") else (-1 if low in ("-1", "sell", "short", "exit") else 0)
    else:
        try:
            sig = int(raw)
        except Exception:
            sig = 0
    sig = max(-1, min(1, sig))
    try:
        conf = float(data.get("confidence", 0.5))
    except Exception:
        conf = 0.5

    return {
        "signal": sig,
        "confidence": max(0.0, min(1.0, conf)),
        "reason": str(data.get("reason", ""))[:300],
        "target_price": data.get("target_price"),
        "stop_loss": data.get("stop_loss"),
        "take_profit": data.get("take_profit"),
    }


def futures_llm_decision(
    prices: pd.DataFrame,
    code: str,
    llm_cfg,  # LLMConfig from ai.llm
    news_text: str = "",
    extra_ctx: str = "",
) -> dict:
    """调用 LLM 获取期货交易决策。

    Args:
        prices: OHLCV DataFrame
        code: 品种代码 (RB, SC, IF...)
        llm_cfg: LLMConfig 实例 (已 resolve)
        news_text: 相关新闻文本
        extra_ctx: 额外上下文 (如卦象、基差信息)

    Returns:
        {"signal": -1/0/1, "confidence": 0-1, "reason": str, "provider": str, "model": str}
    """
    if llm_cfg.api_key is None:
        try:
            llm_cfg.resolve()
        except Exception:
            pass

    if not llm_cfg.api_key:
        raise ValueError(
            f"Missing API key for LLM provider {llm_cfg.provider!r}. Set DEEPSEEK_API_KEY or OPENAI_API_KEY."
        )

    try:
        import requests
    except ImportError:
        raise ImportError("`requests` is required. pip install requests")

    body = {
        "model": llm_cfg.model,
        "messages": [
            {"role": "system", "content": _FUTURES_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _build_futures_prompt(
                    prices,
                    code,
                    llm_cfg.lookback,
                    news_text,
                    extra_ctx,
                ),
            },
        ],
        "temperature": llm_cfg.temperature,
    }
    headers = {"Authorization": f"Bearer {llm_cfg.api_key}", "Content-Type": "application/json"}
    resp = requests.post(
        f"{llm_cfg.base_url.rstrip('/')}/chat/completions",
        json=body,
        headers=headers,
        timeout=llm_cfg.timeout,
    )
    resp.raise_for_status()
    payload = resp.json()
    content = payload["choices"][0]["message"]["content"]

    out = _parse_futures_response(content)
    out["provider"] = llm_cfg.provider
    out["model"] = llm_cfg.model
    return out
