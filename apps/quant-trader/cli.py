from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

from .advisor import advise, format_principles, format_tips
from .config import Config
from .data.base import BarRequest, get_feed
from .engine.backtest import Backtester
from .engine.metrics import format_summary
from .engine.position_sizing import SizingConfig, compute_entry_notional
from .engine.risk import PositionRisk, RiskConfig
from .engine.risk_assessment import assess_portfolio, assess_trade
from .horizon import apply_horizon
from .log import get_logger
from .news import analyze_items, fetch_news, horizon_fit_from_news, recommend_action
from .strategy.base import Signal, get_strategy

logger = get_logger("cli")


def _load_prices(cfg: Config):
    """Load prices, falling back to synthetic data if the real feed fails."""
    req = BarRequest(symbol=cfg.symbol, start=cfg.start, end=cfg.end, interval=cfg.interval)
    feed_kwargs = {}
    if cfg.data_source in ("csv", "file"):
        feed_kwargs["path"] = cfg.data_path
    try:
        feed = get_feed(cfg.data_source, **feed_kwargs)
        return feed.history(req), cfg.data_source
    except Exception as exc:
        if cfg.data_source != "synthetic":
            print(
                f"[warn] data source {cfg.data_source!r} failed ({exc}); falling back to synthetic data.",
                file=sys.stderr,
            )
            feed = get_feed("synthetic")
            return feed.history(req), "synthetic"
        raise


def cmd_backtest(cfg: Config, html: bool = False, out: str | None = None) -> int:
    if cfg.horizon:
        apply_horizon(cfg, cfg.horizon)
    prices, source = _load_prices(cfg)
    strat_params = {k: v for k, v in cfg.strategy.items() if k != "name"}
    if cfg.news.get("enabled"):
        from .strategy.news_blend import NewsBlendStrategy

        items, _ = fetch_news(cfg.symbol, cfg.news.get("source", "auto"))
        strategy, sent = NewsBlendStrategy.from_news_items(
            items,
            horizon=cfg.horizon or "medium",
            **strat_params,
        )
        print(f"  [news] sentiment={sent.label} score={sent.score:+.2f}")
    else:
        strategy = get_strategy(cfg.strategy.get("name", "sma_cross"), **strat_params)

    bt = Backtester(
        cash=cfg.cash,
        order_size=cfg.order_size,
        commission=cfg.commission,
        slippage=cfg.slippage,
        lot_size=cfg.lot_size,
        risk=RiskConfig(**cfg.risk),
        sizing=SizingConfig(**cfg.sizing),
    )
    result = bt.run(prices, strategy)

    bh = float(prices["close"].iloc[-1] / prices["close"].iloc[0] - 1.0)
    print("=" * 60)
    print(f"  Backtest: {cfg.symbol}  [{source} data, {strategy.name}]")
    print(f"  Bars: {len(prices)}  Trades: {result.n_trades}  Risk events: {len(result.risk_events or [])}")
    print("-" * 60)
    print(format_summary(result.stats))
    print("-" * 60)
    print(f"  Buy & hold   : {bh * 100:,.2f}%")
    print("=" * 60)
    print("  操盘建议 / Advisor:")
    print(format_tips(advise(result, buy_and_hold=bh)))
    print("=" * 60)

    # 报告输出 (融合自工作区版: HTML/Markdown 回测报告)
    if html:
        from .engine.reporter import save_html_report
        path = save_html_report(result, out or f"report_{cfg.symbol}.html", title=f"{cfg.symbol} 回测报告")
        print(f"  [report] HTML saved to: {path}")
    elif out:
        from .engine.reporter import report_markdown
        Path(out).write_text(report_markdown(result), encoding="utf-8")
        print(f"  [report] Markdown saved to: {out}")
    return 0


def cmd_advise(cfg: Config) -> int:
    """Run a backtest then print only the advisor output + principles."""
    prices, source = _load_prices(cfg)
    strat_params = {k: v for k, v in cfg.strategy.items() if k != "name"}
    strategy = get_strategy(cfg.strategy.get("name", "sma_cross"), **strat_params)
    bt = Backtester(
        cash=cfg.cash,
        order_size=cfg.order_size,
        commission=cfg.commission,
        slippage=cfg.slippage,
        lot_size=cfg.lot_size,
        risk=RiskConfig(**cfg.risk),
        sizing=SizingConfig(**cfg.sizing),
    )
    result = bt.run(prices, strategy)
    bh = float(prices["close"].iloc[-1] / prices["close"].iloc[0] - 1.0)
    print("=" * 60)
    print(f"  操盘诊断: {cfg.symbol} [{source}, {strategy.name}]")
    print("-" * 60)
    print(format_tips(advise(result, buy_and_hold=bh)))
    print("=" * 60)
    print("  顶级操盘手原则 / Principles:")
    print(format_principles())
    print("=" * 60)
    return 0


