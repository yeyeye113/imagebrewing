// ============================================================
// 真实引擎回测入口
// ============================================================
//
// 直接复用 src/lib/backtest.ts（其内部 import 真实 src/workers/simulator.ts），
// 彻底杜绝旧 run_backtest.mjs 那种"内联手抄副本与源码漂移"的问题——
// 从此回测测的就是线上同一套引擎逻辑。
//
// 运行：node cases/backtest/run_backtest.ts   （Node ≥ 22.6 原生 TS 支持）
//
import { runFullBacktest } from '../../src/lib/backtest.ts'

const { summary } = runFullBacktest()
console.log(summary)
