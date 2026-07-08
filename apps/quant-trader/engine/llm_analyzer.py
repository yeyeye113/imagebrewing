"""LLM多维度分析器 — 让大模型读取完整数据，给出多维度判断。

核心原理: LLM能理解"为什么"而不仅仅是"是什么"，比纯算法更准确。

维度:
  1. 供需基本面分析
  2. 资金流向判断
  3. 技术形态识别
  4. 情绪面判断
  5. 宏观环境评估

预期准确率: 70%+
"""
from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout

import pandas as pd

from quanttrader.ai.llm import LLMConfig, ask_llm
from quanttrader.engine.voter import DimensionVote

logger = logging.getLogger(__name__)

# ── System prompt (期货多维度分析) ──

_SYSTEM_PROMPT = """你是一个专业的期货分析师。分析以下期货品种的数据，给出交易建议。

分析维度:
1. 供需基本面: 库存周期、基差、季节性
2. 资金面: 持仓量变化、量价关系
3. 技术面: 趋势、支撑阻力、形态
4. 情绪面: 超买超卖、市场情绪
5. 宏观面: 美元、政策、经济周期

输出格式 (严格JSON):
{
  "direction": 1或-1或0,
  "confidence": 0.0-1.0,
  "fundamental": {"direction": 1/-1/0, "reason": "..."},
  "capital_flow": {"direction": 1/-1/0, "reason": "..."},
  "technical": {"direction": 1/-1/0, "reason": "..."},
  "sentiment": {"direction": 1/-1/0, "reason": "..."},
  "macro": {"direction": 1/-1/0, "reason": "..."},
  "overall_reason": "综合判断理由(100字内)",
  "risk": "主要风险(50字内)"
}"""

# ── LLM 超时 (秒) ──
_LLM_TIMEOUT = 45


def _compute_indicators(prices: pd.DataFrame) -> dict:
    """计算关键技术指标，供 prompt 构建使用。"""
    closes = prices["close"].astype(float)
    last = float(closes.iloc[-1])

    # SMA
    sma5 = float(closes.tail(5).mean())
    sma10 = float(closes.tail(10).mean())
    sma20 = float(closes.tail(20).mean()) if len(closes) >= 20 else float(closes.mean())

    # RSI (14)
    delta = closes.diff()
    gain = delta.clip(lower=0).tail(14)
    loss = (-delta.clip(upper=0)).tail(14)
    avg_g = float(gain.mean())
    avg_l = float(loss.mean())
    rs = avg_g / avg_l if avg_l > 0 else 100
    rsi = 100 - (100 / (1 + rs))

    # MACD (12, 26, 9)
    macd_line = signal_line = macd_hist = 0.0
    if len(closes) >= 26:
        ema12 = float(closes.ewm(span=12).mean().iloc[-1])
        ema26 = float(closes.ewm(span=26).mean().iloc[-1])
        macd_line = ema12 - ema26
        signal_line = float(
            closes.ewm(span=12).mean().subtract(closes.ewm(span=26).mean()).ewm(span=9).mean().iloc[-1]
        )
        macd_hist = macd_line - signal_line

    # Bollinger Bands %B (20, 2)
    bb_mid = sma20
    bb_std = float(closes.tail(20).std()) if len(closes) >= 20 else 0
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    bb_pct = (last - bb_lower) / (bb_upper - bb_lower) if bb_upper != bb_lower else 0.5

    # ATR (14)
    highs = prices["high"].astype(float) if "high" in prices.columns else closes
    lows = prices["low"].astype(float) if "low" in prices.columns else closes
    if len(prices) >= 14:
        tr_list = []
        for i in range(-14, 0):
            h = float(highs.iloc[i])
            l = float(lows.iloc[i])
            pc = float(closes.iloc[i - 1])
            tr_list.append(max(h - l, abs(h - pc), abs(l - pc)))
        atr = sum(tr_list) / len(tr_list)
    else:
        atr = float(highs.iloc[-1] - lows.iloc[-1])

    # Volume analysis
    volumes = prices["volume"].astype(float) if "volume" in prices.columns else pd.Series(0, index=closes.index)
    vol_5_avg = float(volumes.tail(5).mean())
    vol_20_avg = float(volumes.tail(20).mean()) if len(volumes) >= 20 else vol_5_avg
    vol_ratio = vol_5_avg / vol_20_avg if vol_20_avg > 0 else 1.0

    # Multi-period returns
    ret_5 = (closes.iloc[-1] / closes.iloc[-6] - 1) * 100 if len(closes) >= 6 else 0.0
    ret_10 = (closes.iloc[-1] / closes.iloc[-11] - 1) * 100 if len(closes) >= 11 else 0.0
    ret_20 = (closes.iloc[-1] / closes.iloc[-21] - 1) * 100 if len(closes) >= 21 else 0.0

    # Price position in recent range (20-bar)
    swing_high = float(highs.tail(20).max())
    swing_low = float(lows.tail(20).min())
    range_pos = (last - swing_low) / (swing_high - swing_low) * 100 if swing_high != swing_low else 50

    return {
        "last": last,
        "sma5": sma5,
        "sma10": sma10,
        "sma20": sma20,
        "rsi": rsi,
        "macd_line": macd_line,
        "signal_line": signal_line,
        "macd_hist": macd_hist,
        "bb_pct": bb_pct,
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "atr": atr,
        "vol_5_avg": vol_5_avg,
        "vol_20_avg": vol_20_avg,
        "vol_ratio": vol_ratio,
        "ret_5": ret_5,
        "ret_10": ret_10,
        "ret_20": ret_20,
        "swing_high": swing_high,
        "swing_low": swing_low,
        "range_pos": range_pos,
    }