def cmd_live(cfg: Config) -> int:
    from .broker.base import auto_buy_enabled, get_broker

    bname = cfg.broker.get("name", "paper")
    poll = int(cfg.broker.get("poll_seconds", 60))

    if bname in ("paper", "cn_paper", "cn", "ashare_paper"):
        broker = get_broker(bname, cash=cfg.cash, commission=cfg.commission, slippage=cfg.slippage)
    else:
        broker = get_broker(
            bname,
            api_key=cfg.broker.get("api_key", ""),
            api_secret=cfg.broker.get("api_secret", ""),
            paper=cfg.broker.get("paper", True),
            allow_live=cfg.broker.get("allow_live", False),
            allow_leverage=cfg.sizing.get("allow_leverage", False),
        )

    strat_params = {k: v for k, v in cfg.strategy.items() if k != "name"}
    strategy = get_strategy(cfg.strategy.get("name", "sma_cross"), **strat_params)
    feed = get_feed(cfg.data_source)
    risk = RiskConfig(**cfg.risk)
    sizing = SizingConfig(**cfg.sizing)

    mode = "PAPER" if (bname == "paper" or cfg.broker.get("paper", True)) else "LIVE-REAL-MONEY"
    print(
        f"[{mode}] trading {cfg.symbol} via {bname} broker, polling every {poll}s. "
        f"Risk: {'on' if risk.enabled() else 'off'}. "
        f"Sizing: max_pos={sizing.max_position_pct:.0%}, reserve={sizing.cash_reserve_pct:.0%}. "
        f"Ctrl+C to stop.",
        flush=True,
    )

    pos_risk = None  # tracks entry/peak for the open position
    peak_equity = cfg.cash
    halted = False
    try:
        while True:
            req = BarRequest(symbol=cfg.symbol, start=cfg.start, end=cfg.end, interval=cfg.interval)
            prices = feed.history(req)
            target = strategy.generate(prices).iloc[-1]
            price = float(prices["close"].iloc[-1])

            if hasattr(broker, "set_price"):
                broker.set_price(cfg.symbol, price)

            pos = broker.get_position(cfg.symbol)
            acct = broker.get_account()
            action = "HOLD"

            # Seed/clear per-position risk tracking from the broker's view.
            if pos is not None and pos.qty > 0 and pos_risk is None:
                pos_risk = PositionRisk(float(pos.avg_price))
            if pos is None or pos.qty == 0:
                pos_risk = None

            # 1) Risk-driven exit (stops/trailing) takes priority.
            if pos_risk is not None and pos is not None and pos.qty > 0:
                pos_risk.update(price)
                reason = pos_risk.hit_stop(price, risk)
                if reason:
                    broker.sell_all(cfg.symbol)
                    pos_risk = None
                    action = f"EXIT:{reason}"

            # 2) Portfolio circuit breaker.
            peak_equity = max(peak_equity, acct.equity)
            if risk.max_drawdown and not halted and acct.equity <= peak_equity * (1 - risk.max_drawdown):
                if pos is not None and pos.qty > 0:
                    broker.sell_all(cfg.symbol)
                    pos_risk = None
                halted = True
                action = "HALT:max_drawdown"

            # 3) Strategy entries/exits (skipped once halted).
            if not halted and action == "HOLD":
                if target == Signal.BUY and (pos is None or pos.qty == 0) and not auto_buy_enabled():
                    action = "AUTO_BUY_DISABLED"
                elif target == Signal.BUY and (pos is None or pos.qty == 0):
                    pos_val = (pos.qty * price) if pos else 0.0
                    vol = None
                    if sizing.target_volatility > 0:
                        from .engine.position_sizing import annualized_vol

                        vol = annualized_vol(prices["close"], sizing.vol_lookback)
                    notional = compute_entry_notional(
                        acct.equity,
                        acct.cash,
                        pos_val,
                        cfg.order_size,
                        sizing,
                        risk,
                        volatility=vol,
                    )
                    broker.buy(cfg.symbol, notional)
                    if risk.enabled():
                        pos_risk = PositionRisk(price)
                    action = "BUY"
                elif target != Signal.BUY and pos is not None and pos.qty > 0:
                    broker.sell_all(cfg.symbol)
                    pos_risk = None
                    action = "SELL"

            acct = broker.get_account()
            # flush=True so redirected logs update live instead of buffering.
            print(
                f"  {cfg.symbol} px={price:,.2f} target={Signal(int(target)).name:4s} "
                f"action={action:18s} equity=${acct.equity:,.2f}",
                flush=True,
            )
            time.sleep(poll)
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


