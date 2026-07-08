"""策略研究与样本外验证工具（正式模块）。

把一次性研究脚本固化为可复用、可测试的函数，支撑 CLI：
  - python -m quanttrader.cli alpha   多策略真实回测绩效 + 超跌/超买信号 edge
  - python -m quanttrader.cli oos     预测引擎样本外方向命中率(walk-forward)

实证背景见 docs/prediction_accuracy_plan.md「二次复核实证」：
多指标投票预测方向≈随机；技术择时在白马牛市普遍跑输买入持有；深超跌反转
高胜率低回撤但稀疏。结论：以 Sharpe/回测收益(而非方向命中率)评估策略。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .data.base import _normalize
from .engine.backtest import Backtester
from .engine.position_sizing import SizingConfig
from .engine.risk import RiskConfig
from .log import get_logger
from .predict import LIQUID_STOCKS
from .strategy.advanced_strategies import ALL_STRATEGY_CONFIGS
from .strategy.base import get_strategy

logger = get_logger("research")

# 研究用策略集 = 11 投票策略 + 深超跌反转（寻优最优档 dev-10%/hold60）
RESEARCH_STRATEGIES = [
    *ALL_STRATEGY_CONFIGS,
    ("deep_dip",
     {"ma_long": 60, "ma_exit": 20, "entry_dev": -0.10, "exit_dev": 0.0, "max_hold": 60},
     "深超跌反转"),
]

DEFAULT_FWDS = (5, 10, 20)


# ── 数据加载 ────────────────────────────────────────────────────────

def load_universe_prices(n_stocks: int = 30, days_back: int = 1300,
                         min_bars: int = 300) -> dict[str, pd.DataFrame]:
    """加载 A 股核心标的真实日线（akshare 腾讯源前复权）。需要联网。"""
    import akshare as ak

    out: dict[str, pd.DataFrame] = {}
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=days_back)).strftime("%Y%m%d")
    for code, name in LIQUID_STOCKS[:n_stocks]:
        prefix = "sh" if code.startswith(("6", "68")) else "sz"
        raw = None
        for attempt in range(3):
            try:
                raw = ak.stock_zh_a_hist_tx(symbol=f"{prefix}{code}",
                                            start_date=start, end_date=end, adjust="qfq")
                if raw is not None and not raw.empty:
                    break
            except Exception:
                time.sleep(0.5 * (attempt + 1))
        if raw is None or raw.empty:
            logger.warning("加载失败: %s %s", code, name)
            continue
        df = raw.copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        df = df.rename(columns={c: c.lower() for c in df.columns})
        if "volume" not in df.columns and "amount" in df.columns:
            df["volume"] = (df["amount"] * 10000) / df["close"].clip(lower=0.01)
        df = df.dropna(subset=["close"])
        if len(df) >= min_bars:
            out[code] = _normalize(df)
    return out


# ── 研究一：多策略真实回测绩效 ──────────────────────────────────────

@dataclass
class StrategyAlpha:
    label: str
    sharpe: float
    total_return: float
    win_rate: float
    max_drawdown: float
    exposure: float       # 平均持仓占比（在场时间）
    beat_bh: int          # 跑赢买入持有的标的数
    n_total: int
    n_trades: int


def strategy_alpha_table(prices_map: dict[str, pd.DataFrame],
                         strategies=None) -> tuple[list[StrategyAlpha], float]:
    """对每个策略在 prices_map 上做纯信号回测（无风控满仓择时），返回绩效排名。

    返回 (按夏普降序的 StrategyAlpha 列表, 买入持有平均收益)。不联网。
    """
    strategies = strategies or RESEARCH_STRATEGIES
    bt = Backtester(risk=RiskConfig(), sizing=SizingConfig())
    bhs = {c: float(p["close"].iloc[-1] / p["close"].iloc[0] - 1)
           for c, p in prices_map.items() if len(p) >= 2}

    rows: list[StrategyAlpha] = []
    for sname, params, label in strategies:
        shs, rets, dds, wins, expo = [], [], [], [], []
        beat = ntr = ntot = 0
        for code, p in prices_map.items():
            try:
                strat = get_strategy(sname, **params)
                sig = strat.generate(p)
                res = bt.run(p, strat)
            except Exception as e:
                logger.debug("%s/%s 回测异常: %s", sname, code, e)
                continue
            st = res.stats
            shs.append(st.get("sharpe", 0.0))
            rets.append(st.get("total_return", 0.0))
            dds.append(st.get("max_drawdown", 0.0))
            ts = res.trade_stats or {}
            if ts.get("n_round_trips", 0) > 0:
                wins.append(ts.get("win_rate", 0.0))
                ntr += ts["n_round_trips"]
            expo.append(float((sig.to_numpy() == 1).mean()))
            if st.get("total_return", 0.0) > bhs.get(code, 0.0):
                beat += 1
            ntot += 1
        rows.append(StrategyAlpha(
            label=label,
            sharpe=float(np.mean(shs)) if shs else 0.0,
            total_return=float(np.mean(rets)) if rets else 0.0,
            win_rate=float(np.mean(wins)) if wins else 0.0,
            max_drawdown=float(np.mean(dds)) if dds else 0.0,
            exposure=float(np.mean(expo)) if expo else 0.0,
            beat_bh=beat, n_total=ntot, n_trades=ntr,
        ))
    rows.sort(key=lambda r: -r.sharpe)
    bh_mean = float(np.mean(list(bhs.values()))) if bhs else 0.0
    return rows, bh_mean


def format_alpha_table(rows: list[StrategyAlpha], bh_mean: float) -> str:
    lines = [
        "=" * 86,
        "多策略真实回测绩效（纯信号·无风控满仓择时·按夏普排序）",
        "=" * 86,
        f"{'策略':<14}{'夏普':>8}{'总收益':>10}{'回撤':>9}{'胜率':>7}{'仓位':>7}{'跑赢买持':>10}{'交易数':>8}",
    ]
    for r in rows:
        lines.append(
            f"{r.label:<14}{r.sharpe:>8.2f}{r.total_return*100:>9.1f}%"
            f"{r.max_drawdown*100:>8.1f}%{r.win_rate*100:>6.0f}%"
            f"{r.exposure*100:>6.0f}%{r.beat_bh:>6}/{r.n_total:<3}{r.n_trades:>8}"
        )
    lines.append("-" * 86)
    lines.append(f"{'买入持有基准':<14}{'-':>8}{bh_mean*100:>9.1f}%")
    return "\n".join(lines)


# ── 研究二：超跌/超买信号前瞻收益 edge ──────────────────────────────

def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).rolling(n).mean()
    dn = (-d.clip(upper=0)).rolling(n).mean()
    rs = up / dn.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def _signal_masks(p: pd.DataFrame) -> dict[str, np.ndarray]:
    close = p["close"]
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()
    std20 = close.rolling(20).std()
    r = _rsi(close)
    dev20 = close / ma20 - 1
    dev60 = close / ma60 - 1
    return {
        "RSI<30": (r < 30).to_numpy(),
        "破布林下轨": (close < ma20 - 2 * std20).to_numpy(),
        "距MA20<-5%": (dev20 < -0.05).to_numpy(),
        "距MA60<-10%(深超跌)": (dev60 < -0.10).to_numpy(),
        "20日新低": (close <= close.rolling(20).min()).to_numpy(),
        "RSI>70": (r > 70).to_numpy(),
        "距MA20>+10%": (dev20 > 0.10).to_numpy(),
        "20日新高": (close >= close.rolling(20).max()).to_numpy(),
    }


@dataclass
class SignalEdge:
    name: str
    n: int
    fwd_returns: dict[int, float]   # fwd -> 平均收益
    fwd_winrates: dict[int, float]  # fwd -> 胜率


def signal_edge_table(prices_map: dict[str, pd.DataFrame],
                      fwds=DEFAULT_FWDS) -> tuple[list[SignalEdge], dict[int, float], dict[int, float]]:
    """统计各信号触发后未来 N 日的平均收益与胜率，并给出"任意点买入"基准。"""
    agg: dict[str, dict[int, list]] = {}
    base: dict[int, list] = {f: [] for f in fwds}
    for p in prices_map.values():
        close = p["close"].to_numpy()
        n = len(close)
        masks = _signal_masks(p)
        fr = {}
        for f in fwds:
            arr = np.full(n, np.nan)
            arr[:n - f] = close[f:] / close[:n - f] - 1
            fr[f] = arr
            base[f].extend(arr[~np.isnan(arr)].tolist())
        for sname, mask in masks.items():
            agg.setdefault(sname, {f: [] for f in fwds})
            for f in fwds:
                m = mask & ~np.isnan(fr[f])
                agg[sname][f].extend(fr[f][m].tolist())

    def stat(a):
        arr = np.array(a)
        return (float(arr.mean()) if len(arr) else 0.0,
                float((arr > 0).mean()) if len(arr) else 0.0)

    rows = []
    for sname, byf in agg.items():
        rets, wins, nmax = {}, {}, 0
        for f in fwds:
            m, w = stat(byf[f])
            rets[f] = m; wins[f] = w; nmax = max(nmax, len(byf[f]))
        rows.append(SignalEdge(sname, nmax, rets, wins))
    base_ret = {f: stat(base[f])[0] for f in fwds}
    base_win = {f: stat(base[f])[1] for f in fwds}
    return rows, base_ret, base_win


def format_signal_edge(rows: list[SignalEdge], base_ret, base_win,
                       fwds=DEFAULT_FWDS) -> str:
    lines = [
        "=" * 86,
        "超跌/超买信号前瞻收益 edge（* = 胜率超同期基准 2%+ 才算有 edge）",
        "=" * 86,
        f"{'信号':<22}{'触发':>7}" + "".join(f"{str(f)+'日收益/胜率':>18}" for f in fwds),
        f"{'[基准]任意点买入':<22}{'-':>7}" +
        "".join(f"{base_ret[f]*100:+.2f}%/{base_win[f]*100:.0f}%".rjust(18) for f in fwds),
        "-" * 86,
    ]
    for r in sorted(rows, key=lambda x: -x.fwd_winrates[fwds[-1]]):
        cells = f"{r.name:<22}{r.n:>7}"
        for f in fwds:
            flag = "*" if r.fwd_winrates[f] > base_win[f] + 0.02 else " "
            cells += f"{r.fwd_returns[f]*100:+.2f}%/{r.fwd_winrates[f]*100:.0f}%{flag}".rjust(18)
        lines.append(cells)
    return "\n".join(lines)


# ── 研究三：深超跌信号按趋势 regime 拆分（牛市回调 vs 弱势抄底）──────────

@dataclass
class RegimeEdge:
    """深超跌信号在某趋势 regime 下的前瞻表现 + 同 regime 基准。"""
    regime: str                     # "弱势" / "强势"
    n: dict[int, int]               # fwd -> 信号样本数
    sig_ret: dict[int, float]       # fwd -> 信号平均收益
    sig_win: dict[int, float]       # fwd -> 信号胜率
    base_ret: dict[int, float]      # fwd -> 同 regime 任意点基准收益
    base_win: dict[int, float]      # fwd -> 同 regime 任意点基准胜率


def regime_edge_table(prices_map: dict[str, pd.DataFrame], fwds=DEFAULT_FWDS,
                      dip_dev: float = -0.10, ma_dip: int = 60,
                      ma_regime: int = 120) -> list[RegimeEdge]:
    """深超跌信号(close/MA{ma_dip}-1 <= dip_dev)前瞻收益，按个股趋势 regime
    (close vs MA{ma_regime}) 拆「弱势/强势」，对照各 regime 基准。不联网。

    实证(2026-06-29): 深超跌 edge 在「强势(close≥MA120)」最猛(20日 +16pp 胜率,
    即"牛市健康回调买点")，但极稀疏(占比<0.5%)，难独立成策、宜作入场择时叠加层；
    「弱势(close<MA120)」抄底 edge 温和(+6.5pp)但样本充足。
    """
    regimes = ("弱势", "强势")
    sig_acc: dict[str, dict[int, list[float]]] = {r: {f: [] for f in fwds} for r in regimes}
    base_acc: dict[str, dict[int, list[float]]] = {r: {f: [] for f in fwds} for r in regimes}
    for p in prices_map.values():
        close = p["close"]
        dev = (close / close.rolling(ma_dip).mean() - 1.0).to_numpy()
        weak = (close < close.rolling(ma_regime).mean()).to_numpy()
        c = close.to_numpy()
        n = len(c)
        dip = dev <= dip_dev
        for f in fwds:
            fwd = np.full(n, np.nan)
            fwd[: n - f] = c[f:] / c[: n - f] - 1.0
            ok = ~np.isnan(fwd)
            for r, rmask in (("弱势", weak), ("强势", ~weak)):
                sig_acc[r][f].extend(fwd[dip & rmask & ok].tolist())
                base_acc[r][f].extend(fwd[rmask & ok].tolist())

    def _ms(a):
        arr = np.asarray(a, dtype=float)
        if not len(arr):
            return 0.0, 0.0, 0
        return float(arr.mean()), float((arr > 0).mean()), len(arr)

    rows: list[RegimeEdge] = []
    for r in regimes:
        sr, sw, nn, br, bw = {}, {}, {}, {}, {}
        for f in fwds:
            m, w, k = _ms(sig_acc[r][f])
            bm, bwn, _ = _ms(base_acc[r][f])
            sr[f], sw[f], nn[f] = m, w, k
            br[f], bw[f] = bm, bwn
        rows.append(RegimeEdge(r, nn, sr, sw, br, bw))
    return rows


def format_regime_edge(rows: list[RegimeEdge], fwds=DEFAULT_FWDS) -> str:
    lines = [
        "=" * 86,
        "深超跌(距MA60≤-10%)信号 · 按趋势 regime 拆分前瞻收益/胜率（* = 胜率超同 regime 基准 2pp+）",
        "=" * 86,
    ]
    for r in rows:
        rel = "<" if r.regime == "弱势" else "≥"
        lines.append(f"[{r.regime}(close{rel}MA120)]")
        lines.append(f"  {'窗口':<6}{'信号收益/胜率/样本':<26}{'基准收益/胜率':<20}{'edge':<8}")
        for f in fwds:
            edge = (r.sig_win[f] - r.base_win[f]) * 100
            flag = "*" if edge > 2 else " "
            lines.append(
                f"  {f:<6}"
                f"{f'{r.sig_ret[f]*100:+.2f}%/{r.sig_win[f]*100:.0f}%/{r.n[f]}':<26}"
                f"{f'{r.base_ret[f]*100:+.2f}%/{r.base_win[f]*100:.0f}%':<20}"
                f"{f'{edge:+.1f}pp{flag}':<8}"
            )
    return "\n".join(lines)


# ── 研究四：商品期货 CTA 趋势/动量（净夏普, 含波动率目标）─────────────────
# 实证(2026-06-29, 29 商品主力连续 ≈8 年): 股票里趋势是灾难, 但商品里 MA20/60
# 趋势扣费后净夏普 0.28、+波动率目标(年化15%)升至 0.51/回撤-8.6%; 且弱势段(商品
# 指数<MA120) CTA 仍 +0.9% 而纯多 -19.3% —— 趋势跟随的"危机 alpha"。TSMOM 高换手
# 扣费后转负。详见 docs / cli cta。

ANN_DAYS = 252
DEFAULT_CTA_COST = 0.0003      # 单边换手成本(手续费+滑点), liquid 期货约 2-4bps
DEFAULT_TARGET_VOL = 0.15      # 波动率目标(年化)


@dataclass
class CtaResult:
    label: str
    gross_sharpe: float
    net_sharpe: float
    net_cagr: float
    net_maxdd: float
    n_inst: int


def _ann_sharpe(r: np.ndarray) -> float:
    r = np.asarray(r, float)
    r = r[~np.isnan(r)]
    return float(r.mean() / r.std() * np.sqrt(ANN_DAYS)) if len(r) and r.std() > 0 else 0.0


def _cagr_from_eq(eq: np.ndarray) -> float:
    if not len(eq) or eq[-1] <= 0:
        return -1.0
    return float(eq[-1] ** (ANN_DAYS / len(eq)) - 1.0)


def _max_drawdown(eq: np.ndarray) -> float:
    if not len(eq):
        return 0.0
    peak = np.maximum.accumulate(eq)
    return float((eq / peak - 1.0).min())


def _cta_signals(close: pd.Series) -> dict[str, pd.Series]:
    """各 CTA 信号的离散方向序列 (-1/0/+1)；波动率目标缩放交由 FuturesBacktester 处理。"""
    out: dict[str, pd.Series] = {}
    for n in (20, 60):
        out[f"TSMOM{n}"] = np.sign(close.pct_change(n))
    out["MA20/60"] = np.sign(close.rolling(20).mean() - close.rolling(60).mean())
    hi, lo = close.rolling(20).max(), close.rolling(20).min()
    don = pd.Series(np.nan, index=close.index)
    don[close >= hi] = 1.0
    don[close <= lo] = -1.0
    out["Donchian20"] = don.ffill().fillna(0.0)
    out["买入持有(纯多)"] = pd.Series(1.0, index=close.index)
    return out


def futures_cta_table(prices_map: dict[str, pd.DataFrame],
                      cost: float = DEFAULT_CTA_COST,
                      target_vol: float = DEFAULT_TARGET_VOL) -> list[CtaResult]:
    """商品/股指期货 CTA 信号等权组合的「毛/净(扣换手成本)」绩效。不联网。

    用正式 FuturesBacktester（双向做空+保证金/杠杆、收益率口径逐日盯市）逐品种回测，
    组合=等权各品种净收益。"MA20/60+波动目标" 行用引擎的波动率目标(年化 target_vol)缩放仓位。
    返回按净夏普降序的 CtaResult 列表。
    """
    from .engine.futures_backtest import FuturesBacktestConfig, FuturesBacktester

    labels = ["TSMOM20", "TSMOM60", "MA20/60", "Donchian20", "买入持有(纯多)", "MA20/60+波动目标"]
    bt_g = FuturesBacktester(FuturesBacktestConfig(cost=0.0))
    bt_n = FuturesBacktester(FuturesBacktestConfig(cost=cost))
    bt_gv = FuturesBacktester(FuturesBacktestConfig(cost=0.0, target_vol=target_vol))
    bt_nv = FuturesBacktester(FuturesBacktestConfig(cost=cost, target_vol=target_vol))

    gross_cols: dict[str, list] = {s: [] for s in labels}
    net_cols: dict[str, list] = {s: [] for s in labels}
    for code, df in prices_map.items():
        sig = _cta_signals(df["close"])
        for s in labels:
            base = sig["MA20/60"] if s == "MA20/60+波动目标" else sig[s]
            g_bt, n_bt = (bt_gv, bt_nv) if s == "MA20/60+波动目标" else (bt_g, bt_n)
            gross_cols[s].append(g_bt.run(df, base).returns.rename(code))
            net_cols[s].append(n_bt.run(df, base).returns.rename(code))

    rows: list[CtaResult] = []
    for s in labels:
        gp = pd.concat(gross_cols[s], axis=1).mean(axis=1).fillna(0.0)
        npf = pd.concat(net_cols[s], axis=1).mean(axis=1).fillna(0.0)
        eq = (1.0 + npf).cumprod().to_numpy()
        rows.append(CtaResult(
            label=s,
            gross_sharpe=_ann_sharpe(gp.to_numpy()),
            net_sharpe=_ann_sharpe(npf.to_numpy()),
            net_cagr=_cagr_from_eq(eq),
            net_maxdd=_max_drawdown(eq),
            n_inst=len(net_cols[s]),
        ))
    rows.sort(key=lambda r: -r.net_sharpe)
    return rows


def format_futures_cta(rows: list[CtaResult], cost: float = DEFAULT_CTA_COST) -> str:
    lines = [
        "=" * 76,
        f"商品期货 CTA 信号 · 等权组合毛/净绩效（成本 {cost*1e4:.0f}bps/换手 · 按净夏普排序）",
        "=" * 76,
        f"{'信号':<18}{'毛夏普':>9}{'净夏普':>9}{'净年化':>9}{'净回撤':>9}{'品种数':>7}",
    ]
    for r in rows:
        lines.append(f"{r.label:<18}{r.gross_sharpe:>9.2f}{r.net_sharpe:>9.2f}"
                     f"{r.net_cagr*100:>8.1f}%{r.net_maxdd*100:>8.1f}%{r.n_inst:>7}")
    lines.append("-" * 76)
    lines.append("实证: 商品 MA20/60 趋势扣费后净夏普为正且+波动目标显著增厚, 弱势段是危机 alpha; "
                 "TSMOM 高换手扣费转负。")
    return "\n".join(lines)


def load_futures_universe(days_back: int = 2900, min_bars: int = 300,
                          universe: str = "commodity") -> dict[str, pd.DataFrame]:
    """加载期货主力连续真实日线（akshare 新浪源）。需联网。

    universe: "commodity"(商品) | "index"(股指 IF/IC/IH/IM) | "all"(两者)。
    """
    from datetime import datetime, timedelta

    from .data.base import BarRequest, get_feed
    from .data.futures_cn import COMMODITY_FUTURES, INDEX_FUTURES

    syms = {
        "commodity": COMMODITY_FUTURES,
        "index": INDEX_FUTURES,
        "all": COMMODITY_FUTURES + INDEX_FUTURES,
    }.get(universe, COMMODITY_FUTURES)

    feed = get_feed("futures_cn")
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=days_back)).strftime("%Y%m%d")
    out: dict[str, pd.DataFrame] = {}
    for code, name in syms:
        try:
            df = feed.history(BarRequest(symbol=code, start=start, end=end))
            if len(df) >= min_bars:
                out[code] = df
        except Exception as e:
            logger.warning("期货加载失败 %s %s: %s", code, name, e)
    return out


# ── 研究五：期货 CTA regime 拆分(危机 alpha) + 参数寻优 ──────────────────

def futures_cta_regime(prices_map: dict[str, pd.DataFrame], fast: int = 20, slow: int = 60,
                       cost: float = DEFAULT_CTA_COST, target_vol: float = DEFAULT_TARGET_VOL,
                       ma_regime: int = 120) -> dict[str, dict]:
    """MA(fast/slow)+波动目标 净收益按"等权指数 regime(指数 vs MA{ma_regime})"拆强/弱势，对照纯多。

    展示 CTA 的危机 alpha：弱势段趋势(可做空)是否跑赢纯多。用 FuturesBacktester。不联网。
    """
    from .engine.futures_backtest import FuturesBacktestConfig, FuturesBacktester

    bt = FuturesBacktester(FuturesBacktestConfig(cost=cost, target_vol=target_vol))
    bt_long = FuturesBacktester(FuturesBacktestConfig(cost=cost))
    cta_cols, bh_cols, ret_cols = [], [], []
    for code, df in prices_map.items():
        close = df["close"]
        sig = np.sign(close.rolling(fast).mean() - close.rolling(slow).mean())
        cta_cols.append(bt.run(df, sig).returns.rename(code))
        bh_cols.append(bt_long.run(df, pd.Series(1.0, index=df.index)).returns.rename(code))
        ret_cols.append(close.pct_change().rename(code))

    idx = (1.0 + pd.concat(ret_cols, axis=1).mean(axis=1).fillna(0.0)).cumprod()
    strong = idx >= idx.rolling(ma_regime).mean()
    cta = pd.concat(cta_cols, axis=1).mean(axis=1).fillna(0.0)
    bh = pd.concat(bh_cols, axis=1).mean(axis=1).fillna(0.0)
    out: dict[str, dict] = {}
    for reg, mask in (("强势(指数≥MA120)", strong), ("弱势(指数<MA120)", ~strong)):
        m = mask.reindex(cta.index).fillna(False).to_numpy()
        out[reg] = {
            "share": float(m.mean()),
            "cta_sharpe": _ann_sharpe(cta.to_numpy()[m]),
            "cta_ann": float(cta.to_numpy()[m].mean() * ANN_DAYS) if m.any() else 0.0,
            "bh_sharpe": _ann_sharpe(bh.to_numpy()[m]),
            "bh_ann": float(bh.to_numpy()[m].mean() * ANN_DAYS) if m.any() else 0.0,
        }
    return out


def format_futures_cta_regime(out: dict[str, dict]) -> str:
    lines = [
        "=" * 76,
        "CTA(MA20/60+波动目标) 按指数 regime 拆分 · 危机 alpha 检验",
        "=" * 76,
        f"{'Regime':<20}{'占比':>7}{'CTA夏普/年化':>18}{'纯多夏普/年化':>18}",
    ]
    for reg, d in out.items():
        cta = f"{d['cta_sharpe']:.2f}/{d['cta_ann'] * 100:+.1f}%"
        bh = f"{d['bh_sharpe']:.2f}/{d['bh_ann'] * 100:+.1f}%"
        lines.append(f"{reg:<20}{d['share'] * 100:>6.0f}%{cta:>18}{bh:>18}")
    lines.append("弱势段 CTA 跑赢纯多 = 趋势(可做空)的危机 alpha / 对冲价值。")
    return "\n".join(lines)


def futures_cta_sweep(prices_map: dict[str, pd.DataFrame],
                      fasts=(10, 20, 40), slows=(60, 120, 200),
                      target_vols=(0.10, 0.15, 0.20),
                      cost: float = DEFAULT_CTA_COST) -> list[tuple[str, float, float, float]]:
    """扫 MA 快/慢窗口 × 波动率目标，返回按净夏普降序的 (配置名, 净夏普, 净年化, 净回撤)。

    用 FuturesBacktester(双向+波动目标)逐品种回测后等权组合。不联网。
    """
    from .engine.futures_backtest import FuturesBacktestConfig, FuturesBacktester

    results: list[tuple[str, float, float, float]] = []
    for fast in fasts:
        for slow in slows:
            if fast >= slow:
                continue
            for tv in target_vols:
                bt = FuturesBacktester(FuturesBacktestConfig(cost=cost, target_vol=tv))
                cols = []
                for code, df in prices_map.items():
                    close = df["close"]
                    sig = np.sign(close.rolling(fast).mean() - close.rolling(slow).mean())
                    cols.append(bt.run(df, sig).returns.rename(code))
                port = pd.concat(cols, axis=1).mean(axis=1).fillna(0.0)
                eq = (1.0 + port).cumprod().to_numpy()
                results.append((f"MA{fast}/{slow}+vt{tv*100:.0f}%",
                                _ann_sharpe(port.to_numpy()), _cagr_from_eq(eq), _max_drawdown(eq)))
    results.sort(key=lambda x: -x[1])
    return results


def format_futures_cta_sweep(rows: list[tuple[str, float, float, float]], top: int = 10) -> str:
    lines = [
        "=" * 64,
        f"商品期货 CTA 参数寻优 (按净夏普 Top {top})",
        "=" * 64,
        f"{'配置':<22}{'净夏普':>9}{'净年化':>10}{'净回撤':>10}",
    ]
    for name, sh, cagr, dd in rows[:top]:
        lines.append(f"{name:<22}{sh:>9.2f}{cagr*100:>9.1f}%{dd*100:>9.1f}%")
    return "\n".join(lines)


# ── 研究六：deep_dip 策略滚动样本外回测 ─────────────────────────────

@dataclass
class DeepDipWalkForwardRow:
    """单标的 deep_dip 滚动 OOS 窗口绩效."""
    symbol: str
    n_folds: int
    avg_return: float
    avg_sharpe: float
    avg_win_rate: float
    beat_bh: int


@dataclass
class DeepDipWalkForwardReport:
    """deep_dip 策略 walk-forward 汇总."""
    strategy_params: dict
    train_bars: int
    test_bars: int
    step_bars: int
    rows: list[DeepDipWalkForwardRow]
    avg_return: float = 0.0
    avg_sharpe: float = 0.0
    avg_win_rate: float = 0.0

    def to_dict(self) -> dict:
        return {
            "strategy_params": self.strategy_params,
            "train_bars": self.train_bars,
            "test_bars": self.test_bars,
            "step_bars": self.step_bars,
            "avg_return": round(self.avg_return, 4),
            "avg_sharpe": round(self.avg_sharpe, 4),
            "avg_win_rate": round(self.avg_win_rate, 4),
            "symbols": [r.__dict__ for r in self.rows],
        }


def synth_prices_map(n: int = 400, seeds: tuple[int, ...] = (1, 2)) -> dict[str, pd.DataFrame]:
    """合成 OHLCV 字典（研究/测试用, 不联网）。"""
    out: dict[str, pd.DataFrame] = {}
    for i, seed in enumerate(seeds):
        rng = np.random.default_rng(seed)
        close = np.linspace(10.0, 20.0, n) + rng.normal(0, 0.3, n).cumsum() * 0.1
        for j in range(80, n, 70):
            close[j : j + 5] *= 0.85
        close = np.maximum(close, 1.0)
        idx = pd.date_range("2020-01-01", periods=n, freq="B")
        sym = chr(65 + i) * 3
        out[sym] = pd.DataFrame(
            {
                "open": close * 0.998,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
            },
            index=idx,
        )
    return out


def deep_dip_walk_forward(
    prices_map: dict[str, pd.DataFrame],
    *,
    train_bars: int = 200,
    test_bars: int = 60,
    step_bars: int = 30,
    strategy_params: dict | None = None,
) -> DeepDipWalkForwardReport:
    """对 deep_dip 策略做滚动 OOS 回测（规则策略无拟合，train 窗口仅作暖机）。

    每个 fold: 暖机 train_bars → 在随后 test_bars 上跑 Backtester，步进 step_bars。
    不联网；用于验证唯一实证 edge 策略在样本外的稳定性。
    """
    params = strategy_params or {
        "ma_long": 60, "ma_exit": 20, "entry_dev": -0.10, "exit_dev": 0.0, "max_hold": 60,
    }
    bt = Backtester(risk=RiskConfig(), sizing=SizingConfig())
    def strat_factory():
        return get_strategy("deep_dip", **params)

    rows: list[DeepDipWalkForwardRow] = []
    for code, p in prices_map.items():
        n = len(p)
        min_len = train_bars + test_bars + 10
        if n < min_len:
            continue
        fold_rets, fold_shs, fold_wins, beat = [], [], [], 0
        folds = 0
        bh_full = float(p["close"].iloc[-1] / p["close"].iloc[0] - 1)
        for start in range(0, n - min_len + 1, step_bars):
            seg = p.iloc[start : start + train_bars + test_bars]
            warm, test = seg.iloc[:train_bars], seg.iloc[train_bars:]
            if len(test) < test_bars // 2:
                continue
            try:
                strat = strat_factory()
                res = bt.run(test, strat)
            except Exception as e:
                logger.debug("deep_dip wf %s fold@%s: %s", code, start, e)
                continue
            st = res.stats
            fold_rets.append(st.get("total_return", 0.0))
            fold_shs.append(st.get("sharpe", 0.0))
            ts = res.trade_stats or {}
            if ts.get("n_round_trips", 0) > 0:
                fold_wins.append(ts.get("win_rate", 0.0))
            if st.get("total_return", 0.0) > bh_full / max(1, (n // test_bars)):
                beat += 1
            folds += 1
        if folds == 0:
            continue
        rows.append(DeepDipWalkForwardRow(
            symbol=code,
            n_folds=folds,
            avg_return=float(np.mean(fold_rets)),
            avg_sharpe=float(np.mean(fold_shs)),
            avg_win_rate=float(np.mean(fold_wins)) if fold_wins else 0.0,
            beat_bh=beat,
        ))

    avg_ret = float(np.mean([r.avg_return for r in rows])) if rows else 0.0
    avg_sh = float(np.mean([r.avg_sharpe for r in rows])) if rows else 0.0
    avg_wr = float(np.mean([r.avg_win_rate for r in rows])) if rows else 0.0
    return DeepDipWalkForwardReport(
        strategy_params=params,
        train_bars=train_bars,
        test_bars=test_bars,
        step_bars=step_bars,
        rows=rows,
        avg_return=avg_ret,
        avg_sharpe=avg_sh,
        avg_win_rate=avg_wr,
    )


def format_deep_dip_walk_forward(report: DeepDipWalkForwardReport) -> str:
    lines = [
        "=" * 72,
        "deep_dip 策略滚动样本外回测 (暖机+测试窗口)",
        "=" * 72,
        f"参数: {report.strategy_params}",
        f"暖机={report.train_bars} 测试={report.test_bars} 步进={report.step_bars}",
        f"{'标的':<8}{'折数':>6}{'均收益':>10}{'均夏普':>10}{'均胜率':>10}{'跑赢':>8}",
    ]
    for r in report.rows:
        lines.append(
            f"{r.symbol:<8}{r.n_folds:>6}{r.avg_return*100:>9.1f}%"
            f"{r.avg_sharpe:>10.2f}{r.avg_win_rate*100:>9.0f}%{r.beat_bh:>8}"
        )
    lines.append("-" * 72)
    lines.append(
        f"{'汇总':<8}{len(report.rows):>6}{report.avg_return*100:>9.1f}%"
        f"{report.avg_sharpe:>10.2f}{report.avg_win_rate*100:>9.0f}%"
    )
    return "\n".join(lines)