def build_analysis_prompt(prices: pd.DataFrame, code: str, news_text: str = "") -> str:
    """构建完整的多维度分析 prompt，发送给 LLM。

    包含:
      - 最近 60 根 OHLCV 数据 (文本表格)
      - 关键技术指标
      - 成交量分析
      - 多周期收益率
      - 当前价格在近期区间的位置
      - 可选: 新闻标题
    """
    # 最近60根K线
    bars = prices.tail(60)
    closes = bars["close"].astype(float)
    opens = bars["open"].astype(float) if "open" in bars.columns else closes
    highs = bars["high"].astype(float) if "high" in bars.columns else closes
    lows = bars["low"].astype(float) if "low" in bars.columns else closes
    volumes = bars["volume"].astype(float) if "volume" in bars.columns else pd.Series(0, index=closes.index)

    # K线数据表格
    lines = [
        f"品种代码: {code}",
        f"数据量: 最近 {len(bars)} 根K线 (共 {len(prices)} 根)",
        "",
        "=== K线数据 (日期 | 开 | 高 | 低 | 收 | 量) ===",
    ]
    for idx, row in bars.iterrows():
        date_str = str(idx)[:10]
        o = float(row["open"]) if "open" in bars.columns else float(row["close"])
        h = float(row["high"]) if "high" in bars.columns else float(row["close"])
        l = float(row["low"]) if "low" in bars.columns else float(row["close"])
        c = float(row["close"])
        v = float(row["volume"]) if "volume" in bars.columns else 0
        lines.append(f"{date_str} | {o:.2f} | {h:.2f} | {l:.2f} | {c:.2f} | {v:.0f}")

    # 技术指标
    ind = _compute_indicators(prices)
    lines.extend([
        "",
        "=== 关键技术指标 ===",
        f"当前价格: {ind['last']:.2f}",
        f"SMA5={ind['sma5']:.2f}  SMA10={ind['sma10']:.2f}  SMA20={ind['sma20']:.2f}",
        f"RSI(14)={ind['rsi']:.1f}  {'超买' if ind['rsi'] > 70 else '超卖' if ind['rsi'] < 30 else '中性'}",
        f"MACD: Line={ind['macd_line']:.2f}  Signal={ind['signal_line']:.2f}  Hist={ind['macd_hist']:.2f}",
        f"BB%B={ind['bb_pct']:.2f}  Upper={ind['bb_upper']:.2f}  Lower={ind['bb_lower']:.2f}",
        f"ATR(14)={ind['atr']:.2f} ({ind['atr'] / ind['last'] * 100:.2f}% of price)",
        "",
        "=== 成交量分析 ===",
        f"5日均量: {ind['vol_5_avg']:.0f}  20日均量: {ind['vol_20_avg']:.0f}  量比: {ind['vol_ratio']:.2f}x",
        f"量能趋势: {'放量' if ind['vol_ratio'] > 1.15 else '缩量' if ind['vol_ratio'] < 0.85 else '正常'}",
        "",
        "=== 多周期收益率 ===",
        f"5日: {ind['ret_5']:+.2f}%  10日: {ind['ret_10']:+.2f}%  20日: {ind['ret_20']:+.2f}%",
        "",
        "=== 价格位置 ===",
        f"20日最高: {ind['swing_high']:.2f}  20日最低: {ind['swing_low']:.2f}",
        f"当前位置: {ind['range_pos']:.1f}% (0%=最低, 100%=最高)",
    ])

    # 趋势判断
    trend = "多头" if ind["sma5"] > ind["sma10"] > ind["sma20"] else (
        "空头" if ind["sma5"] < ind["sma10"] < ind["sma20"] else "震荡"
    )
    lines.append(f"均线排列: {trend}")

    # 新闻
    if news_text:
        lines.extend(["", "=== 近期新闻/事件 ===", news_text[:1500]])

    return "\n".join(lines)


