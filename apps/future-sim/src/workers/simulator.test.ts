// ============================================================
// Simulator Tests — 核心模拟逻辑测试
// ============================================================

import { describe, it, expect } from 'vitest'
import { computeCompositeScore } from '../workers/simulator'
import type { ScoreProfile } from '../types'

// 默认评分配置
function createDefaultScores(): ScoreProfile {
  return {
    artifact: {
      quality: 50, originality: 50, clarity: 50, usability: 50,
      emotionalHook: 50, differentiation: 50, completeness: 50,
      reliability: 50, aestheticQuality: 50, problemSolutionFit: 50,
    },
    market: {
      marketSize: 50, audiencePain: 50, willingnessToPay: 50, trendFit: 50,
      timingScore: 50, competitionIntensity: 50, substitutionRisk: 50,
      platformDependency: 50, regulatoryRisk: 50, categoryGrowth: 50,
    },
    distribution: {
      shareability: 50, viralityPotential: 50, storyValue: 50,
      socialProofPotential: 50, creatorReputation: 50, distributionPower: 50,
      communityPotential: 50, mediaFriendliness: 50, recommendationFit: 50,
      visualSpreadPower: 50,
    },
    retention: {
      activationRatePotential: 50, firstSessionValue: 50, retentionPotential: 50,
      habitPotential: 50, networkEffect: 50, switchingCost: 50, longTermValue: 50,
      updateVelocity: 50, feedbackLoopStrength: 50, communityLockIn: 50,
    },
    business: {
      monetizationFit: 50, pricingPower: 50, arpuPotential: 50, conversionPotential: 50,
      upsellPotential: 50, enterprisePotential: 50, lowCostDistribution: 50,
      grossMarginPotential: 50, lifecycleValue: 50, revenueDiversity: 50,
    },
    risk: {
      executionRisk: 50, technicalDebt: 50, churnRisk: 50, negativeFeedbackRisk: 50,
      copycatRisk: 50, scalabilityRisk: 50, maintenanceBurden: 50, legalRisk: 50,
      platformBanRisk: 50, founderDependency: 50,
    },
  }
}

describe('computeCompositeScore', () => {
  it('应该返回正确的结构', () => {
    const scores = createDefaultScores()
    const result = computeCompositeScore(scores)

    expect(result).toHaveProperty('productScore')
    expect(result).toHaveProperty('marketScore')
    expect(result).toHaveProperty('distributionScore')
    expect(result).toHaveProperty('retentionScore')
    expect(result).toHaveProperty('businessScore')
    expect(result).toHaveProperty('riskScore')
    expect(result).toHaveProperty('overall')
    expect(result).toHaveProperty('clarityScore')
    expect(result).toHaveProperty('painScore')
    expect(result).toHaveProperty('differentiationScore')
  })

  it('默认分数应该产生中等整体分数', () => {
    const scores = createDefaultScores()
    const result = computeCompositeScore(scores)

    // 所有维度都是 50，整体应该在 40-60 之间
    expect(result.overall).toBeGreaterThan(35)
    expect(result.overall).toBeLessThan(65)
  })

  it('高痛点应该提高市场分数', () => {
    const scores = createDefaultScores()
    scores.market.audiencePain = 90
    const result = computeCompositeScore(scores)

    expect(result.marketScore).toBeGreaterThan(50)
    expect(result.painScore).toBe(90)
  })

  it('高留存应该提高留存分数', () => {
    const scores = createDefaultScores()
    scores.retention.retentionPotential = 85
    scores.retention.habitPotential = 85
    const result = computeCompositeScore(scores)

    expect(result.retentionScore).toBeGreaterThan(50)
  })

  it('高清晰度应该反映在 clarityScore', () => {
    const scores = createDefaultScores()
    scores.artifact.clarity = 80
    const result = computeCompositeScore(scores)

    expect(result.clarityScore).toBe(80)
    expect(result.productScore).toBeGreaterThan(50)
  })

  it('高差异化应该反映在 differentiationScore', () => {
    const scores = createDefaultScores()
    scores.artifact.differentiation = 75
    const result = computeCompositeScore(scores)

    expect(result.differentiationScore).toBe(75)
  })

  it('低风险应该提高 riskScore', () => {
    const scores = createDefaultScores()
    // 设置所有风险为低（风险类变量越高表示风险越大）
    scores.risk.executionRisk = 10
    scores.risk.technicalDebt = 10
    scores.risk.churnRisk = 10
    const result = computeCompositeScore(scores)

    expect(result.riskScore).toBeGreaterThan(50)
  })
})

describe('分数边界', () => {
  it('所有分数为 0 应该产生合理的整体分数', () => {
    const scores = createDefaultScores()
    Object.keys(scores).forEach((key) => {
      const group = scores[key as keyof ScoreProfile]
      Object.keys(group).forEach((k) => {
        ;(group as Record<string, number>)[k] = 0
      })
    })
    // 风险类需要特殊处理
    scores.risk.executionRisk = 100
    scores.risk.technicalDebt = 100

    const result = computeCompositeScore(scores)
    expect(result.overall).toBeGreaterThan(0)
    expect(result.overall).toBeLessThan(30)
  })

  it('所有分数为 100 应该产生高整体分数', () => {
    const scores = createDefaultScores()
    Object.keys(scores).forEach((key) => {
      const group = scores[key as keyof ScoreProfile]
      Object.keys(group).forEach((k) => {
        ;(group as Record<string, number>)[k] = 100
      })
    })

    const result = computeCompositeScore(scores)
    // 由于 riskScore 的计算方式（100 - riskFactor），高风险值会拉低分数
    expect(result.overall).toBeGreaterThan(70)
  })
})
