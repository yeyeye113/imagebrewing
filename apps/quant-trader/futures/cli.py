"""期货模块 CLI — 独立运行 + 盯市。

用法:
  python -m quanttrader.futures.cli scan          # 扫描主力合约
  python -m quanttrader.futures.cli watch # 盯市守护
  python -m quanttrader.futures.cli advise # 扫描+顾问
  python -m quanttrader.futures.cli risk   # 查看风控状态
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime

from .advisor import FuturesAdvisor, format_advices, format_principles
from .contracts import (
    MARKET_HOURS,
    contract_info,
    is_trading_now,
    seconds_to_next_session,
    session_label,
)
from .scanner import scan_futures


def cmd_scan(args) -> int:
    """扫描主力合约。"""
    print()
    print("🔍 扫描商品期货主力合约...")
    print()

    report = scan_futures(top_n=args.top)
    if not report.signals:
        print("⚠️ 未获取到期货数据（akshare 可能不可用或网络受限）")
        print("   试试: pip install akshare -U")
        return 1

    print(f"📊 {report.timestamp[:19]}")
    print(
        f"   时段: {report.stats.get('session', '?')} | "
        f"扫描 {report.stats['total_scanned']} 品种 → {report.stats['candidates']} 信号"
    )
    print(
        f"   多 {report.stats['long_signals']} · "
        f"空 {report.stats['short_signals']} · "
        f"中性 {report.stats['neutral_signals']}"
    )
    print()

    for i, s in enumerate(report.signals[:15], 1):
        icon = {"long": "📈", "short": "📉", "neutral": "⚖️"}.get(s.signal, "❓")
        strength_mark = {"strong": "★★★", "moderate": "★★☆", "weak": "★☆☆"}.get(s.signal_strength, "")
        change_sign = "+" if s.change_pct >= 0 else ""
        night = "🌙" if s.has_night else " ☀️"
        print(
            f"  {i:2d}. {icon} {s.code:4s} {s.name:<6s} "
            f"¥{s.price:>8,.0f} {change_sign}{s.change_pct:+.1f}% "
            f"评分 {s.score:>5.1f} {strength_mark} {night}"
        )
        print(
            f"      成交量 {s.volume:>8,} 手 | "
            f"持仓 {s.open_interest:>8,} ({s.oi_change_pct:+.1f}%) | "
            f"投机度 {s.speculative_ratio:.2f}"
        )
        print(f"      {s.reason}")

    print()
    return 0


def cmd_advise(args) -> int:
    """扫描 + 生成交易建议。"""
    print()
    print("🔍 期货扫描 + 智能建议...")
    print()

    advisor = FuturesAdvisor(
        equity=args.equity,
        cash=args.cash,
        max_leverage=args.max_leverage,
        max_margin_pct=args.max_margin_pct,
        risk_per_trade=args.risk_per_trade,
    )
    scan, advices = advisor.scan_and_advise()

    print(format_advices(advices, max_show=args.top))
    print()
    print("📖 期货交易铁律:")
    print(format_principles())
    print()
    return 0


def cmd_watch(args) -> int:
    """盯市守护循环。"""
    print("👁️  期货盯市模式启动")
    print(f"   扫描间隔: {args.interval}s | 品种: {args.top} 个")
    print(f"   当前: {session_label()} | {'🟢 交易中' if is_trading_now() else '⏸️ 等待开盘'}")
    print("   Ctrl+C 停止")
    print()

    advisor = FuturesAdvisor(
        equity=args.equity,
        cash=args.cash,
        max_leverage=args.max_leverage,
        max_margin_pct=args.max_margin_pct,
        risk_per_trade=args.risk_per_trade,
    )
    last_scan_ts = None

    try:
        while True:
            now = datetime.now()

            # Check if market is open
            if not is_trading_now():
                wait = seconds_to_next_session()
                wait_min = wait / 60
                if wait_min > 0.5:
                    print(f"  ⏸️ 休市中，下次交易: {wait_min:.0f} 分钟后", flush=True)
                time.sleep(min(args.interval, wait))
                continue

            # Scan
            print(f"\n{'─' * 50}")
            print(f"  {now.strftime('%H:%M:%S')} — {session_label()}")
            print(f"{'─' * 50}")

            signals, advices = advisor.scan_and_advise()

            if signals:
                # Show top 3 signals
                for s in signals[:3]:
                    icon = {"long": "📈", "short": "📉"}.get(s.signal, "⚖️")
                    c = "+" if s.change_pct >= 0 else ""
                    print(f"  {icon} {s.code} {s.name} {c}{s.change_pct:+.1f}% score={s.score:.0f} {s.signal_strength}")

            # Check for actionable signals
            actionable = [a for a in advices if a.direction != "neutral" and a.confidence in ("高", "中")]
            if actionable:
                print(f"\n  🎯 {len(actionable)} 个可操作信号:")
                for a in actionable[:3]:
                    print(a.to_text())

            last_scan_ts = now
            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\n👁️  盯市结束")
    return 0


def cmd_risk(args) -> int:
    """展示风控状态。"""

    print()
    print("🛡️ 期货风控状态")

    # Demo: 展示当前品种的保证金要求
    print()
    print("  主力品种保证金一览 (假设当前价):")
    print(f"  {'品种':6s} {'名称':8s} {'价格':>8s} {'每手保证金':>10s} {'杠杆':>5s} {'夜盘':>4s}")
    print("  " + "─" * 50)

    demo_prices = {
        "RB": 3600,
        "I": 800,
        "SC": 580,
        "M": 3400,
        "RM": 2800,
        "AG": 6000,
        "AU": 480,
        "CU": 72000,
        "TA": 5800,
        "MA": 2500,
        "SA": 1800,
        "P": 7800,
        "Y": 8000,
        "IF": 3800,
        "T": 100,
    }

    for code in ["RB", "I", "SC", "AG", "AU", "CU", "TA", "MA", "SA", "P", "IF", "T"]:
        spec = contract_info(code)
        if not spec:
            continue
        price = demo_prices.get(code, 5000)
        margin = spec.calc_margin(price, 1)
        leverage = 1 / spec.margin_rate if spec.margin_rate > 0 else 1
        hours = MARKET_HOURS.get(code)
        night = "🌙" if hours and hours.night_open else "☀️"
        print(f"  {code:6s} {spec.name:8s} ¥{price:>6,.0f} ¥{margin:>10,.0f}  {leverage:.0f}x{'':>2s} {night}")

    print()
    print(f"  最大建议杠杆: {args.max_leverage:.0f}x")
    print(f"  单笔风险上限: {args.risk_per_trade * 100:.0f}% 总资金")
    print(f"  保证金率上限: {args.max_margin_pct * 100:.0f}%")
    print()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="期货辅助交易提示系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m quanttrader.futures scan           # 扫描主力合约
  python -m quanttrader.futures advise         # 扫描 + 智能建议
  python -m quanttrader.futures watch   # 盯市守护
  python -m quanttrader.futures risk           # 查看风控参数
""",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="scan",
        choices=["scan", "advise", "watch", "risk"],
        help="模式: scan/advise/watch/risk",
    )
    parser.add_argument("--top", "-n", type=int, default=15, help="显示前 N 个品种")
    parser.add_argument("--interval", type=int, default=60, help="盯市扫描间隔 (秒)")
    parser.add_argument("--equity", type=float, default=100_000, help="总权益")
    parser.add_argument("--cash", type=float, default=100_000, help="可用资金")
    parser.add_argument("--max-leverage", type=float, default=3.0, help="最大杠杆")
    parser.add_argument("--max-margin-pct", type=float, default=0.30, help="最大保证金占比")
    parser.add_argument("--risk-per-trade", type=float, default=0.02, help="单笔风险比例")

    args = parser.parse_args(argv)

    if args.command == "advise":
        return cmd_advise(args)
    if args.command == "watch":
        return cmd_watch(args)
    if args.command == "risk":
        return cmd_risk(args)
    return cmd_scan(args)


if __name__ == "__main__":
    raise SystemExit(main())