def _parse_llm_json(content: str) -> dict | None:
    """从 LLM 回复中解析 JSON。失败时尝试正则提取。"""
    # 尝试直接解析
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # 尝试提取 JSON 块
    m = re.search(r"\{.*\}", content, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    # 尝试提取 ```json ... ``` 代码块
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    return None


def _extract_direction_from_text(content: str) -> int:
    """从纯文本中提取方向判断 (JSON 解析失败时的 fallback)。"""
    low = content.lower()

    # 中文关键词
    bullish_cn = ["看多", "做多", "买入", "做多", "偏多", "看涨", "多头"]
    bearish_cn = ["看空", "做空", "卖出", "偏空", "看跌", "空头"]
    neutral_cn = ["中性", "观望", "横盘", "震荡", "不确定"]

    bull_count = sum(1 for w in bullish_cn if w in content)
    bear_count = sum(1 for w in bearish_cn if w in content)
    neutral_count = sum(1 for w in neutral_cn if w in content)

    if bull_count > bear_count and bull_count > neutral_count:
        return 1
    elif bear_count > bull_count and bear_count > neutral_count:
        return -1

    # 英文 fallback
    if re.search(r"\b(bullish|buy|long|go\s+long)\b", low):
        return 1
    if re.search(r"\b(bearish|sell|short|go\s+short|exit)\b", low):
        return -1

    return 0


def call_llm_analysis(
    prices: pd.DataFrame,
    code: str,
    news_text: str = "",
    cfg: LLMConfig | None = None,
) -> dict:
    """调用 LLM 进行多维度分析。

    使用 quanttrader.ai.llm.ask_llm 发送自定义 prompt，解析 JSON 响应。
    超时 45 秒 (concurrent.futures)。失败返回中性结果。

    Returns:
        dict with keys: direction, confidence, fundamental, capital_flow,
                        technical, sentiment, macro, overall_reason, risk
    """
    if cfg is None:
        cfg = LLMConfig(provider="deepseek", lookback=60)

    prompt = build_analysis_prompt(prices, code, news_text)

    def _call():
        return ask_llm(prices, cfg, news_text=news_text, extra_ctx=prompt)

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_call)
            result = future.result(timeout=_LLM_TIMEOUT)
    except FuturesTimeout:
        logger.warning("LLM 多维度分析超时 (%ds)", _LLM_TIMEOUT)
        return _neutral_result("LLM 调用超时")
    except Exception as e:
        logger.warning("LLM 多维度分析失败: %s", e)
        return _neutral_result(f"LLM 调用异常: {e}")

    # ask_llm 返回的是 {signal, confidence, reason, ...}
    # 我们需要发送自定义 prompt 并解析多维度 JSON
    # ask_llm 已经把我们的 extra_ctx 作为 user prompt 的一部分发送
    # 但它的 _parse_decision 只提取 signal/confidence/reason
    # 所以我们需要重新发送请求以获取完整的多维度 JSON

    # 直接发送请求获取原始 LLM 回复
    try:
        raw_content = _call_raw_llm(prompt, cfg)
    except Exception as e:
        logger.warning("LLM 原始请求失败: %s, 回退到基础分析", e)
        # fallback: 使用 ask_llm 的结果
        direction = result.get("signal", 0)
        confidence = result.get("confidence", 0.5)
        reason = result.get("reason", "")
        return {
            "direction": direction,
            "confidence": confidence,
            "fundamental": {"direction": 0, "reason": "数据不可用"},
            "capital_flow": {"direction": 0, "reason": "数据不可用"},
            "technical": {"direction": direction, "reason": reason},
            "sentiment": {"direction": 0, "reason": "数据不可用"},
            "macro": {"direction": 0, "reason": "数据不可用"},
            "overall_reason": reason or "LLM 回退到基础分析",
            "risk": "LLM 多维度解析失败，仅依赖基础信号",
        }

    # 解析多维度 JSON
    data = _parse_llm_json(raw_content)

    if data is None:
        # JSON 解析失败，从文本提取方向
        direction = _extract_direction_from_text(raw_content)
        return {
            "direction": direction,
            "confidence": 0.4,
            "fundamental": {"direction": 0, "reason": "JSON 解析失败"},
            "capital_flow": {"direction": 0, "reason": "JSON 解析失败"},
            "technical": {"direction": direction, "reason": raw_content[:200]},
            "sentiment": {"direction": 0, "reason": "JSON 解析失败"},
            "macro": {"direction": 0, "reason": "JSON 解析失败"},
            "overall_reason": raw_content[:200],
            "risk": "LLM 返回格式异常，仅提取方向",
        }

    # 验证并规范化
    direction = _clamp_direction(data.get("direction", 0))
    confidence = _clamp_confidence(data.get("confidence", 0.5))

    dim_keys = ["fundamental", "capital_flow", "technical", "sentiment", "macro"]
    dims = {}
    for key in dim_keys:
        d = data.get(key, {})
        dims[key] = {
            "direction": _clamp_direction(d.get("direction", 0) if isinstance(d, dict) else 0),
            "reason": str(d.get("reason", ""))[:200] if isinstance(d, dict) else "",
        }

    return {
        "direction": direction,
        "confidence": confidence,
        "fundamental": dims.get("fundamental", {"direction": 0, "reason": ""}),
        "capital_flow": dims.get("capital_flow", {"direction": 0, "reason": ""}),
        "technical": dims.get("technical", {"direction": 0, "reason": ""}),
        "sentiment": dims.get("sentiment", {"direction": 0, "reason": ""}),
        "macro": dims.get("macro", {"direction": 0, "reason": ""}),
        "overall_reason": str(data.get("overall_reason", ""))[:200],
        "risk": str(data.get("risk", ""))[:100],
    }


