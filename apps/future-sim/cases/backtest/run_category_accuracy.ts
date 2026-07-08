// 运行：node cases/backtest/run_category_accuracy.ts

import {
  runCategoryAccuracyReport,
  formatCategoryReport,
} from '../../src/lib/category-accuracy.ts'
import { runHoldoutBacktest } from '../../src/lib/holdout-backtest.ts'
import { runExtendedBacktest } from '../../src/lib/backtest.ts'

console.log('=== 校准集 Extended ===')
console.log(`Exact: ${(runExtendedBacktest().accuracy.exactHitRate * 100).toFixed(1)}%`)
console.log('')

console.log('=== Holdout（含 Floga / Loomin）===')
const holdout = runHoldoutBacktest()
console.log(`Cases: ${holdout.results.length}`)
console.log(`Exact: ${(holdout.accuracy.exactHitRate * 100).toFixed(1)}%`)
console.log('')

for (const dataset of ['calibrated', 'holdout', 'all'] as const) {
  const report = runCategoryAccuracyReport(dataset)
  console.log(formatCategoryReport(report))
  console.log('\n---\n')
}