def _load_one(cfg: Config, symbol: str):
    """Load a single symbol's prices using cfg's source, with synthetic fallback."""
    req = BarRequest(symbol=symbol, start=cfg.start, end=cfg.end, interval=cfg.interval)
    feed_kwargs = {"path": cfg.data_path} if cfg.data_source in ("csv", "file") else {}
    try:
        return get_feed(cfg.data_source, **feed_kwargs).history(req), cfg.data_source
    except Exception as exc:
        if cfg.data_source != "synthetic":
            print(f"[warn] {symbol}: {cfg.data_source!r} failed ({exc}); using synthetic.", file=sys.stderr)
            return get_feed("synthetic").history(req), "synthetic"
        raise


def cmd_portfolio(cfg: Config) -> int:
    """Multi-asset portfolio backtest with capital allocation."""
    from .engine.portfolio_backtest import MultiBacktester

    symbols = cfg.symbols or [cfg.symbol]
    if len(symbols) < 2:
        print(
            "[info] only one symbol; portfolio backtest works best with several. Set `symbols: [A, B, C]` in config.",
            file=sys.stderr,
        )

    prices_by_symbol = {}
    source = cfg.data_source
    for sym in symbols:
        df, source = _load_one(cfg, sym)
        prices_by_symbol[sym] = df

    name = cfg.strategy.get("name", "sma_cross")
    strat_params = {k: v for k, v in cfg.strategy.items() if k != "name"}

    def factory():
        return get_strategy(name, **strat_params)

    mbt = MultiBacktester(
        cash=cfg.cash,
        allocation=cfg.allocation,
        order_size=cfg.order_size,
        commission=cfg.commission,
        slippage=cfg.slippage,
        lot_size=cfg.lot_size,
        risk=RiskConfig(**cfg.risk),
        sizing=SizingConfig(**cfg.sizing),
    )
    result = mbt.run(prices_by_symbol, factory)

    print("=" * 60)
    print(f"  Portfolio backtest [{source}, {name}, alloc={result.allocation}]")
    print(f"  Symbols: {', '.join(symbols)}")
    print("-" * 60)
    print(format_summary(result.stats))
    print("-" * 60)
    print("  Per-symbol (weight · return · sharpe · trades):")
    for sym, res in result.per_symbol.items():
        w = result.weights.get(sym, 0)
        print(
            f"    {sym:10s} w={w * 100:5.1f}%  "
            f"ret={res.stats.get('total_return', 0) * 100:6.1f}%  "
            f"sharpe={res.stats.get('sharpe', 0):5.2f}  trades={res.n_trades}"
        )
    print("=" * 60)
    print("  操盘建议 / Advisor (组合层面):")
    print(format_tips(advise(result)))
    print("=" * 60)
    return 0