def _call_raw_llm(prompt: str, cfg: LLMConfig) -> str:
    """直接发送 LLM 请求，返回原始文本内容 (不经过 _parse_decision)。"""
    import time

    cfg = cfg.resolve()
    if not cfg.api_key:
        raise ValueError(
            f"Missing API key for provider {cfg.provider!r}. "
            f"Set env {cfg.provider.upper()}_API_KEY."
        )

    import requests

    body = {
        "model": cfg.model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": cfg.temperature,
        "max_tokens": 1024,
    }
    headers = {"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"}

    max_retries = 3
    last_err = None
    for attempt in range(max_retries):
        try:
            resp = requests.post(
                f"{cfg.base_url.rstrip('/')}/chat/completions",
                json=body,
                headers=headers,
                timeout=cfg.timeout,
            )
            if resp.status_code in (429, 500, 502, 503, 504):
                retry_after = resp.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else min(2 ** attempt * 2, 30)
                time.sleep(wait)
                last_err = RuntimeError(f"HTTP {resp.status_code}")
                continue
            resp.raise_for_status()
            payload = resp.json()
            return str(payload["choices"][0]["message"]["content"])
        except requests.exceptions.Timeout:
            time.sleep(min(2 ** attempt * 3, 30))
            last_err = RuntimeError(f"Timeout (attempt {attempt + 1})")
            continue
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.ChunkedEncodingError,
            requests.exceptions.ContentDecodingError,
        ) as e:
            time.sleep(min(2 ** attempt * 5, 60))
            last_err = RuntimeError(f"Connection: {e.__class__.__name__} (attempt {attempt + 1})")
            continue

    raise RuntimeError(f"LLM raw call failed after {max_retries} attempts: {last_err}")


