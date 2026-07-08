// ============================================================
// Holdout 验证集回测 — 未参与校准的案例库样本
// ============================================================

import {
  BACKTEST_CASES,
  EXTRA_SUCCESS_CASES,
  loadExpansionCases,
  runBacktest,
  calculateAccuracy,
  type BacktestRunResult,
  type AccuracyMetrics,
} from './backtest.ts'
import { buildHoldoutCases } from './case-loader.ts'
import type { SimulationConfig } from '../types/index.ts'

function calibratedNames(): string[] {
  const names = [
    ...BACKTEST_CASES,
    ...loadExpansionCases(),
    ...EXTRA_SUCCESS_CASES,
  ].map((c) => c.name)
  // 案例库中同名不同结局的条目（以校准集为准）
  names.push('Arc Browser', 'vidIQ', 'Draftss', 'marblism', 'Photopea', 'Post Bridge', 'Postiz')
  return names
}

export function getHoldoutCases() {
  return buildHoldoutCases(calibratedNames())
}

export interface CalibrationReport {
  results: BacktestRunResult[]
  accuracy: AccuracyMetrics
  lowConfidence: { name: string; actual: string; predicted: string; prob: number }[]
  summary: string
}

export function runHoldoutBacktest(config?: SimulationConfig): CalibrationReport {
  const cases = getHoldoutCases()
  const results = cases.map((c) => runBacktest(c, config))
  const accuracy = calculateAccuracy(results)

  const lowConfidence = results
    .filter((r) => r.probabilityOfActual < 0.45)
    .map((r) => ({
      name: r.caseName,
      actual: r.actualOutcome,
      predicted: r.mostLikelyOutcome,
      prob: r.probabilityOfActual,
    }))
    .sort((a, b) => a.prob - b.prob)

  const lines = [
    '=== Holdout Backtest (case library, not in calibrated set) ===',
    '',
    `Cases: ${cases.length}`,
    `Exact: ${(accuracy.exactHitRate * 100).toFixed(1)}% (${accuracy.exactHits}/${accuracy.totalCases})`,
    `Top-2: ${(accuracy.topTwoHitRate * 100).toFixed(1)}%`,
    `Avg P(actual): ${(accuracy.averagePrecision * 100).toFixed(1)}%`,
    '',
  ]

  for (const r of results) {
    const tag = r.exactMatch ? 'HIT' : r.topTwoMatch ? 'TOP-2' : 'MISS'
    lines.push(
      `[${tag}] ${r.caseName}`,
      `  Predicted: ${r.mostLikelyOutcome} (${(r.probabilityOfActual * 100).toFixed(1)}% on actual)`,
      `  Actual:    ${r.actualOutcome}`,
      '',
    )
  }

  if (lowConfidence.length > 0) {
    lines.push('=== Low confidence (P(actual) < 45%) ===', '')
    for (const lc of lowConfidence) {
      lines.push(`  ${lc.name}: pred=${lc.predicted} actual=${lc.actual} P=${(lc.prob * 100).toFixed(1)}%`)
    }
  }

  return {
    results,
    accuracy,
    lowConfidence,
    summary: lines.join('\n'),
  }
}
