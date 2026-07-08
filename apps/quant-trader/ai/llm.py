"""LLM trading-brain adapter for DeepSeek and OpenAI/GPT.

Both providers speak the OpenAI Chat Completions protocol, so a single client
with per-provider presets covers both. The adapter turns recent price bars
(plus optional news text) into a structured opinion: a -1/0/1 signal with a
confidence and a short reason.

⚠️  CRITICAL SAFETY RULE:
    LLM output is treated as TEXT OPINION ONLY.
    It CANNOT directly trigger broker execution.
    All BUY/SELL must go through: rule_engine + ML + signal_quality_gate.
    The `is_opinion` flag is set to True on all LLM outputs to enforce this.

Usage:
- As an AIStrategy callable:  AIStrategy(fn=llm_callable(LLMConfig(provider="deepseek", api_key=...)))
- As the "llm" strategy:      get_strategy("llm", provider="gpt", api_key=...)
- Directly:                   ask_llm(prices_df, LLMConfig(...))
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

# Auto-load .env — try python-dotenv first, fallback to manual parse
try:
    from dotenv import load_dotenv as _load_dotenv

    _load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env", override=False)
except ImportError:
    # Manual .env parse when python-dotenv not installed
    _env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if _env_path.exists():
        for _line in _env_path.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())
except Exception:
    pass

import pandas as pd

# Provider presets. DeepSeek and OpenAI/GPT are both OpenAI-compatible, so only
# the base URL, default model, and the env var for the key differ.
PROVIDERS: dict[str, dict] = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "env": "DEEPSEEK_API_KEY",
    },
    "gpt": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "env": "OPENAI_API_KEY",
    },
    "mimo": {
        "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
        "model": "mimo-v2.5",
        "env": "MIMO_API_KEY",
    },
}
# Aliases — deep-copy so resolve() on one doesn't mutate the other.
PROVIDERS["openai"] = {**PROVIDERS["gpt"]}


@dataclass
class LLMConfig:
    provider: str = "deepseek"
    api_key: str = ""
    model: str = ""  # blank -> provider default
    base_url: str = ""  # blank -> provider default
    temperature: float = 0.2
    timeout: float = 30.0
    lookback: int = 60  # number of recent bars summarized for the model

    def resolve(self) -> LLMConfig:
        """Fill blanks from the provider preset / environment."""
        preset = PROVIDERS.get((self.provider or "deepseek").lower())
        if not preset:
            raise ValueError(f"Unknown LLM provider {self.provider!r}. Options: {', '.join(sorted(PROVIDERS))}.")
        if not self.base_url:
            self.base_url = preset["base_url"]
        if not self.model:
            self.model = preset["model"]
        if not self.api_key:
            self.api_key = os.environ.get(preset["env"], "")
        return self


_SYSTEM_PROMPT = (
    "You are a disciplined quantitative trading assistant with deep market knowledge. "
    "Given multi-timeframe OHLCV price history (with volume) for a single stock, "
    "decide the desired position for the NEXT bar. Reply with STRICT JSON only, no prose:\n"
    '{"signal": 1|0|-1, "confidence": 0.0-1.0, "reason": "<=300 chars", '
    '"target_price": <float>, "stop_loss": <float>, "take_profit": <float>}\n\n'
    "signal: 1 = go long (buy), 0 = stay flat/neutral, -1 = exit or short.\n\n"
    "Price target rules:\n"
    "- target_price: your best estimate for the next bar's close, based on technicals.\n"
    "- Use pivot points, ATR, and Bollinger Bands to estimate targets.\n"
    "- stop_loss: entry price minus 1.5×ATR for longs, plus 1.5×ATR for shorts.\n"
    "- take_profit: entry price plus 2×ATR for longs, minus 2×ATR for shorts.\n"
    "- If signal=0, set target_price=current price, stop_loss=0, take_profit=0.\n\n"
    "Decision framework:\n"
    "- Trend alignment: check SMA10 vs SMA30 vs price. Price above both = bullish.\n"
    "- Momentum: accelerating/diverging returns? Check multi-period returns (5/10/20 bar).\n"
    "- RSI: >70 = overbought (bearish bias), <30 = oversold (bullish bias), 30-70 = neutral.\n"
    "- Bollinger %B: >1 = overbought, <0 = oversold, 0.5 = mid-range.\n"
    "- MACD: histogram positive and rising = bullish momentum, negative and falling = bearish.\n"
    "- Pivot Points: price near R1/R2 = resistance (bearish), near S1/S2 = support (bullish).\n"
    "- Volume: rising volume on moves confirms, declining volume = weak.\n"
    "- Volatility regime: high vol = smaller size / more conservative.\n"
    "- Mean-reversion risk: if price far from SMA10 (>2× daily vol range), a snap-back is likely.\n"
    "- Be conservative: prefer 0 (hold) when the edge is unclear, noisy, or conflicting.\n"
    "- Confidence below 0.6 = do not trade (signal 0).\n\n"
    "CRITICAL ANTI-PATTERNS (learned from backtesting):\n"
    "- OVERSOLD BOUNCE RISK: If price deviates >5% below SMA10, a snap-back is likely. "
    "Do NOT chase shorts after a large drop — reduce confidence by 0.15.\n"
    "- NEWS vs TECHNICALS CONFLICT: If bullish news (Fed pause, supply cuts) conflicts with "
    "bearish technicals (below all MAs, downtrend), TECHNICALS WIN. News is lagging; "
    "price action is truth. Reduce confidence by 0.2 when news contradicts trend.\n"
    "- HIGH CONFIDENCE REVERSAL RISK: The stronger the trend appears (>2% 5-bar move, "
    "all MAs aligned), the HIGHER the reversal probability. Cap confidence at 0.7 "
    "when 5-bar return exceeds 2σ of daily volatility.\n"
    "- EIA/EVENT TRAP: Do not open new positions in energy futures (SC/FU/MA/TA) "
    "right before EIA inventory data — wait for the data to settle.\n"
    "- TREND EXHAUSTION: If volume is declining while price makes new extremes, "
    "the trend is weakening. Do not give high confidence to trend-following signals."
)


def _sanitize_for_llm(text: str, max_len: int = 1500) -> str:
    """Remove potential prompt injection patterns from user-supplied text."""
    # Remove system instruction overrides
    text = re.sub(
        r"(?i)(ignore|forget|disregard)\s+(previous|above|all)\s+(instructions?|prompts?|rules?)",
        "[FILTERED]",
        text,
    )
    # Remove role-switching attempts
    text = re.sub(
        r"(?i)(you are now|act as|pretend to be|system:\s*)",
        "[FILTERED]",
        text,
    )
    # Remove code block injection that could override system prompt
    text = re.sub(r"```.*?```", "[FILTERED]", text, flags=re.DOTALL)
    # Limit length
    return text[:max_len]


def _build_user_prompt(prices: pd.DataFrame, lookback: int, news_text: str = "", extra_ctx: str = "") -> str:
    bars = prices.tail(lookback)
    closes = bars["close"].astype(float)
    opens = bars["open"].astype(float) if "open" in bars.columns else closes
    highs = bars["high"].astype(float) if "high" in bars.columns else closes
    lows = bars["low"].astype(float) if "low" in bars.columns else closes
    volumes = bars["volume"].astype(float) if "volume" in bars.columns else pd.Series(0, index=closes.index)

    last = float(closes.iloc[-1])
    pct = closes.pct_change().dropna()
    vol_mean = float(volumes.tail(20).mean()) if len(volumes) >= 20 else 0
    vol_last = float(volumes.iloc[-1])
    vol_ratio = vol_last / vol_mean if vol_mean > 0 else 1.0

    # Multi-timeframe returns
    ret_5 = (closes.iloc[-1] / closes.iloc[-6] - 1) * 100 if len(closes) >= 6 else 0.0
    ret_10 = (closes.iloc[-1] / closes.iloc[-11] - 1) * 100 if len(closes) >= 11 else 0.0
    ret_20 = (closes.iloc[-1] / closes.iloc[-21] - 1) * 100 if len(closes) >= 21 else 0.0

    # Moving averages
    sma5 = float(closes.tail(5).mean())
    sma10 = float(closes.tail(10).mean())
    sma20 = float(closes.tail(20).mean()) if len(closes) >= 20 else float(closes.mean())
    sma60 = float(closes.tail(60).mean()) if len(closes) >= 60 else sma20
    trend = "bullish" if sma5 > sma10 > sma20 else ("bearish" if sma5 < sma10 < sma20 else "mixed")

    # Volatility
    daily_vol = float(pct.tail(20).std() * 100) if len(pct) >= 2 else 0.0
    vol_5 = float(pct.tail(5).std() * 100) if len(pct) >= 5 else daily_vol
    vol_regime = "high" if vol_5 > daily_vol * 1.3 else ("low" if vol_5 < daily_vol * 0.7 else "normal")

    # Recent range & distance from SMA10
    recent_high = float(highs.tail(10).max())
    recent_low = float(lows.tail(10).min())
    dist_from_sma10 = (last / sma10 - 1) * 100 if sma10 > 0 else 0.0

    # Volume trend
    vol_5_avg = float(volumes.tail(5).mean())
    vol_20_avg = float(volumes.tail(20).mean()) if len(volumes) >= 20 else vol_5_avg
    vol_trend = (
        "rising" if vol_5_avg > vol_20_avg * 1.15 else ("falling" if vol_5_avg < vol_20_avg * 0.85 else "steady")
    )

    recent = [round(c, 2) for c in closes.tail(10).tolist()]

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

    # Swing High/Low (20-bar)
    swing_high = float(highs.tail(20).max())
    swing_low = float(lows.tail(20).min())

    # Price position in range
    range_pos = (last - swing_low) / (swing_high - swing_low) * 100 if swing_high != swing_low else 50

    lines = [
        f"SYMBOL price data (last {lookback} bars, {len(bars)} total):",
        f"Latest close: {last:.2f}",
        f"Multi-period returns: 5-bar={ret_5:+.2f}% 10-bar={ret_10:+.2f}% 20-bar={ret_20:+.2f}%",
        f"Moving averages: SMA5={sma5:.2f} SMA10={sma10:.2f} SMA20={sma20:.2f} SMA60={sma60:.2f}",
        f"Trend alignment: {trend} (SMA5 {'>' if sma5 > sma10 else '<'}= SMA10 {'>' if sma10 > sma20 else '<'}= SMA20)",
        f"Price vs SMA10: {dist_from_sma10:+.2f}% (deviation)",
        f"RSI(14): {rsi:.1f} {'⚠️ OVERBOUGHT' if rsi > 70 else '⚠️ OVERSOLD' if rsi < 30 else ''}",
        f"Bollinger(20,2): Upper={bb_upper:.2f} Mid={bb_mid:.2f} Lower={bb_lower:.2f} | %B={bb_pct:.2f}",
        f"ATR(14): {atr:.2f} ({atr / last * 100:.2f}% of price)",
        f"MACD: Line={macd_line:.2f} Signal={signal_line:.2f} Hist={macd_hist:.2f}",
        f"Pivot Points: R2={r2:.2f} R1={r1:.2f} P={pivot:.2f} S1={s1:.2f} S2={s2:.2f}",
        f"Swing High/Low (20-bar): {swing_high:.2f} / {swing_low:.2f} | Position: {range_pos:.0f}%",
        f"Daily volatility: {daily_vol:.2f}% (20-bar), last 5 bars: {vol_5:.2f}% → regime: {vol_regime}",
        f"Recent range (10-bar): {recent_low:.2f} – {recent_high:.2f}",
        f"Volume: last={vol_last:.0f} mean(20)={vol_mean:.0f} ratio={vol_ratio:.1f}x trend={vol_trend}",
        f"Last 10 closes: {recent}",
    ]

    # 超买超卖警告
    if abs(dist_from_sma10) > 5:
        direction = "BELOW" if dist_from_sma10 < 0 else "ABOVE"
        lines.append(
            f"⚠️ OVEREXTENDED: Price is {abs(dist_from_sma10):.1f}% {direction} SMA10 — "
            f"mean reversion risk is HIGH. Do not chase the move."
        )
    if abs(ret_5) > 2:
        lines.append(
            f"⚠️ STRONG 5-BAR MOVE ({ret_5:+.1f}%): Trend exhaustion likely. "
            f"Cap confidence at 0.7 — reversal probability is elevated."
        )
    if vol_trend == "falling" and (trend == "bullish" or trend == "bearish"):
        lines.append(
            f"⚠️ DIVERGENCE: Volume declining during {trend} trend — trend may be weakening. Reduce confidence."
        )
    if news_text:
        lines.append(f"\nNews headlines:\n{_sanitize_for_llm(news_text)}")
    if extra_ctx:
        lines.append(f"\n辅助上下文:\n{extra_ctx}")
    return "\n".join(lines)


def _parse_decision(content: str) -> dict:
    """Extract {signal, confidence, reason} from the model's reply."""
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
        # Fall back to keyword scan — use word boundaries to avoid false positives.
        low = content.lower()
        # Negation patterns: "do not buy", "don't buy", "avoid buying" → not a buy signal
        neg = re.search(r"(?:do\s+not|don'?t|avoid|never|not)\s+(?:buy|long|go\s+long)", low)
        if neg:
            sig = 0  # treat negated action as HOLD
        elif re.search(r"\bbuy\b|\blong\b|\bgo\s+long\b|\bbuying\b", low):
            sig = 1
        elif re.search(r"\bsell\b|\bshort\b|\bgo\s+short\b|\bexit\b|\bselling\b|\bshorting\b", low):
            sig = -1
        else:
            sig = 0
        return {
            "signal": sig,
            "confidence": 0.0,
            "reason": f"[keyword-fallback] {content.strip()[:200]}",
            "is_opinion": True,
            "source": "llm_text_opinion",
        }

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
    out = {
        "signal": sig,
        "confidence": max(0.0, min(1.0, conf)),
        "reason": str(data.get("reason", ""))[:300],
        "target_price": data.get("target_price"),
        "stop_loss": data.get("stop_loss"),
        "take_profit": data.get("take_profit"),
        # ═══════════════════════════════════════════════════════════
        # 安全标记: LLM 输出仅为文本观点，不可直接用于下单
        # ═══════════════════════════════════════════════════════════
        "is_opinion": True,
        "source": "llm_text_opinion",
    }
    return out