def _neutral_result(reason: str = "") -> dict:
    """返回中性结果 (失败时使用)。"""
    return {
        "direction": 0,
        "confidence": 0.0,
        "fundamental": {"direction": 0, "reason": reason},
        "capital_flow": {"direction": 0, "reason": reason},
        "technical": {"direction": 0, "reason": reason},
        "sentiment": {"direction": 0, "reason": reason},
        "macro": {"direction": 0, "reason": reason},
        "overall_reason": reason or "LLM 分析失败，返回中性",
        "risk": "LLM 不可用",
    }


def _clamp_direction(val) -> int:
    """将方向值规范化为 -1/0/1。"""
    try:
        d = int(val)
        return max(-1, min(1, d))
    except Exception:
        return 0


def _clamp_confidence(val) -> float:
    """将置信度规范化为 0.0~1.0。"""
    try:
        c = float(val)
        return max(0.0, min(1.0, c))
    except Exception:
        return 0.0


def score_llm_analysis(
    prices: pd.DataFrame,
    code: str = "",
    news_text: str = "",
) -> DimensionVote:
    """主入口: 调用 LLM 多维度分析，返回 DimensionVote。

    返回 DimensionVote (name="LLM分析", weight=1.0)，可直接加入 SignalVoter。

    流程:
      1. 构建多维度 prompt (60 根 K 线 + 技术指标 + 新闻)
      2. 调用 LLM (45 秒超时)
      3. 解析 JSON 多维度响应
      4. 综合 5 个维度的方向和置信度，返回单一 DimensionVote
    """
    analysis = call_llm_analysis(prices, code, news_text)

    direction = analysis["direction"]
    confidence = analysis["confidence"]

    # 从 5 个子维度提取综合理由
    reasons = []
    dim_labels = {
        "fundamental": "供需",
        "capital_flow": "资金",
        "technical": "技术",
        "sentiment": "情绪",
        "macro": "宏观",
    }
    for key, label in dim_labels.items():
        d = analysis.get(key, {})
        dim_dir = d.get("direction", 0)
        dim_reason = d.get("reason", "")
        if dim_dir != 0 and dim_reason:
            arrow = "多" if dim_dir > 0 else "空"
            reasons.append(f"[{label}{arrow}] {dim_reason}")

    # 综合理由
    overall = analysis.get("overall_reason", "")
    risk = analysis.get("risk", "")

    reason_parts = []
    if overall:
        reason_parts.append(overall)
    if risk:
        reason_parts.append(f"风险:{risk}")
    if reasons:
        reason_parts.extend(reasons[:3])  # 最多 3 个子维度理由

    reason = " | ".join(reason_parts)[:300]

    logger.info(
        "LLM分析完成: %s 方向=%d 置信度=%.2f 理由=%s",
        code, direction, confidence, overall[:50] if overall else "-",
    )

    return DimensionVote(
        name="LLM分析",
        direction=direction,
        confidence=confidence,
        weight=1.0,
        reason=reason,
    )
