// ============================================================
// 扩展回测入口 — 核心 13 + expansion.json + 额外成功案例
// ============================================================
//
// 运行：node cases/backtest/run_extended_backtest.ts

import { runExtendedBacktest } from '../../src/lib/backtest.ts'

const { summary, coreAccuracy, expansionAccuracy, accuracy } = runExtendedBacktest()
console.log(summary)
console.log('')
console.log('=== Split Summary ===')
console.log(`Core:      ${(coreAccuracy.exactHitRate * 100).toFixed(1)}% exact (${coreAccuracy.exactHits}/${coreAccuracy.totalCases})`)
console.log(`Expansion: ${(expansionAccuracy.exactHitRate * 100).toFixed(1)}% exact (${expansionAccuracy.exactHits}/${expansionAccuracy.totalCases})`)
console.log(`Combined:  ${(accuracy.exactHitRate * 100).toFixed(1)}% exact (${accuracy.exactHits}/${accuracy.totalCases})`)