def _apply_params_to_config(config_path: str, strategy_name: str, params: dict) -> str:
    """Write the optimized params back into a YAML config's `strategy:` block."""
    import yaml

    path = config_path or "config.yaml"
    data: dict[str, Any] = {}
    if Path(path).exists():
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    strat = data.get("strategy") or {}
    strat["name"] = strategy_name
    strat.update(params)
    data["strategy"] = strat
    Path(path).write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def cmd_optimize(cfg: Config, apply: bool = False, out: str | None = None, metric: str = "sharpe") -> int:
    """Grid-search strategy params with walk-forward (out-of-sample) validation."""
    from .engine.optimize import DEFAULT_GRIDS, grid_search, walk_forward

    prices, source = _load_prices(cfg)
    name = cfg.strategy.get("name", "sma_cross")
    grid = DEFAULT_GRIDS.get(name)
    if not grid:
        print(f"No default grid for strategy {name!r}. Supported: {list(DEFAULT_GRIDS)}", file=sys.stderr)
        return 1

    risk = RiskConfig(**cfg.risk)
    bt_kwargs: dict[str, Any] = dict(
        cash=cfg.cash,
        order_size=cfg.order_size,
        commission=cfg.commission,
        slippage=cfg.slippage,
        lot_size=cfg.lot_size,
        risk=risk,
        sizing=SizingConfig(**cfg.sizing),
    )

    print("=" * 60)
    print(f"  Optimize: {cfg.symbol} [{source}, {name}]  metric={metric}")
    print("-" * 60)
    full = grid_search(prices, name, grid, metric=metric, risk=risk, **bt_kwargs)
    print(f"  Best in-sample params : {full.best_params}")
    print(f"  Best in-sample {metric:8s}: {full.best_score:.2f}")
    print("  Top 5:")
    for params, stats in full.results[:5]:
        print(
            f"    {params}  sharpe={stats.get('sharpe', 0):.2f}  "
            f"ret={stats.get('total_return', 0) * 100:.1f}%  dd={stats.get('max_drawdown', 0) * 100:.1f}%"
        )

    print("-" * 60)
    print("  Walk-forward (out-of-sample) validation:")
    try:
        wf = walk_forward(prices, name, grid, n_splits=4, metric=metric, risk=risk, **bt_kwargs)
        for i, f in enumerate(wf.folds, 1):
            print(
                f"    fold {i}: params={f['best_params']} "
                f"OOS ret={f['oos_stats'].get('total_return', 0) * 100:.1f}% "
                f"OOS sharpe={f['oos_stats'].get('sharpe', 0):.2f}"
            )
        print("-" * 60)
        print(f"  Avg OOS return : {wf.avg_oos_return * 100:.2f}%")
        print(f"  Avg OOS sharpe : {wf.avg_oos_sharpe:.2f}")
        print(f"  Overfit gap (IS-OOS sharpe): {wf.overfit_gap:.2f}")
        if wf.overfit_gap > 1.0:
            print("  [!] 样本内远好于样本外 -> 过拟合风险高,别直接上实盘。")
        elif wf.avg_oos_sharpe <= 0:
            print("  [!] 样本外夏普<=0 -> 策略在未见数据上不赚钱。")
        else:
            print("  [+] 样本外表现尚可,相对稳健。")
    except Exception as e:
        print(f"    walk-forward skipped: {e}")

    if apply:
        written = _apply_params_to_config(out or cfg._source_path, name, full.best_params)
        print("-" * 60)
        print(f"  [applied] best params written to {written}")
    print("=" * 60)
    return 0


def cmd_news(cfg: Config) -> int:
    """Fetch and parse news sentiment for a symbol."""
    limit = int(cfg.news.get("limit", 20))
    source = cfg.news.get("source", "auto")
    items, used = fetch_news(cfg.symbol, source, limit)
    sent = analyze_items(items)
    hf = horizon_fit_from_news(items)
    horizon = cfg.horizon or "medium"

    print("=" * 60)
    print(f"  新闻解析: {cfg.symbol} [{used}]  投资周期: {horizon}")
    print("-" * 60)
    print(f"  情绪: {sent.label}  得分 {sent.score:+.2f}  ({sent.summary})")
    if sent.keywords:
        print(f"  关键词: {', '.join(sent.keywords[:8])}")
    print(f"  周期匹配: 短{hf['short']:.0%} / 中{hf['medium']:.0%} / 长{hf['long']:.0%}")
    print(f"  建议: {recommend_action(sent, horizon)}")
    print("-" * 60)
    print("  最新标题:")
    for i, it in enumerate(items[:10], 1):
        print(f"    {i:2d}. [{it.published[:10] if it.published else '----'}] {it.title[:70]}")
    print("=" * 60)
    return 0


