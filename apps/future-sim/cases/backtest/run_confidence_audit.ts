// 运行：node cases/backtest/run_confidence_audit.ts

import { runFullBacktest, runExtendedBacktest } from '../../src/lib/backtest.ts'
import { runHoldoutBacktest } from '../../src/lib/holdout-backtest.ts'
import type { BacktestRunResult } from '../../src/lib/backtest.ts'

function collectResults(): BacktestRunResult[] {
  const seen = new Set<string>()
  const all: BacktestRunResult[] = []
  for (const r of [
    ...runFullBacktest().results,
    ...runExtendedBacktest().results,
    ...runHoldoutBacktest().results,
  ]) {
    if (seen.has(r.caseName)) continue
    seen.add(r.caseName)
    all.push(r)
  }
  return all.sort((a, b) => a.probabilityOfActual - b.probabilityOfActual)
}

const results = collectResults()
const low = results.filter((r) => r.probabilityOfActual < 0.75)
const borderline = results.filter((r) => r.probabilityOfActual >= 0.75 && r.probabilityOfActual < 0.85)

console.log('=== Future-Sim Confidence Audit ===\n')
console.log(`Total unique cases: ${results.length}`)
console.log(`Exact: ${(results.filter((r) => r.exactMatch).length / results.length * 100).toFixed(1)}%`)
console.log(`Avg P(actual): ${(results.reduce((s, r) => s + r.probabilityOfActual, 0) / results.length * 100).toFixed(1)}%`)
console.log(`Low confidence (<75%): ${low.length}`)
console.log(`Borderline (75-85%): ${borderline.length}\n`)

if (low.length > 0) {
  console.log('--- Low confidence (exact but uncertain) ---')
  for (const r of low) {
    const tag = r.exactMatch ? 'HIT' : 'MISS'
    console.log(`[${tag}] ${r.caseName}: P=${(r.probabilityOfActual * 100).toFixed(1)}% pred=${r.mostLikelyOutcome} actual=${r.actualOutcome}`)
  }
  console.log('')
}

if (borderline.length > 0) {
  console.log('--- Borderline ---')
  for (const r of borderline) {
    console.log(`  ${r.caseName}: P=${(r.probabilityOfActual * 100).toFixed(1)}%`)
  }
}
