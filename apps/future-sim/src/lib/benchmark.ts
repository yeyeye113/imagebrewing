// ============================================================
// Benchmark 排名 — 基于案例库用户规模分位（静态校准）
// ============================================================

import type { OutcomeClass, RankingStats } from '@/types'

function clamp(v: number, min: number, max: number) {
  return Math.max(min, Math.min(max, v))
}

/** seed=42, 400 runs, 180d — node cases/backtest/calibrate_benchmark.ts 生成（v3 引擎重校准） */
const CASE_USER_MEDIANS: { outcome: OutcomeClass; medianUsers: number }[] = [
  { outcome: 'clear_success', medianUsers: 71182 },  // Lovable
  { outcome: 'long_compound', medianUsers: 85162 },  // Photopea
  { outcome: 'dead', medianUsers: 161 },             // Marblism
  { outcome: 'dead', medianUsers: 0 },               // Google Stadia
  { outcome: 'moderate_success', medianUsers: 70 },  // Post Bridge
  { outcome: 'clear_success', medianUsers: 77952 },  // Cursor
  { outcome: 'long_compound', medianUsers: 73135 },  // Notion
  { outcome: 'dead', medianUsers: 0 },               // Clubhouse
  { outcome: 'moderate_success', medianUsers: 251 }, // Arc Browser
  { outcome: 'blockbuster', medianUsers: 98147 },    // ChatGPT
  { outcome: 'clear_success', medianUsers: 77028 },  // Figma
  { outcome: 'dead', medianUsers: 0 },               // Quibi
  { outcome: 'long_compound', medianUsers: 56635 },  // Obsidian
]

/** 根据模拟中位用户数，对照案例库估算排名率 */
export function computeBenchmarkRanking(medianUsers: number): RankingStats {
  const allUsers = CASE_USER_MEDIANS.map((b) => b.medianUsers).sort((a, b) => a - b)

  let below = 0
  for (const u of allUsers) {
    if (medianUsers >= u) below++
  }
  const percentile = allUsers.length > 0 ? below / allUsers.length : 0.5

  const successMedians = CASE_USER_MEDIANS
    .filter((b) => ['moderate_success', 'clear_success', 'blockbuster', 'long_compound'].includes(b.outcome))
    .map((b) => b.medianUsers)
  const topMedians = CASE_USER_MEDIANS
    .filter((b) => ['clear_success', 'blockbuster'].includes(b.outcome))
    .map((b) => b.medianUsers)

  const successThreshold = successMedians.reduce((a, b) => a + b, 0) / (successMedians.length || 1)
  const topThreshold = topMedians.length ? Math.min(...topMedians) * 0.75 : 6000

  return {
    aboveMedian: clamp(percentile, 0, 0.98),
    top30: clamp(percentile > 0.5 ? percentile + 0.05 : percentile * 0.75, 0, 0.95),
    top20: clamp(medianUsers >= successThreshold * 0.55 ? percentile + 0.12 : percentile * 0.55, 0, 0.92),
    top10: clamp(medianUsers >= topThreshold ? percentile + 0.18 : percentile * 0.4, 0, 0.85),
    top5: clamp(medianUsers >= topThreshold * 1.15 ? percentile + 0.25 : percentile * 0.25, 0, 0.70),
    top1: clamp(medianUsers >= topThreshold * 1.8 ? percentile * 0.5 + 0.35 : percentile * 0.12, 0, 0.45),
    expectedPercentile: clamp(percentile, 0, 1),
    medianPercentile: clamp(percentile, 0, 1),
    worst5Percentile: clamp(percentile * 0.35, 0, 1),
    best5Percentile: clamp(percentile * 1.35 + 0.1, 0.5, 5),
    hasBenchmarkData: true,
  }
}
