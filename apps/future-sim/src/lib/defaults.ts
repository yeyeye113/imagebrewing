// ============================================================
// Default score profiles
// ============================================================

import type { ScoreProfile } from '@/types'

export function createDefaultScores(): ScoreProfile {
  return {
    artifact: {
      quality: 50,
      originality: 50,
      clarity: 50,
      usability: 50,
      emotionalHook: 50,
      differentiation: 50,
      completeness: 50,
      reliability: 50,
      aestheticQuality: 50,
      problemSolutionFit: 50,
    },
    market: {
      marketSize: 50,
      audiencePain: 50,
      willingnessToPay: 50,
      trendFit: 50,
      timingScore: 50,
      competitionIntensity: 50,
      substitutionRisk: 50,
      platformDependency: 50,
      regulatoryRisk: 50,
      categoryGrowth: 50,
    },
    distribution: {
      shareability: 50,
      viralityPotential: 50,
      storyValue: 50,
      socialProofPotential: 50,
      creatorReputation: 50,
      distributionPower: 50,
      communityPotential: 50,
      mediaFriendliness: 50,
      recommendationFit: 50,
      visualSpreadPower: 50,
    },
    retention: {
      activationRatePotential: 50,
      firstSessionValue: 50,
      retentionPotential: 50,
      habitPotential: 50,
      networkEffect: 50,
      switchingCost: 50,
      longTermValue: 50,
      updateVelocity: 50,
      feedbackLoopStrength: 50,
      communityLockIn: 50,
    },
    business: {
      monetizationFit: 50,
      pricingPower: 50,
      arpuPotential: 50,
      conversionPotential: 50,
      upsellPotential: 50,
      enterprisePotential: 50,
      lowCostDistribution: 50,
      grossMarginPotential: 50,
      lifecycleValue: 50,
      revenueDiversity: 50,
    },
    risk: {
      executionRisk: 50,
      technicalDebt: 50,
      churnRisk: 50,
      negativeFeedbackRisk: 50,
      copycatRisk: 50,
      scalabilityRisk: 50,
      maintenanceBurden: 50,
      legalRisk: 50,
      platformBanRisk: 50,
      founderDependency: 50,
    },
  }
}

export function createDefaultExistingData() {
  return {
    exposure: 0,
    visitors: 0,
    users: 0,
    activeUsers: 0,
    revenue: 0,
    day1Retention: 0,
    day7Retention: 0,
    day30Retention: 0,
    shares: 0,
    comments: 0,
    saves: 0,
    rating: 0,
  }
}