def cmd_risk(cfg: Config) -> int:
    """Pre-trade risk assessment with loss / VaR estimates."""
    risk = RiskConfig(**cfg.risk)
    sizing = SizingConfig(**cfg.sizing)

    if cfg.symbols:
        prices_by_symbol = {}
        source = cfg.data_source
        for sym in cfg.symbols:
            df, source = _load_one(cfg, sym)
            prices_by_symbol[sym] = df
        result = assess_portfolio(
            prices_by_symbol,
            cfg.allocation,
            cfg.cash,
            cfg.order_size,
            sizing,
            risk,
        )
        print("=" * 60)
        print(f"  组合风险评估 [{source}, alloc={cfg.allocation}]  评级 {result.risk_grade} ({result.risk_score}/100)")
        print("-" * 60)
        print(f"  已分配 {result.allocated_pct * 100:.1f}%  ·  闲置现金 {result.idle_cash_pct * 100:.1f}%")
        print(
            f"  组合 VaR95/日 ${result.portfolio_var_95_1d:,.0f} "
            f"({result.portfolio_var_95_1d_pct * 100:.2f}%)  ·  HHI={result.concentration_hhi:.2f}"
        )
        print("  各标的:")
        for sym, p in result.per_symbol.items():
            print(
                f"    {sym:10s} w={p['weight'] * 100:5.1f}%  "
                f"alloc=${p['allocated_cash']:,.0f}  "
                f"止损亏=${p['max_loss_at_stop']:,.0f}  grade={p['risk_grade']}"
            )
        if result.warnings:
            print("-" * 60)
            for w in result.warnings:
                print(f"  [!] {w}")
        print("=" * 60)
        return 0

    prices, source = _load_prices(cfg)
    price = float(prices["close"].iloc[-1])
    a = assess_trade(
        cfg.symbol,
        price,
        prices,
        cfg.cash,
        cfg.cash,
        0,
        cfg.order_size,
        sizing,
        risk,
        cfg.commission,
        cfg.slippage,
    )
    print("=" * 60)
    print(f"  仓位风险评估: {cfg.symbol} @ ${price:,.2f} [{source}]  评级 {a.risk_grade} ({a.risk_score}/100)")
    print("-" * 60)
    print(f"  预估买入     ${a.proposed_notional:,.0f}  ({a.proposed_position_pct * 100:.1f}% 净值)")
    print(f"  止损最大亏   ${a.max_loss_at_stop:,.0f}  ({a.max_loss_pct * 100:.2f}% 净值)")
    print(f"  1日 VaR95    ${a.var_95_1d:,.0f}  ({a.var_95_1d_pct * 100:.2f}%)")
    print(f"  年化波动     {a.annual_vol * 100:.1f}%  ·  绑定限制: {a.binding_cap}")
    print("  上限分解:")
    for k, v in a.cap_breakdown.items():
        mark = " ←" if k == a.binding_cap else ""
        print(f"    {k:20s} ${v:,.0f}{mark}")
    if a.scenarios:
        print("  情景分析:")
        for s in a.scenarios:
            print(
                f"    {s['name']:12s} {s['trigger']:8s}  "
                f"${abs(s['loss']):,.0f} ({abs(s['loss_pct_equity']) * 100:.2f}%)"
            )
    if a.warnings:
        print("-" * 60)
        for w in a.warnings:
            print(f"  [!] {w}")
    print("=" * 60)
    return 0


def cmd_trade(
    cfg: Config, side: str, qty: float | None, notional: float | None, order_type: str, limit_price: float | None
) -> int:
    """Place a single manual order through the configured broker."""
    from .broker.base import get_broker

    bname = cfg.broker.get("name", "paper")
    if bname == "paper" or bname in ("cn_paper", "cn", "ashare_paper"):
        broker = get_broker(bname, cash=cfg.cash, commission=cfg.commission, slippage=cfg.slippage)
    else:
        broker = get_broker(
            bname,
            api_key=cfg.broker.get("api_key", ""),
            api_secret=cfg.broker.get("api_secret", ""),
            paper=cfg.broker.get("paper", True),
            allow_live=cfg.broker.get("allow_live", False),
            allow_leverage=cfg.sizing.get("allow_leverage", False),
        )

    live = getattr(broker, "is_live", False)
    if live and not cfg.broker.get("allow_live", False):
        print(
            "[X] 实盘(真钱)交易未确认。请在 config 的 broker.allow_live: true,或设环境变量 QT_ALLOW_LIVE=1。",
            file=sys.stderr,
        )
        return 1

    # Push a fresh price into paper brokers so the fill has a reference.
    if hasattr(broker, "set_price"):
        prices, _ = _load_prices(cfg)
        broker.set_price(cfg.symbol, float(prices["close"].iloc[-1]))

    if side == "sell" and qty is None:
        pos = broker.get_position(cfg.symbol)
        qty = pos.qty if pos else 0.0
        if qty <= 0:
            print(f"[!] {cfg.symbol} 无持仓可卖。", file=sys.stderr)
            return 1

    if side == "buy" and qty is None and notional is None:
        notional = broker.get_account().cash * cfg.order_size

    order = broker.submit_order(
        cfg.symbol,
        side,
        qty=qty,
        notional=notional,
        order_type=order_type,
        limit_price=limit_price,
    )
    acct = broker.get_account()
    mode = "LIVE-REAL-MONEY" if live else "PAPER"
    print("=" * 60)
    print(f"  [{mode}] 下单: {cfg.symbol} {side.upper()} ({order_type}) via {bname}")
    print(f"  订单号: {order.id}  状态: {order.status}")
    if order.filled_qty:
        print(f"  成交: {order.filled_qty:,.4f} @ ${order.filled_price:,.2f}  费用 ${order.fees:,.2f}")
    if order.note:
        print(f"  备注: {order.note}")
    print(f"  账户: 现金 ${acct.cash:,.2f}  权益 ${acct.equity:,.2f}")
    print("=" * 60)
    return 0


