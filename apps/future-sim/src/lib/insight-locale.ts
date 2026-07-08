// ============================================================
// insight-locale — 切换界面语言后按新语言重建产品诊断报告
// ------------------------------------------------------------
// 背景：诊断叙事（diagnosisSummary / deathReasons / roadmap 等）在
// 模拟运行时按"当时的界面语言"生成并固化进 SimulationResult；用户
// 事后切换语言只会翻译 UI 标签，报告正文仍是旧语言（英文界面下大段
// 中文）。buildProductInsightReport 是纯函数、只依赖已存的统计结果，
// 因此无需重跑蒙特卡洛，直接用新 locale 重建即可。
// ============================================================

import type { Locale } from './i18n/types.ts'
import type { ArtifactProfile, ScoreProfile, SimulationResult, ProductInsightReport } from '../types'
import { buildProductInsightReport } from './product-insight-report.ts'
import { getInsightTexts } from './i18n/insight-texts.ts'
import { getTierForMode } from './simulation-tiers.ts'
import { computeCompositeScore } from '../workers/simulator.ts'

/** 与 worker 侧 trimInsightToSummary 保持一致的基础区裁剪 */
function trimToSummary(insight: ProductInsightReport): ProductInsightReport {
  return {
    ...insight,
    deathReasons: insight.deathReasons.slice(0, 2),
    successOpportunities: insight.successOpportunities.slice(0, 1),
    improvementPlan: insight.improvementPlan.slice(0, 1),
    optimizationStrategies: [],
    actionRoadmap: [],
  }
}

/** worker 侧 biggestOpportunity 的同款四语判定（保持口径一致） */
function pickBiggestOpportunity(composite: { painScore: number; distributionScore: number }, locale: Locale): string {
  return composite.painScore > composite.distributionScore
    ? (locale === 'zh-CN' ? '痛点强，有长期复利潜力，需强化留存和分发' : locale === 'ja-JP' ? 'ペイン強・長期複利の余地、リテンションと配信を強化' : locale === 'ko-KR' ? '페인 강함·장기 복리 잠재, 리텐션·유통 강화' : 'Strong pain; compound potential—boost retention & distribution')
    : (locale === 'zh-CN' ? '分发有优势，需强化产品价值和留存' : locale === 'ja-JP' ? '配信に優位、プロダクト価値とリテンションを強化' : locale === 'ko-KR' ? '유통 우위, 제품 가치·리텐션 강화' : 'Distribution edge—strengthen value & retention')
}

/**
 * 按目标语言重建结果中的语言相关内容（诊断报告 + 核心判断 + 风险文本），
 * 返回替换后的 result 浅拷贝；无法重建（旧存档字段不齐）时返回原 result。
 * 不重跑蒙特卡洛，仅重新生成文本层。
 */
export function localizeResult(
  result: SimulationResult,
  scores: ScoreProfile,
  profile: ArtifactProfile | null,
  locale: Locale,
): SimulationResult {
  if (!result.productInsight) return result
  try {
    const composite = computeCompositeScore(scores)
    const txt = getInsightTexts(locale)
    const op = result.outcomeProbabilities

    // 风险文本三件套按 worker 侧同款规则用新语言重算
    const riskAnalysis = {
      ...result.riskAnalysis,
      topFailureReason: txt.riskTopFailure(composite),
      mostLikelyCrashTime: op.dead > 0.5 ? txt.crashPhases.p1 :
        op.dead > 0.3 ? txt.crashPhases.p2 :
        op.lowAlive > 0.3 ? txt.crashPhases.p3 : txt.crashPhases.p4,
      mostVulnerableVariable: txt.riskVulnerable(composite),
    }

    // coreJudgment 的语言相关字段重算；worthInvesting 为纯布尔，沿用原值
    const coreJudgment = {
      mostLikelyOutcome: txt.pickOutcome(op),
      biggestOpportunity: pickBiggestOpportunity(composite, locale),
      biggestRisk: riskAnalysis.topFailureReason,
      worthInvesting: result.coreJudgment.worthInvesting,
      topOptimizationDirection:
        composite.retentionScore < composite.distributionScore ? txt.dims.retention :
          composite.painScore < 50 ? txt.dims.pain : txt.dims.distribution,
    }

    const full = buildProductInsightReport({
      scores,
      composite,
      outcomeProbabilities: op,
      ranking: result.ranking,
      riskAnalysis,
      sensitivity: result.sensitivity,
      strategyComparison: result.strategyComparison,
      optimizationSuggestions: result.optimizationSuggestions,
      coreJudgment,
      confidence: result.confidence,
      profile,
      locale,
    })

    const tier = getTierForMode(result.config.mode)
    const productInsight = tier.insightLevel === 'summary' ? trimToSummary(full) : full

    // 与 worker 收尾逻辑一致：首要死因以诊断报告为准
    riskAnalysis.topFailureReason = productInsight.deathReasons[0]?.title ?? riskAnalysis.topFailureReason
    coreJudgment.biggestRisk = riskAnalysis.topFailureReason

    return { ...result, productInsight, coreJudgment, riskAnalysis }
  } catch {
    // 旧版本存档字段不齐时安全回退，不影响页面渲染
    return result
  }
}
