// 运行：node cases/backtest/run_holdout_backtest.ts

import { runHoldoutBacktest } from '../../src/lib/holdout-backtest.ts'
import { runExtendedBacktest, runFullBacktest } from '../../src/lib/backtest.ts'

const calibrated = runFullBacktest()
const extended = runExtendedBacktest()
const holdout = runHoldoutBacktest()

console.log('=== Calibrated Core ===')
console.log(`Exact: ${(calibrated.accuracy.exactHitRate * 100).toFixed(1)}% (${calibrated.accuracy.exactHits}/13)`)
console.log('')
console.log('=== Calibrated Extended ===')
console.log(`Exact: ${(extended.accuracy.exactHitRate * 100).toFixed(1)}% (${extended.accuracy.exactHits}/${extended.accuracy.totalCases})`)
console.log('')
console.log(holdout.summary)