def cmd_serve(host: str, port: int) -> int:
    try:
        import uvicorn
    except ImportError:
        print("uvicorn is required to serve the API. Run `pip install fastapi uvicorn`.", file=sys.stderr)
        return 1
    print(f"Starting quant-trader on http://{host}:{port}  (dashboard at /, API docs at /docs)")
    uvicorn.run("quanttrader.api.server:app", host=host, port=port, reload=False)
    return 0


def cmd_quick(cfg: Config) -> int:
    """短期推荐：≤1000元/≤5天 盘后分析+标的推荐。"""
    from .ai.llm import LLMConfig
    from .short_term import format_report, generate_recommendations

    print("\n[*] 短期交易推荐引擎启动...\n")

    provider = cfg.strategy.get("provider", "deepseek")
    llm_cfg = LLMConfig(provider=provider)
    has_key = False
    try:
        llm_cfg.resolve()
        has_key = bool(llm_cfg.api_key)
    except Exception:
        pass

    if not has_key:
        print("[!] 未配置 LLM API Key，使用纯量化评分模式。")
        print("   设置 DEEPSEEK_API_KEY 环境变量可启用 AI 研判。\n")
        llm_cfg.api_key = ""

    results = generate_recommendations(budget=1000, llm_config=llm_cfg if has_key else None)
    print()
    print(format_report(results))
    print()
    return 0


def cmd_report(cfg: Config, report_type: str = "daily") -> int:
    """生成交易报告 (daily/weekly/monthly/all)。"""
    from datetime import date

    from .reports import DailyReport, MonthlyReport, ReportGenerator, WeeklyReport

    if report_type == "all":
        paths = ReportGenerator.all()
        print("=" * 60)
        print("  报告生成完成")
        for k, v in paths.items():
            print(f"  {k:8s} : {v}")
        print("=" * 60)
        return 0

    target = date.today()
    if report_type == "daily":
        path = DailyReport(target).generate()
    elif report_type == "weekly":
        path = WeeklyReport(target).generate()
    elif report_type == "monthly":
        path = MonthlyReport(target).generate()
    else:
        print(f"未知报告类型: {report_type}", file=sys.stderr)
        return 1

    print(f"报告已生成: {path}")
    return 0


def cmd_alpha(n_stocks: int = 10) -> int:
    """多策略真实回测 + 信号 edge 研究表（需联网加载 akshare）。"""
    from .research import (
        format_alpha_table,
        format_signal_edge,
        load_universe_prices,
        signal_edge_table,
        strategy_alpha_table,
    )

    logger.info("加载 %d 只标的…", n_stocks)
    prices = load_universe_prices(n_stocks=n_stocks)
    if not prices:
        logger.error("未加载到行情，请检查网络与 akshare")
        return 1
    rows, bh = strategy_alpha_table(prices)
    print(format_alpha_table(rows, bh))
    print()
    edge_rows, base_ret, base_win = signal_edge_table(prices)
    print(format_signal_edge(edge_rows, base_ret, base_win))
    return 0


