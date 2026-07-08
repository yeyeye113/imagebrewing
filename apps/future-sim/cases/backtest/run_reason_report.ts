// 运行：node cases/backtest/run_reason_report.ts
// 输出：cases/backtest/prediction_reason_report.md

import { writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { runBacktest } from '../../src/lib/backtest.ts'
import { buildCalibratedCases, buildExpandedHoldoutCases } from '../../src/lib/category-accuracy.ts'
import {
  buildCaseReasonReport,
  formatFullReasonReport,
} from '../../src/lib/prediction-reason.ts'

const __dirname = dirname(fileURLToPath(import.meta.url))
const outPath = join(__dirname, 'prediction_reason_report.md')

const seen = new Set<string>()
const cases = [...buildCalibratedCases(), ...buildExpandedHoldoutCases()].filter((c) => {
  if (seen.has(c.name)) return false
  seen.add(c.name)
  return true
})

const reports = cases.map((c) => buildCaseReasonReport(c, runBacktest(c)))

const md = formatFullReasonReport(reports)
writeFileSync(outPath, md, 'utf8')

console.log(`已写入 ${outPath}`)
console.log(`案例 ${reports.length} · Exact ${reports.filter((r) => r.exactMatch).length}/${reports.length}`)
console.log(`低置信 ${reports.filter((r) => r.confidenceTier === 'low').map((r) => r.name).join(', ') || '无'}`)
