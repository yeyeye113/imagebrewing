#!/usr/bin/env python
"""quant-trader 全自动交易平台 — 一键启动。

用法:
    python run.py                          # 前台守护，市场时段自动交易
    python run.py --once                   # 单次决策（给 cron / 外部调度用）
    python run.py --status                 # 查看守护进程状态
    python run.py --install                # 注册为 Windows 系统服务
    python run.py --scan                   # 仅扫描：拉新闻 + LLM 研判，不下单

环境变量:
    DEEPSEEK_API_KEY    深度求是 API 密钥（或 OPENAI_API_KEY）
    QT_WEBHOOK_URL      通知 webhook 地址（覆盖 daemon.yaml）
    QT_ALLOW_LIVE=1     真钱交易闸门

配置:
    交易参数  → config.yaml（或 config_llm.yaml）
    守护进程  → daemon.yaml
"""

import datetime as dt
import os
import sys
from pathlib import Path

# Ensure the package is importable
sys.path.insert(0, str(Path(__file__).parent))

# Windows GBK 兼容 — 强制 UTF-8 输出
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _banner(cfg, daemon):
    """Print startup banner."""
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  🏦 quant-trader 全自动交易守护进程                      ║")
    print("╠══════════════════════════════════════════════════════════╣")
    print(f"║  标的: {cfg.symbol:<45s} ║")
    print(f"║  市场: {daemon.market:<45s} ║")
    print(f"║  数据: {cfg.data_source:<45s} ║")
    print(f"║  模型: {cfg.strategy.get('provider', 'deepseek'):<45s} ║")
    print(f"║  轮询: {daemon.poll_seconds}s{'':<42s} ║")
    print(f"║  通知: {'已配置' if daemon.webhook_url else '仅控制台'}{'':<42s} ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="quant-trader 全自动交易平台",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--config", "-c", default="config.yaml", help="交易配置文件")
    parser.add_argument("--daemon-config", "-d", default="daemon.yaml", help="守护进程配置文件")
    parser.add_argument("--once", action="store_true", help="单次决策后退出")
    parser.add_argument("--daemon", action="store_true", help="后台守护模式")
    parser.add_argument("--scan", action="store_true", help="仅扫描：拉新闻 + LLM 研判，不下单")
    parser.add_argument("--quick", action="store_true", help="短期推荐：≤1000元/≤5天 盘后分析+标的推荐")
    parser.add_argument("--fortune", action="store_true", help="主人今日运势 (天干地支+宜忌+心态)")
    parser.add_argument("--status", action="store_true", help="查看守护进程状态")
    parser.add_argument("--install", action="store_true", help="注册 Windows 系统服务")
    parser.add_argument("--uninstall", action="store_true", help="移除 Windows 系统服务")
    parser.add_argument("--webhook", default="", help="通知 webhook URL (覆盖 daemon.yaml)")
    parser.add_argument("--futures", action="store_true", help="期货辅助交易：扫描+建议+盯市")
    parser.add_argument("--analyze", "-a", default="", help="分析研判: 高低点+时间轴计划 (标的代码，如 RB, I, 600519)")
    parser.add_argument("--predict", "-p", default="", help="自由预测: 任意问题综合研判 (如 '原油SC下周怎么走')")
    parser.add_argument(
        "--direction", default="long", choices=["long", "short", "neutral"], help="分析方向 (配合 --analyze)"
    )

    args = parser.parse_args()

    # ── 导入 ──
    from quanttrader.config import Config
    from quanttrader.daemon import DaemonConfig, DaemonState, TradingDaemon, market_is_open, market_label

    # ── 创建 daemon 配置 ──
    dcfg_path = args.daemon_config
    dcfg = DaemonConfig.load(dcfg_path) if Path(dcfg_path).exists() else DaemonConfig()

    if args.webhook:
        dcfg.webhook_url = args.webhook
    elif not dcfg.webhook_url:
        dcfg.webhook_url = os.environ.get("QT_WEBHOOK_URL", "")

    # ── 配置文件不存在时的引导 ──
    if not Path(args.config).exists():
        print(f"""
╔══════════════════════════════════════════════════════════╗
║  ⚠️  未找到配置文件: {args.config:<36s} ║
║                                                          ║
║  快速开始:                                                ║
║  1. cp config.example.yaml config.yaml                   ║
║  2. 编辑 config.yaml 填写你的标的和参数                   ║
║  3. 设置 DEEPSEEK_API_KEY 环境变量                        ║
║  4. python run.py                                        ║
╚══════════════════════════════════════════════════════════╝
""")
        return 1

    # ── 加载交易配置 ──
    cfg = Config.load(args.config)
    provider = cfg.strategy.get("provider", "deepseek")

    # ── Windows 服务管理（不需要 API key）──
    if args.install:
        from quanttrader.daemon import install_windows_service

        return install_windows_service()
    if args.uninstall:
        from quanttrader.daemon import uninstall_windows_service

        return uninstall_windows_service()

    # ── 状态查询（不需要 API key）──
    if args.status:
        import time as _time

        state = DaemonState.load(Path(dcfg.state_file))
        label = market_label(dcfg.market)
        is_open = market_is_open(dcfg.market)
        wr = state.win_rate
        win_str = f"{wr * 100:.1f}%" if wr is not None else "N/A"
        print(f"""
╔══════════════════════════════════════════════════════════╗
║  📊 交易守护进程状态                                      ║
╠══════════════════════════════════════════════════════════╣
║  市场: {label:<45s} ║
║  状态: {"🟢 交易中" if is_open else "⏸️ 等待开盘"}{"":<38s} ║
║  日期: {state.date:<45s} ║
║  今日交易: {state.day_trades} 笔{"":<38s} ║
║  今日盈亏: ${state.day_pnl:> ,.2f}{"":<38s} ║
║  累计交易: {state.total_trades} 笔{"":<38s} ║
║  累计盈亏: ${state.total_pnl:> ,.2f}{"":<38s} ║
║  命中率: {win_str:<45s} ║
║  连亏: {state.consecutive_losses}{"":<44s} ║
║  熔断: {"⛔ 是" if state.halt_until > _time.time() else "✅ 否"}{"":<43s} ║
║  最后决策: {state.last_decision_at or "无"}{"":<38s} ║
╚══════════════════════════════════════════════════════════╝
""")
        return 0

    # ── 运势模式 ──
    if args.fortune:
        print("运势/玄学功能已下线。")
        return 0

    # ── 期货辅助交易模式 ──
    if args.futures:
        from quanttrader.futures.cli import main as futures_main

        return futures_main(["advise"])

    # ── 分析研判模式: 高低点 + 时间轴计划 ──
    if args.analyze:
        from quanttrader.analysis.highlow import find_highlows
        from quanttrader.analysis.timeline import build_timeline
        from quanttrader.forecast import _load_synthetic

        symbol = args.analyze.upper()
        print(f"\n📐 {symbol} 分析研判...\n")

        # 拉取数据
        df = None
        try:
            from quanttrader.futures.scanner_v2 import _fetch_single

            df = _fetch_single(symbol)
        except Exception:
            pass
        if df is None or len(df) < 20:
            code_seed = sum(ord(c) for c in symbol) + int(dt.date.today().strftime("%Y%m%d"))
            import numpy as np

            _rng = np.random.RandomState(code_seed % 2**31)
            df = _load_synthetic(
                symbol, days=120, start_price=float(abs(hash(symbol)) % 3000 + 2000), trend=0.03, vol=0.20, _rng=_rng
            )
            print("  [!] 使用合成数据 (无真实行情)\n")

        # 高低点分析
        hl = find_highlows(df, symbol=symbol)
        print(hl.to_text())
        print()

        # 时间轴计划
        plan = build_timeline(hl, direction=args.direction)
        print(plan.to_text())

        # 核心计划 + edge 展示
        try:
            from quanttrader.core_plan import format_plan, generate_plan
            from quanttrader.edge_journal import edge_summary_for_display

            edge = edge_summary_for_display(df)
            if edge.get("edge_active"):
                print(
                    f"\n🎯 Edge: {edge['edge_setup']} ({edge['edge_score']:.0f}分) "
                    f"→ {edge['edge_direction']}"
                )
                for r in edge.get("edge_reasons", []):
                    print(f"   · {r}")
            cp = generate_plan(df, require_edge=False)
            if cp:
                print("\n" + format_plan(cp))
        except Exception as ex:
            print(f"\n  [!] 核心计划: {ex}")
        return 0

    # ── 自由预测模式 ──
    if args.predict:
        from quanttrader.analysis.predictor import free_predict

        question = args.predict
        print(f"\n🔮 自由预测: {question}\n")

        report = free_predict(question)
        print(report.to_text())
        return 0

    # ── 短期推荐模式 ──
    if args.quick:
        from quanttrader.ai.llm import LLMConfig
        from quanttrader.short_term import format_report, generate_recommendations

        print("\n[*] 短期交易推荐引擎启动...\n")

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

    # ── 仅扫描模式 ──
    if args.scan:
        from quanttrader.ai.llm import LLMConfig, ask_llm
        from quanttrader.data.base import BarRequest, get_feed
        from quanttrader.news.feeds import aggregate_news, news_for_llm
        from quanttrader.news.parser import analyze_items, recommend_action

        # Init LLM config for scan
        scan_llm = LLMConfig(provider=provider)
        try:
            scan_llm.resolve()
        except Exception:
            pass

        print(f"\n[*] 扫描 {cfg.symbol}...\n")

        # Data
        feed_kwargs = {}
        if cfg.data_source in ("csv", "file"):
            feed_kwargs["path"] = cfg.data_path
        try:
            prices = get_feed(cfg.data_source, **feed_kwargs).history(
                BarRequest(symbol=cfg.symbol, start=cfg.start, end=cfg.end, interval=cfg.interval)
            )
            price = float(prices["close"].iloc[-1])
            print(f"[*] {cfg.symbol} 最新价: ${price:,.2f}  ({len(prices)} K线)")
        except Exception as e:
            print(f"[-] 行情加载失败: {e}")
            prices = None
            price = 0

        # News
        print("[*] 聚合新闻中...")
        items = aggregate_news(cfg.symbol, limit=15)
        sent = analyze_items(items)
        news_text = news_for_llm(items)
        print(f"   共 {len(items)} 条 (去重) | 情绪: {sent.label} ({sent.score:+.2f})")
        print(f"   高影响: {sum(1 for it in items if it.impact_level == 'high')} 条")
        print(
            f"   宏观: {sum(1 for it in items if it.category == 'macro')} 条 | "
            f"行业: {sum(1 for it in items if it.category == 'sector')} 条 | "
            f"公司: {sum(1 for it in items if it.category == 'company')} 条"
        )
        print(f"   建议: {recommend_action(sent, cfg.horizon)}")
        print()

        for it in items[:8]:
            imp = {"high": "HIGH", "medium": "MED", "low": " "}.get(it.impact_level, "")
            print(f"  {imp} [{it.source:12s}] {it.title[:70]}")
        print()

        # LLM
        if prices is not None and scan_llm.api_key:
            print("[LLM] 研判中...")
            try:
                decision = ask_llm(prices, scan_llm, news_text)
                sig = int(decision["signal"])
                label = {1: "BUY", 0: "HOLD", -1: "SELL"}.get(sig, str(sig))
                print(f"   决策: {label} | 置信度: {decision.get('confidence', 0):.0%}")
                print(f"   理由: {decision.get('reason', '')[:200]}")
                print(f"   模型: {decision.get('provider', '')}/{decision.get('model', '')}")
            except Exception as e:
                print(f"   LLM 调用失败: {e}")
        return 0

    # ── 检查 LLM API key (守护/单次需要) ──
    from quanttrader.ai.llm import LLMConfig

    llm = LLMConfig(provider=provider)
    try:
        llm.resolve()
    except ValueError as e:
        print(f"[-] LLM 配置错误: {e}")
        return 1

    if not llm.api_key:
        env_map = {"deepseek": "DEEPSEEK_API_KEY", "gpt": "OPENAI_API_KEY", "openai": "OPENAI_API_KEY"}
        env_var = env_map.get(provider, "DEEPSEEK_API_KEY")
        print(f"""
╔══════════════════════════════════════════════════════════╗
║  [!] 缺少 API 密钥                                       ║
║                                                          ║
║  export {env_var}=sk-你的密钥{"":<28s} ║
║                                                          ║
║  获取密钥:                                                ║
║  DeepSeek → https://platform.deepseek.com                ║
║  OpenAI   → https://platform.openai.com                  ║
╚══════════════════════════════════════════════════════════╝
""")
        return 1

    # ── 启动 ──
    _banner(cfg, dcfg)

    daemon = TradingDaemon(
        config_path=args.config,
        daemon_config_path=dcfg_path,
    )

    if args.once:
        daemon._running = True
        daemon._tick()
        return 0

    daemon.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