def _chat_completion(cfg: LLMConfig, messages: list[dict], max_tokens: int = 512) -> str:
    """Low-level chat-completions call with retry; returns the raw content string.

    Retries on transient errors (429/5xx/timeout/connection) with exponential
    backoff; non-retryable errors propagate immediately. cfg must be resolved.
    """
    import time as _time

    if not cfg.api_key:
        raise ValueError(
            f"Missing API key for provider {cfg.provider!r}. Set it in settings or env "
            f"{PROVIDERS[cfg.provider.lower()]['env']}."
        )
    try:
        import requests
    except ImportError as exc:  # pragma: no cover
        raise ImportError("`requests` is required for the LLM adapter. pip install requests") from exc

    body = {
        "model": cfg.model,
        "messages": messages,
        "temperature": cfg.temperature,
        "max_tokens": max_tokens,  # limit output to avoid timeout
    }
    headers = {"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"}

    # Retry with exponential backoff on transient errors
    max_retries = 3
    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = requests.post(
                f"{cfg.base_url.rstrip('/')}/chat/completions",
                json=body,
                headers=headers,
                timeout=cfg.timeout,
            )
            # Rate limit or server error — retry (保留原始异常类型, 耗尽后透传)
            if resp.status_code in (429, 500, 502, 503, 504):
                retry_after = resp.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else min(2**attempt * 2, 30)
                _time.sleep(wait)
                last_err = requests.exceptions.HTTPError(
                    f"HTTP {resp.status_code}: {resp.text[:200]}", response=resp
                )
                continue
            resp.raise_for_status()
            payload = resp.json()
            return str(payload["choices"][0]["message"]["content"])
        except requests.exceptions.Timeout as e:
            wait = min(2**attempt * 3, 30)
            _time.sleep(wait)
            last_err = e
            continue
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.ChunkedEncodingError,
            requests.exceptions.ContentDecodingError,
        ) as e:
            wait = min(2**attempt * 5, 60)
            _time.sleep(wait)
            last_err = e
            continue
        except Exception:
            # Non-retryable error (e.g. JSON parse, missing key)
            raise

    # 重试耗尽: 透传最后一次原始异常 (保留 HTTPError/Timeout/ConnectionError 类型供调用方区分)
    if last_err is None:  # pragma: no cover — 理论不可达 (每条重试路径都记录了异常)
        raise RuntimeError("LLM request failed after retries with no recorded error")
    raise last_err


