// ============================================================
// 动态优化建议 — 按敏感性排序生成
// ============================================================

import type { OutcomeProbabilities, OptimizationSuggestion, RankingStats, SensitivityResult } from '../types'
import { VARIABLE_NAMES } from './utils.ts'

const VAR_META: Record<string, Omit<OptimizationSuggestion, 'priority' | 'impactOnSuccess' | 'impactOnFailure'>> = {
  audiencePain: {
    title: '强化痛点与问题匹配',
    whyImportant: '痛点强度是最强预测变量，决定用户是否愿意尝试和留存',
    whatToChange: '聚焦核心用户痛点、强化问题-方案匹配、用案例证明价值',
    howToVerify: '用户访谈 + 落地页转化 A/B',
    metricToWatch: '首日转化率',
  },
  clarity: {
    title: '提升清晰度与首屏表达',
    whyImportant: '清晰度直接影响用户理解和转化，通常是最高 ROI 优化项',
    whatToChange: '优化首屏表达、标题、卖点说明，完成 5 秒理解测试',
    howToVerify: 'A/B 测试不同版本首屏，监控首日转化率',
    metricToWatch: '首日转化率',
  },
  retentionPotential: {
    title: '强化留存与习惯回路',
    whyImportant: '留存是长期复利的基础，D7 留存是最关键指标之一',
    whatToChange: '增加习惯形成机制、通知提醒、成长系统、工作流绑定',
    howToVerify: '监控 D7/D30 留存率，追踪用户回访频率',
    metricToWatch: 'D7 留存',
  },
  distributionPower: {
    title: '优化分发与获客渠道',
    whyImportant: '分发是增长引擎，但需与留存匹配，避免虚火',
    whatToChange: '增加分享钩子、SEO、社区建设、内容营销',
    howToVerify: '追踪各渠道获客成本和转化率',
    metricToWatch: '各渠道获客成本',
  },
  differentiation: {
    title: '强化差异化定位',
    whyImportant: '红海赛道中差异化决定用户为何选你而非竞品',
    whatToChange: '明确唯一差异点，写入定价页、onboarding 与 demo',
    howToVerify: '竞品对比访谈 + 流失用户问卷',
    metricToWatch: '竞品切换率',
  },
  monetizationFit: {
    title: '验证商业化路径',
    whyImportant: '有用户无收入仍会死在现金流上',
    whatToChange: '定义免费/付费边界，测试定价梯度与试用策略',
    howToVerify: '追踪试用→付费漏斗与 ARPU',
    metricToWatch: '付费转化率',
  },
  shareability: {
    title: '提升可分享性与传播',
    whyImportant: '可分享产出物能降低获客成本、加速冷启动',
    whatToChange: '设计可分享的结果页/徽章/邀请机制',
    howToVerify: '监控分享率与邀请注册占比',
    metricToWatch: '分享率',
  },
  technicalDebt: {
    title: '偿还关键路径技术债',
    whyImportant: '稳定性与迭代速度直接影响口碑与留存',
    whatToChange: '优先修复首体验路径崩溃与性能瓶颈',
    howToVerify: '崩溃率、P95 延迟、发布频率',
    metricToWatch: '崩溃率',
  },
}

function pctDelta(a: number, b: number): string {
  const d = (a - b) * 100
  return `${d >= 0 ? '+' : ''}${d.toFixed(1)}%`
}

export function buildDynamicOptimizationSuggestions(
  sensitivity: SensitivityResult[],
  ranking: RankingStats,
  op: OutcomeProbabilities,
): OptimizationSuggestion[] {
  const sorted = [...sensitivity].sort((a, b) => a.optimizationPriority - b.optimizationPriority)
  const top = sorted.slice(0, 5)

  return top.map((s, i) => {
    const meta = VAR_META[s.variable] ?? {
      title: `优化${VARIABLE_NAMES[s.variable] ?? s.variable}`,
      whyImportant: `该变量对模拟结果影响强度 ${(s.impactStrength * 100).toFixed(0)}%`,
      whatToChange: `将${VARIABLE_NAMES[s.variable] ?? s.variable}从 ${s.originalValue} 提升约 15 分`,
      howToVerify: '对比优化前后死亡概率与 Top10% 概率',
      metricToWatch: 'Top10% 概率',
    }

    return {
      priority: i + 1,
      ...meta,
      impactOnSuccess: `Top10% 概率 ${pctDelta(s.top10AfterIncrease, ranking.top10)}`,
      impactOnFailure: `死亡概率 ${pctDelta(s.deathProbAfterIncrease, op.dead)}`,
    }
  })
}
