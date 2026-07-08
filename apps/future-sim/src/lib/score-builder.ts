// ============================================================
// 简化评分 → 完整 ScoreProfile（回测 / benchmark 共用）
// ============================================================

import type { ScoreProfile } from '@/types'

export interface PreLaunchScores {
  clarity: number
  pain: number
  retention: number
  distribution: number
  /** 案例库原始竞争压力 0-100（越高越红海） */
  competitionPressure?: number
  /** 差异化分数 0-100 */
  differentiation?: number
}

export function buildScoreProfileFromPreLaunch(pre: PreLaunchScores): ScoreProfile {
  const clarity = pre.clarity
  const pain = pre.pain
  const retention = pre.retention
  const distribution = pre.distribution

  // 从四维分推断市场风险（回测扩展案例校准）
  let competitionIntensity = pre.competitionPressure ?? 50
  let substitutionRisk = 40
  let copycatRisk = 40
  let platformDependency = 30
  let legalRisk = 10
  let founderDependency = 35
  const differentiation = pre.differentiation ?? clarity

  if (pre.competitionPressure === undefined) {
    if (pain < 35) {
      competitionIntensity = Math.max(competitionIntensity, 82)
      substitutionRisk = Math.max(substitutionRisk, 78)
    }

    // 高分发低留存：护城河薄（Jasper / GPT wrapper 类）
    if (distribution >= 75 && retention < 58) {
      substitutionRisk = Math.max(substitutionRisk, 85)
      copycatRisk = Math.max(copycatRisk, 78)
      platformDependency = Math.max(platformDependency, 68)
    }

    if (distribution >= 65 && retention < distribution - 12) {
      competitionIntensity = Math.max(competitionIntensity, 70)
      substitutionRisk = Math.max(substitutionRisk, 65)
    }

    // 可穿戴/硬件红海（Pebble / Jawbone；排除高分发 SaaS）
    if (pain >= 50 && pain <= 70 && retention >= 50 && retention <= 60 && distribution >= 60 && distribution < 75) {
      competitionIntensity = Math.max(competitionIntensity, 80)
      substitutionRisk = Math.max(substitutionRisk, 75)
    }

    // 大厂跟进赛道（CodeWhisperer / Vine 类）
    if (clarity >= 72 && distribution >= 65 && pain >= 58 && pain <= 72) {
      competitionIntensity = Math.max(competitionIntensity, 74)
      copycatRisk = Math.max(copycatRisk, 72)
    }

    // 监管/模式风险（Zenefits 类 HR 合规；收窄区间避免误伤高成长 SaaS）
    if (
      clarity >= 78 && pain >= 65 && pain <= 75 &&
      retention >= 70 && retention <= 78 &&
      distribution >= 60 && distribution <= 68
    ) {
      legalRisk = Math.max(legalRisk, 55)
    }

    // 重资产/模式风险（WeWork 类：高分但 lease-heavy）
    if (
      clarity >= 82 && pain >= 70 && pain <= 78 &&
      retention >= 74 && retention <= 82 &&
      distribution >= 68 && distribution <= 72
    ) {
      legalRisk = Math.max(legalRisk, 58)
      founderDependency = Math.max(founderDependency, 65)
    }
  }

  return {
    artifact: {
      quality: clarity,
      originality: clarity,
      clarity,
      usability: clarity,
      emotionalHook: Math.round(clarity * 0.8 + pain * 0.2),
      differentiation,
      completeness: clarity,
      reliability: clarity,
      aestheticQuality: clarity,
      problemSolutionFit: Math.round(clarity * 0.5 + pain * 0.5),
    },
    market: {
      marketSize: 65,
      audiencePain: pain,
      willingnessToPay: Math.round(pain * 0.8),
      trendFit: 60,
      timingScore: 60,
      competitionIntensity,
      substitutionRisk,
      platformDependency,
      regulatoryRisk: legalRisk > 20 ? legalRisk : 15,
      categoryGrowth: 55,
    },
    distribution: {
      shareability: distribution,
      viralityPotential: distribution,
      storyValue: Math.round(distribution * 0.9),
      socialProofPotential: Math.round(distribution * 0.8),
      creatorReputation: 50,
      distributionPower: distribution,
      communityPotential: Math.round(distribution * 0.85),
      mediaFriendliness: distribution,
      recommendationFit: Math.round(distribution * 0.9),
      visualSpreadPower: Math.round(distribution * 0.8),
    },
    retention: {
      activationRatePotential: retention,
      firstSessionValue: retention,
      retentionPotential: retention,
      habitPotential: Math.round(retention * 0.9),
      networkEffect: Math.round(retention * 0.7),
      switchingCost: Math.round(retention * 0.6),
      longTermValue: retention,
      updateVelocity: Math.round(retention * 0.8),
      feedbackLoopStrength: Math.round(retention * 0.75),
      communityLockIn: Math.round(retention * 0.65),
    },
    business: {
      monetizationFit: Math.round(pain * 0.6 + clarity * 0.4),
      pricingPower: Math.round(pain * 0.5 + clarity * 0.3),
      arpuPotential: Math.round(pain * 0.5),
      conversionPotential: Math.round(clarity * 0.5 + pain * 0.3),
      upsellPotential: Math.round(pain * 0.4),
      enterprisePotential: Math.round(clarity * 0.4),
      lowCostDistribution: distribution,
      grossMarginPotential: 60,
      lifecycleValue: Math.round(retention * 0.6 + pain * 0.3),
      revenueDiversity: 40,
    },
    risk: {
      executionRisk: Math.round(100 - clarity * 0.5 - retention * 0.3),
      technicalDebt: 30,
      churnRisk: Math.round(100 - retention),
      negativeFeedbackRisk: Math.round(100 - clarity * 0.4 - pain * 0.3),
      copycatRisk,
      scalabilityRisk: 35,
      maintenanceBurden: 30,
      legalRisk,
      platformBanRisk: Math.round(30),
      founderDependency,
    },
  }
}
