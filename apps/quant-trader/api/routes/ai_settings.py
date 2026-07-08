"""Settings & AI routes: /settings, /ai/run, /ai/llm/run."""
from __future__ import annotations

import os

from fastapi import Depends, HTTPException

from ...broker.base import get_broker
from ...strategy.base import Signal
from ..helpers import _RECENT_END, _RECENT_START, load_prices
from ..schemas import (
    AIRunRequest,
    AIRunResponse,
    LLMRunRequest,
    LLMRunResponse,
    SettingsResponse,
    SettingsUpdateRequest,
)


def register_settings_routes(app, shared, auth):
    """Register settings and AI endpoints."""

    def _positions_list():
        positions = getattr(shared.broker, "_positions", {})
        return [
            {"symbol": p.symbol, "qty": p.qty, "avg_price": p.avg_price}
            for p in positions.values()
        ]

    def _price_into_broker(symbol: str, source: str) -> None:
        if hasattr(shared.broker, "set_price"):
            try:
                prices, _ = load_prices(symbol, source, _RECENT_START, _RECENT_END, "1d")
            except Exception as e:
                raise HTTPException(status_code=502, detail=f"Data load failed: {e}")
            shared.broker.set_price(symbol, float(prices["close"].iloc[-1]))

    def _settings_payload() -> SettingsResponse:
        return SettingsResponse(
            broker=shared.broker_name,
            paper=shared.state["paper"],
            live=getattr(shared.broker, "is_live", False),
            has_broker_keys=bool(shared.state["api_key"] and shared.state["api_secret"]),
            cash=shared.state["cash"],
            ai_endpoint=shared.ai_cfg["endpoint"],
            has_ai_key=bool(shared.ai_cfg["api_key"]),
            llm_provider=shared.llm_cfg["provider"],
            llm_model=shared.llm_cfg["model"],
            has_llm_key=bool(shared.llm_cfg["api_key"]),
        )

    @app.get("/settings", response_model=SettingsResponse, dependencies=[Depends(auth)])
    def get_settings():
        return _settings_payload()

    @app.post("/settings", response_model=SettingsResponse, dependencies=[Depends(auth)])
    def update_settings(req: SettingsUpdateRequest):
        touch_broker = any(v is not None for v in (
            req.broker, req.api_key, req.api_secret, req.paper, req.allow_live, req.cash))
        if req.api_key is not None:
            shared.state["api_key"] = req.api_key
        if req.api_secret is not None:
            shared.state["api_secret"] = req.api_secret
        if req.paper is not None:
            shared.state["paper"] = req.paper
        if req.allow_live is not None:
            shared.state["allow_live"] = req.allow_live
        if req.cash is not None:
            shared.state["cash"] = float(req.cash)

        if touch_broker:
            name = (req.broker or shared.broker_name).lower()
            try:
                if name in ("paper", "cn_paper", "cn", "ashare_paper"):
                    new_broker = get_broker(name, cash=shared.state["cash"])
                else:
                    new_broker = get_broker(
                        name,
                        api_key=shared.state["api_key"], api_secret=shared.state["api_secret"],
                        paper=shared.state["paper"], allow_live=shared.state["allow_live"],
                    )
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"券商初始化失败: {e}")
            shared.broker = new_broker
            shared.broker_name = name

        if req.ai_endpoint is not None:
            shared.ai_cfg["endpoint"] = req.ai_endpoint.strip()
        if req.ai_api_key is not None:
            shared.ai_cfg["api_key"] = req.ai_api_key.strip()
        if req.llm_provider is not None:
            shared.llm_cfg["provider"] = req.llm_provider.strip().lower() or "deepseek"
        if req.llm_api_key is not None:
            shared.llm_cfg["api_key"] = req.llm_api_key.strip()
        if req.llm_model is not None:
            shared.llm_cfg["model"] = req.llm_model.strip()
        return _settings_payload()

    @app.post("/ai/run", response_model=AIRunResponse, dependencies=[Depends(auth)])
    def ai_run(req: AIRunRequest):
        if not shared.ai_cfg["endpoint"]:
            raise HTTPException(status_code=400, detail="未配置 AI 接口地址，请在设置里填写 AI Endpoint。")
        from ...strategy.ai_strategy import AIStrategy

        try:
            prices, used = load_prices(req.symbol, req.source, _RECENT_START, _RECENT_END, "1d")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"行情加载失败: {e}")
        strat = AIStrategy(endpoint=shared.ai_cfg["endpoint"], api_key=shared.ai_cfg["api_key"] or None)
        try:
            sig = int(strat.generate(prices).iloc[-1])
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"调用 AI 接口失败: {e}")

        executed = False
        if req.execute:
            if getattr(shared.broker, "is_live", False) and os.environ.get("QT_ALLOW_LIVE", "") not in ("1", "true", "yes"):
                raise HTTPException(status_code=403, detail="实盘交易未启用。设置 QT_ALLOW_LIVE=1 后才能用 AI 实盘下单。")
            _price_into_broker(req.symbol, req.source)
            pos = shared.broker.get_position(req.symbol)
            if sig == Signal.BUY and (pos is None or pos.qty == 0):
                shared.broker.submit_order(req.symbol, "buy",
                                    notional=req.notional or shared.broker.get_account().cash * 0.95, note="ai")
                executed = True
            elif sig != Signal.BUY and pos is not None and pos.qty > 0:
                shared.broker.submit_order(req.symbol, "sell", qty=pos.qty, note="ai")
                executed = True

        acct = shared.broker.get_account()
        label = {1: "BUY", 0: "HOLD", -1: "SELL/EXIT"}.get(sig, str(sig))
        return AIRunResponse(symbol=req.symbol, signal=sig, label=label, executed=executed,
                             endpoint=shared.ai_cfg["endpoint"],
                             account={"cash": acct.cash, "equity": acct.equity,
                                      "positions": _positions_list()})

    @app.post("/ai/llm/run", response_model=LLMRunResponse, dependencies=[Depends(auth)])
    def ai_llm_run(req: LLMRunRequest):
        if not shared.llm_cfg["api_key"]:
            raise HTTPException(status_code=400,
                                detail=f"未配置 {shared.llm_cfg['provider']} 的 API Key，请在设置里填写。")
        from ...ai.llm import LLMConfig, ask_llm
        from ...news import fetch_news as _fetch_news

        try:
            prices, used = load_prices(req.symbol, req.source, _RECENT_START, _RECENT_END, "1d")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"行情加载失败: {e}")

        news_text = ""
        if req.use_news:
            try:
                items, _src = _fetch_news(req.symbol, "auto", 10)
                news_text = "\n".join(f"- {getattr(it, 'title', '')}" for it in items)
            except Exception:
                news_text = ""

        cfg = LLMConfig(provider=shared.llm_cfg["provider"], api_key=shared.llm_cfg["api_key"], model=shared.llm_cfg["model"])
        try:
            decision = ask_llm(prices, cfg, news_text)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"调用大模型失败: {e}")
        sig = int(decision["signal"])

        executed = False
        if req.execute:
            if getattr(shared.broker, "is_live", False) and os.environ.get("QT_ALLOW_LIVE", "") not in ("1", "true", "yes"):
                raise HTTPException(status_code=403, detail="实盘交易未启用。设置 QT_ALLOW_LIVE=1 后才能用 AI 实盘下单。")
            _price_into_broker(req.symbol, req.source)
            pos = shared.broker.get_position(req.symbol)
            if sig == Signal.BUY and (pos is None or pos.qty == 0):
                shared.broker.submit_order(req.symbol, "buy",
                                    notional=req.notional or shared.broker.get_account().cash * 0.95, note="llm")
                executed = True
            elif sig != Signal.BUY and pos is not None and pos.qty > 0:
                shared.broker.submit_order(req.symbol, "sell", qty=pos.qty, note="llm")
                executed = True

        acct = shared.broker.get_account()
        label = {1: "BUY", 0: "HOLD", -1: "SELL/EXIT"}.get(sig, str(sig))
        return LLMRunResponse(
            symbol=req.symbol, provider=decision.get("provider", shared.llm_cfg["provider"]),
            model=decision.get("model", ""), signal=sig, label=label,
            confidence=float(decision.get("confidence", 0.0)), reason=str(decision.get("reason", "")),
            executed=executed,
            account={"cash": acct.cash, "equity": acct.equity, "positions": _positions_list()},
        )
