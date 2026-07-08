// ============================================================
// 重算 benchmark.ts 静态用户规模尺
// 运行：node cases/backtest/calibrate_benchmark.ts
// ============================================================

import { BACKTEST_CASES, collectCaseUserMedians } from '../../src/lib/backtest.ts'
import type { SimulationConfig } from '../../src/types/index.ts'

const config: SimulationConfig = {
  runs: 400,
  periodDays: 180,
  granularity: 'week',
  mode: 'standard',
  scenarios: ['baseline'],
  strategies: ['original'],
  seed: 42,
}

const medians = collectCaseUserMedians(BACKTEST_CASES, config)

console.log('// seed=42, 400 runs, 180d — auto-calibrated')
console.log('const CASE_USER_MEDIANS = [')
for (const m of medians) {
  console.log(`  { outcome: '${m.outcome}', medianUsers: ${m.medianUsers} }, // ${m.name}`)
}
console.log(']')