def cmd_deep_dip_wf(synthetic: bool = False, n_stocks: int = 5) -> int:
    """deep_dip 策略滚动样本外回测。"""
    from .research import (
        deep_dip_walk_forward,
        format_deep_dip_walk_forward,
        load_universe_prices,
        synth_prices_map,
    )

    if synthetic:
        prices = synth_prices_map()
    else:
        prices = load_universe_prices(n_stocks=n_stocks, min_bars=280)
    if not prices:
        logger.error("无可用行情")
        return 1
    report = deep_dip_walk_forward(prices)
    print(format_deep_dip_walk_forward(report))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quanttrader", description="Minimal quant trading framework")
    parser.add_argument(
        "command",
        choices=[
            "backtest",
            "live",
            "serve",
            "advise",
            "optimize",
            "portfolio",
            "risk",
            "news",
            "trade",
            "quick",
            "report",
            "predict",
            "alpha",
            "deep-dip-wf",
        ],
        help="What to run",
    )
    parser.add_argument("-c", "--config", help="Path to config.yaml")
    parser.add_argument("--symbol", help="Override symbol")
    parser.add_argument("--source", help="Override data source (yahoo|synthetic)")
    parser.add_argument("--host", default="127.0.0.1", help="API host (serve)")
    parser.add_argument("--port", type=int, default=8000, help="API port (serve)")
    parser.add_argument("--apply", action="store_true", help="optimize: write best params back to the config file")
    parser.add_argument("--out", help="optimize --apply: target config path (default: the loaded config)")
    parser.add_argument("--metric", default="sharpe", help="optimize: ranking metric (default sharpe)")
    # trade command
    parser.add_argument("--side", choices=["buy", "sell"], help="trade: order side")
    parser.add_argument("--qty", type=float, help="trade: share quantity")
    parser.add_argument("--notional", type=float, help="trade: dollar amount (buy)")
    parser.add_argument("--order-type", default="market", choices=["market", "limit"], help="trade: order type")
    parser.add_argument("--limit-price", type=float, help="trade: limit price")
    # report command
    parser.add_argument(
        "--type",
        dest="report_type",
        default="daily",
        choices=["daily", "weekly", "monthly", "all"],
        help="report: report type (default daily)",
    )
    # predict command
    parser.add_argument("--profile", default="fast", help="predict: fast|balanced|precise|research")
    parser.add_argument("--n-stocks", type=int, default=10, help="predict/alpha: 股票数量")
    parser.add_argument("--n-futures", type=int, default=10, help="predict: 期货数量")
    parser.add_argument("--synthetic", action="store_true", help="deep-dip-wf: 用合成数据")
    args = parser.parse_args(argv)

    if args.command == "serve":
        return cmd_serve(args.host, args.port)

    cfg = Config.load(args.config)
    if args.symbol:
        cfg.symbol = args.symbol
    if args.source:
        cfg.data_source = args.source

    if args.command == "backtest":
        return cmd_backtest(cfg)
    if args.command == "advise":
        return cmd_advise(cfg)
    if args.command == "optimize":
        return cmd_optimize(cfg, apply=args.apply, out=args.out, metric=args.metric)
    if args.command == "portfolio":
        return cmd_portfolio(cfg)
    if args.command == "risk":
        return cmd_risk(cfg)
    if args.command == "news":
        return cmd_news(cfg)
    if args.command == "trade":
        if not args.side:
            print(
                "trade 需要 --side buy|sell (可选 --qty / --notional / --order-type / --limit-price)", file=sys.stderr
            )
            return 1
        return cmd_trade(cfg, args.side, args.qty, args.notional, args.order_type, args.limit_price)
    if args.command == "live":
        return cmd_live(cfg)
    if args.command == "quick":
        return cmd_quick(cfg)
    if args.command == "report":
        return cmd_report(cfg, args.report_type)
    if args.command == "predict":
        return cmd_predict_enhanced(
            n_stocks=args.n_stocks,
            n_futures=args.n_futures,
            profile=args.profile,
        )
    if args.command == "alpha":
        return cmd_alpha(n_stocks=args.n_stocks)
    if args.command == "deep-dip-wf":
        return cmd_deep_dip_wf(synthetic=args.synthetic, n_stocks=args.n_stocks)
    return 1