def ask_llm(prices: pd.DataFrame, cfg: LLMConfig, news_text: str = "", extra_ctx: str = "") -> dict:
    """Call the configured LLM for a trading decision on the latest bar.

    Retries on transient errors (429/5xx) with exponential backoff.
    Shrinks input if token count is likely too large.
    """
    cfg = cfg.resolve()

    # Auto-shrink lookback if dataset is large (avoids token overflow)
    effective_lookback = cfg.lookback
    if len(prices) > effective_lookback:
        pass  # normal — _build_user_prompt tails to lookback
    # If user passed a huge lookback, cap it
    if effective_lookback > 90:
        effective_lookback = 90

    user_prompt = _build_user_prompt(prices, effective_lookback, news_text, extra_ctx)

    # Estimate tokens: rough ~4 chars per token, limit to ~6000 tokens (~24K chars)
    if len(user_prompt) > 24000:
        # Truncate news and extra context first
        news_text = news_text[:800] if news_text else ""
        extra_ctx = extra_ctx[:500] if extra_ctx else ""
        user_prompt = _build_user_prompt(prices, min(effective_lookback, 40), news_text, extra_ctx)

    content = _chat_completion(
        cfg,
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    out = _parse_decision(content)
    out["provider"] = cfg.provider
    out["model"] = cfg.model
    return out


def ask_llm_text(prompt: str, cfg: LLMConfig, system: str = "", max_tokens: int = 1024) -> str:
    """General-purpose free-form LLM Q&A — returns the raw text reply.

    与 ask_llm 的区别: 不构造行情 prompt、不解析交易信号 JSON, 适用于
    自由研判/文本分析场景 (如 analysis.predictor.free_predict)。
    """
    cfg = cfg.resolve()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return _chat_completion(cfg, messages, max_tokens=max_tokens)


def llm_callable(cfg: LLMConfig, news_text: str = ""):
    """Return a function compatible with AIStrategy(fn=...): prices -> last-bar signal."""

    def _fn(prices: pd.DataFrame):
        from ..strategy.base import Signal

        target = pd.Series(int(Signal.HOLD), index=prices.index, dtype="int64")
        try:
            target.iloc[-1] = int(ask_llm(prices, cfg, news_text)["signal"])
        except Exception:
            pass  # on any failure stay flat rather than trade on noise
        return target

    return _fn
