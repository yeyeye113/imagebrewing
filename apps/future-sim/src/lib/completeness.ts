// ============================================================
// 数据完整度 — 评分 + 作品画像综合计算
// ============================================================

import type { ArtifactProfile, ScoreProfile } from '@/types'

const SCORE_GROUPS = ['artifact', 'market', 'distribution', 'retention', 'business', 'risk'] as const

/** 评分维度填写比例（非默认 50 视为已填写） */
export function scoreFillRatio(scores: ScoreProfile): number {
  const allValues = SCORE_GROUPS.flatMap(
    (g) => Object.values(scores[g] as unknown as Record<string, number>),
  )
  const filled = allValues.filter((v) => v !== 50).length
  return allValues.length > 0 ? filled / allValues.length : 0
}

/** 作品画像文本字段完整度 */
export function profileFillRatio(profile: ArtifactProfile | null | undefined): number {
  if (!profile) return 0
  const checks = [
    profile.name.trim().length > 0,
    profile.description.trim().length > 10,
    profile.targetUsers.trim().length > 0,
    profile.coreFeatures.length > 0,
    profile.coreSellingPoints.length > 0,
    profile.competitors.length > 0,
    profile.channelResources.trim().length > 0,
    profile.teamSize > 0,
  ]
  const ed = profile.existingData
  const hasMetrics = ed.users > 0 || ed.revenue > 0 || ed.day7Retention > 0
  checks.push(hasMetrics)
  return checks.filter(Boolean).length / checks.length
}

/** 综合完整度：评分 70% + 画像 30% */
export function computeDataCompleteness(
  scores: ScoreProfile,
  profile?: ArtifactProfile | null,
): number {
  const scorePart = scoreFillRatio(scores)
  const profilePart = profileFillRatio(profile)
  if (!profile) return Math.min(1, scorePart)
  return Math.min(1, scorePart * 0.7 + profilePart * 0.3)
}

/** 置信度：完整度 + 模拟次数 */
export function computeConfidence(
  scores: ScoreProfile,
  runs: number,
  profile?: ArtifactProfile | null,
): number {
  const completeness = computeDataCompleteness(scores, profile)
  const runsBonus = runs >= 50000 ? 0.25 : runs >= 10000 ? 0.15 : 0.08
  return Math.min(0.92, Math.max(0.05, completeness * 0.55 + runsBonus + 0.1))
}