def cmd_predict_enhanced(
    n_stocks: int = 10,
    n_futures: int = 10,
    use_news: bool = False,
    use_wuxing: bool = False,
    wuxing_weight: float = 0.05,
    apply_correction: bool = False,
    profile: str = "fast",
) -> int:
    """6步增强预测管线 — 经 prediction_service 统一执行并写 journal."""
    import os

    from .live_panel import LivePanelTracker
    from .prediction_log import DeviationTracker, PredictionLogger
    from .prediction_service import (
        PredictionDeps,
        PredictionRequest,
        persist_prediction_batch,
        run_prediction_batch,
    )
    from .screening_journal import ScreeningJournal
    from .strategy_journal import StrategyJournal

    t0 = time.time()
    logger.info("╔══════════════════════════════════════════════════════════════╗")
    logger.info("║  6+1步预测管线 (prediction_service)                          ║")
    logger.info("╚══════════════════════════════════════════════════════════════╝")

    log_dir = os.environ.get("QT_PREDICTION_LOG_DIR", "")
    deps = PredictionDeps(
        prediction_logger=PredictionLogger(log_dir),
        deviation_tracker=DeviationTracker(PredictionLogger(log_dir)),
        screening_journal=ScreeningJournal(log_dir),
        live_panel=LivePanelTracker(log_dir),
        strategy_journal=StrategyJournal(log_dir),
    )

    req = PredictionRequest(
        n_stocks=n_stocks, n_futures=n_futures,
        use_news=use_news, use_wuxing=use_wuxing,
        wuxing_weight=wuxing_weight, apply_correction=apply_correction,
        profile=profile,
    )
    batch = run_prediction_batch(req)
    persist_prediction_batch(
        batch, deps,
        apply_correction=apply_correction,
        correction_weight=req.correction_weight,
    )

    for kind, log in [("股票", batch.stock_log), ("期货", batch.future_log)]:
        if log.get("sector_preselect"):
            sp = log["sector_preselect"]
            logger.info("[%s] 板块预筛: %d → %d 只", kind, sp.get("n_before", 0), sp.get("n_after", 0))

    _print_pipeline_results("股票", batch.stock_results)
    _print_pipeline_results("期货", batch.future_results)

    if batch.errors:
        for err in batch.errors:
            logger.error("管线错误: %s", err)

    elapsed = time.time() - t0
    logger.info("=" * 80)
    logger.info("  耗时 %.1fs  |  profile=%s  news=%s  wuxing=%s  矫正=%s",
                elapsed, batch.profile.name, batch.effective_news,
                batch.effective_wuxing, apply_correction)
    logger.info("  ⚠️  量化技术面综合分析，不构成投资建议。")
    logger.info("=" * 80)
    return 0


def _print_pipeline_results(kind: str, results: list) -> None:
    """格式化输出管线结果 (含多时间维度)."""
    if not results:
        logger.info("  [%s] 无标的通过筛选.", kind)
        return

    from .ashare_pipeline import PipelineResult
    r0 = results[0]
    is_pipeline = isinstance(r0, PipelineResult)

    lines = [
        "",
        "=" * 100,
        f"  {'📈' if kind == '股票' else '📉'} {kind} TOP {len(results)} 综合排名 (多时间维度预测)",
        "=" * 100,
    ]

    if is_pipeline:
        header = (
            f"  {'排名':<4} {'代码':<8} {'名称':<8} {'板块':<6} "
            f"{'综合':>5} {'技术':>5} "
            f"{'3日预测':<14} {'7日预测':<14} {'30日预测':<14}"
        )
        lines.append(header)
        lines.append("  " + "-" * 110)

        for r in results:
            lines.append(
                f"  {r.rank:<4} {r.symbol:<8} {r.name:<8} {r.sector:<6} "
                f"{r.final_score:>5.0f} {r.round1_score:>5.0f} "
                f"{r.prediction_3d:<14} {r.prediction_7d:<14} {r.prediction_30d:<14}"
            )

        top_sectors = list(set(r.sector for r in results[:5]))
        lines.append("  " + "-" * 110)
        lines.append(f"  Top5 覆盖板块: {', '.join(top_sectors)}")
    else:
        # 简单模式回退
        header = (
            f"  {'排名':<4} {'代码':<8} {'名称':<8} "
            f"{'得分':>5} {'信号':>5} {'当前价':>8}"
        )
        lines.append(header)
        lines.append("  " + "-" * 38)
        for i, r in enumerate(results, 1):
            d = r if isinstance(r, dict) else r.__dict__
            lines.append(
                f"  {i:<4} {d.get('symbol', ''):<8} {d.get('name', ''):<8} "
                f"{d.get('final_score', d.get('score', 0)):>5.0f} "
                f"{d.get('signal', '—'):>5} "
                f"{d.get('last_price', 0):>8.2f}"
            )

    lines.append("=" * 100)
    logger.info("\n".join(lines))


if __name__ == "__main__":
    raise SystemExit(main())
