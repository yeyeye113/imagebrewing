// ============================================================
// insight-narrative — 模拟诊断长文案（死亡原因 / 摘要 / 报告章节）
// ============================================================

import type { Locale } from './types.ts'

export interface DeathCopyBlock {
  title: string
  rootCause: string
  earlySignals: string[]
  preventionActions: string[]
}

export interface InsightNarrative {
  painScore: (n: number) => string
  painWeak: (n: number) => string
  retentionGood: (n: number) => string
  retentionWeak: (n: number) => string
  distributionGood: (n: number) => string
  distributionWeak: (n: number) => string
  clarityGood: (n: number) => string
  clarityWeak: (n: number) => string
  gapRisk: (gap: number) => string
  competitionRisk: string
  platformRisk: string
  techDebtRisk: string
  painFit: (pain: number, label: string, fit: number) => string
  distVsRet: (dist: number, ret: number, gap: number, crash: string) => string
  retentionScore: (ret: number, habit: number, first: number) => string
  channelScore: (dist: number, share: number) => string
  competitionScore: (comp: number, diff: number, sub: number, rivals?: string) => string
  platformScore: (dep: number, ban: number) => string
  monetizationScore: (fit: number, pay: number) => string
  legalScore: (legal: number, reg: number) => string
  generalRoot: string
  generalEvidence: (vuln: string, overall: number) => string
  generalEarly: string[]
  generalPrevent: string[]
  knownCompetitors: (names: string) => string
  crashWindow: (t: string) => string
  weakPain: DeathCopyBlock
  hypeMismatch: DeathCopyBlock
  retentionCollapse: DeathCopyBlock
  distributionFailure: DeathCopyBlock
  competitionShock: DeathCopyBlock
  platformRiskBlock: DeathCopyBlock
  monetizationFailure: DeathCopyBlock
  regulatory: DeathCopyBlock
  aiCommoditization: DeathCopyBlock
  headlinePublish: (outcome: string, weakest: string) => string
  headlineHighDeath: (death: string, risk: string) => string
  headlineValidate: (death: string, direction: string) => string
  diagnosisSummary: (p: {
    product: string
    type: string
    stage: string
    benchmark: boolean
    outcome: string
    death: string
    success: string
    topRisk: string
    optimize: string
    stageHint: string
    lowConf: boolean
    /** 原始死亡概率（0-1），用于按风险分档调节叙事语气；缺省时按中等风险处理 */
    deathValue?: number
  }) => string
  stageHintEarly: string
  stageHintDecline: string
  confHigh: string
  confMid: string
  confLow: string
  publishYes: string
  publishNo: string
  successOpportunities: Record<string, DeathCopyBlock & { trigger: string; actions: string[]; metrics: string[] }>
  reportSections: {
    insightSummary: string
    decisionTable: string
    publishDecision: string
    mostLikely: string
    deathProb: string
    successProb: string
    confidenceNote: string
    artifactType: string
    stage: string
    scoreDiag: string
    strengths: string
    weaknesses: string
    structuralRisks: string
    noStrength: string
    none: string
    noStructural: string
    deathAnalysis: string
    rootCause: string
    scoreEvidence: string
    earlySignals: string
    prevention: string
    growthOps: string
    trigger: string
    keyActions: string
    metricsWatch: string
    roadmap: string
    goals: string
    tasks: string
    improvements: string
    whyNow: string
    expectedImpact: string
    concreteSteps: string
    strategyRec: string
    bestFor: string
    whyRecommended: string
    execList: string
    severity: Record<string, string>
    urgency: Record<string, string>
    effort: Record<string, string>
  }
  /** 改进方案：各变量的具体步骤与监控指标 */
  improveSteps: Record<string, { steps: string[]; metrics: string[]; effort: 'low' | 'medium' | 'high' }>
  improveFallbackStep: string
  improveFallbackMetrics: string[]
  improveFallbackTitle: string
  improveWhyNowTop: string
  improveWhyNowRank: string
  improveExpectedImpact: string
  dirDown: string
  dirUp: string
  /** 策略推荐理由模板与补充语 */
  whyBase: string
  whyClarityWeak: string
  whyRetentionShort: string
  whyNeedAcquisition: string
  whyNeedMonetization: string
  whyWeakestDim: string
  markdownReport: {
    title: string
    disclaimer: string
    basicInfo: string
    project: string
    name: string
    type: string
    stage: string
    targetUsers: string
    period: string
    runs: string
    confidence: string
    completeness: string
    coreJudgment: string
    mostLikely: string
    biggestOpp: string
    biggestRisk: string
    worthInvest: string
    topOptimize: string
    yes: string
    no: string
    legacyInsight: string
    outcomeDist: string
    ranking: string
    benchmarkYes: string
    benchmarkNo: string
    forecast: string
    futurePaths: string
    failurePaths: string
    successPaths: string
    sensitivity: string
    strategyCompare: string
    optimization: string
    warnings: string
    conclusion: string
    worthPublish: string
    optimizeBeforePublish: string
    directPublish: string
    keepInvesting: string
    cautionInvest: string
    footer: string
    notFilled: string
    days: string
    /** 通用表头 */
    colOutcome: string
    colProb: string
    colIndicator: string
    colValue: string
    colMedian: string
    colVariable: string
    colScore: string
    colTop10Impact: string
    colPriority: string
    colStrategy: string
    colDeath: string
    colBlockbuster: string
    colUsers: string
    colRevenue: string
    colRecommend: string
    colHealthy: string
    colDanger: string
    colDesc: string
    /** 排名率行标签 */
    rankAboveMedian: string
    rankExpectedPctl: string
    rankMedianPctl: string
    /** 未来路径章节 */
    phase0_7: string
    phase8_30: string
    phase31_90: string
    phase91_365: string
    notCovered: string
    pathStat: string
    phaseTrend: string
    keyRisk: string
    keyOpp: string
    trendFast: string
    trendSteady: string
    trendPlateau: string
    trendDecline: string
    riskHint0_7: string
    oppHint0_7: string
    riskHint8_30: string
    oppHint8_30: string
    riskHint31_90: string
    oppHint31_90: string
    riskHint91_365: string
    oppHint91_365: string
    /** 失败/成功路径字段 */
    pTrigger: string
    pProb: string
    pSignals: string
    pSolution: string
    pKeyVars: string
    pHowImprove: string
    /** 最优优化方案字段 */
    oPriority: string
    oWhy: string
    oSuccessImpact: string
    oFailImpact: string
    oWhatChange: string
    oVerify: string
    oMetric: string
    /** 结论补充 */
    suggestOptimizeFirst: string
    generatedAt: string
  }
}

const NARRATIVE: Record<Locale, InsightNarrative> = {
  'zh-CN': buildZh(),
  'en-US': buildEn(),
  'ja-JP': buildJa(),
  'ko-KR': buildKo(),
}

function buildZh(): InsightNarrative {
  return {
    painScore: (n) => `痛点抓得准（${n}/100）`,
    painWeak: (n) => `痛点还不够疼（${n}/100）`,
    retentionGood: (n) => `留得住人（${n}/100）`,
    retentionWeak: (n) => `留存乏力（${n}/100）`,
    distributionGood: (n) => `传得出去（${n}/100）`,
    distributionWeak: (n) => `声量不足（${n}/100）`,
    clarityGood: (n) => `一看就懂（${n}/100）`,
    clarityWeak: (n) => `表达还得再磨（${n}/100）`,
    gapRisk: (gap) => `分发-留存落差 ${gap} 分：小心「火一把就凉」`,
    competitionRisk: '赛道很卷，差异化才是活路',
    platformRisk: '平台依赖偏高，命脉别全押在别人手里',
    techDebtRisk: '技术债在悄悄拖慢你的迭代',
    painFit: (pain, label) => `痛点强度 ${pain}/100（${label}）`,
    distVsRet: (dist, ret, gap) => `分发 ${dist} vs 留存 ${ret}，落差 ${gap} 分`,
    retentionScore: (ret) => `留存潜力 ${ret}/100`,
    channelScore: (dist) => `渠道能力 ${dist}/100`,
    competitionScore: (comp) => `竞争强度 ${comp}/100`,
    platformScore: (dep) => `平台依赖 ${dep}/100`,
    monetizationScore: (fit) => `变现适配 ${fit}/100`,
    legalScore: (legal) => `法律风险 ${legal}/100`,
    generalRoot: '从综合评分看，最薄弱的环节会最先暴露出来——按敏感性优先级逐项加固，别让一块短板拖垮整体。',
    generalEvidence: (vuln) => `最脆弱维度：${vuln}`,
    generalEarly: ['核心指标连续 2 周低于健康线——这是最早的求救信号', '用户的负面反馈开始聚在同一个痛点上'],
    generalPrevent: ['每周对照预警指标表做一次复盘，别等出事才回头看', '优先修复敏感性最高的那个变量，好钢用在刀刃上'],
    knownCompetitors: (names) => `已知竞品：${names}`,
    crashWindow: (t) => `最可能的崩盘窗口：${t}，提前布防`,
    weakPain: {
      title: '痛点不足 / 伪需求',
      rootCause: '说白了，用户觉得这个问题「有也行、没有也行」——没有足够强的动机去用、去付费，产品解决的痛还不够疼。',
      earlySignals: ['落地页跳出率 > 70%', '用户访谈里常听到「还不错，但不用也没事」', '自然留存 D7 < 5%'],
      preventionActions: ['收窄 ICP，只服务最痛的一群人', '用具体场景案例替换功能罗列', '做一次「不用它会损失什么」的价值验证'],
    },
    hypeMismatch: {
      title: '高分发低留存（热度虚火）',
      rootCause: '传播把大批尝鲜用户带进了门，但产品还接不住这波流量——新鲜感一过，人就散了，热闹只是虚火。',
      earlySignals: ['首周暴涨后 D7 留存断崖', '社媒讨论很热但日活不跟', '差评集中在「试一次就不用了」'],
      preventionActions: ['先修留存再砸投放，顺序别反', '区分「曝光 KPI」与「留存 KPI」', '为尝鲜用户设计二次激活路径'],
    },
    retentionCollapse: {
      title: '留存崩塌',
      rootCause: '用户第一次来没看清价值、也没形成回来的习惯，于是用完即走——不是用户无情，是产品还没给出留下的理由。',
      earlySignals: ['D7 < 8%', 'D30 < 3%', '周活跃/注册比持续下降'],
      preventionActions: ['定义并打磨 Aha moment', '建立通知/工作流/数据沉淀这些「回来的钩子」', '对流失用户做 cohort 复盘'],
    },
    distributionFailure: {
      title: '分发失灵 / 无人看见',
      rootCause: '产品本身可能真不错，但缺一条能持续带来新用户的渠道——「做出来没人知道」，酒香也怕巷子深。',
      earlySignals: ['连续 2 周自然新增低于预期', '各渠道 CPA 都居高不下', '没有自发分享/UGC'],
      preventionActions: ['选 1 个主渠道先打透', '设计可传播的产出物，让用户替你说话', '找 10 个种子用户深度共创'],
    },
    competitionShock: {
      title: '竞争挤压 / 被替代',
      rootCause: '赛道已经拥挤，或者大厂随时可能入场——差异化不够硬的话，用户换掉你不会有任何心理负担。',
      earlySignals: ['竞品发布当周流失加速', '价格/功能战压薄毛利', '用户对比评测明显增多'],
      preventionActions: ['深耕垂直场景建立壁垒', '用数据/工作流提高迁移成本', '避开正面功能对标，做细分市场的冠军'],
    },
    platformRiskBlock: {
      title: '平台依赖 / 政策风险',
      rootCause: '增长或核心能力绑在单一平台/API 上，别人的规则一变，你的业务就跟着伤筋动骨——命脉握在别人手里，睡不安稳。',
      earlySignals: ['平台算法/政策调整后流量骤降', 'API 涨价或限流', '账号风控越来越频繁'],
      preventionActions: ['铺多渠道、建私域，鸡蛋分篮放', '核心能力逐步自有化', '合规与 ToS 审查前置'],
    },
    monetizationFailure: {
      title: '有用户难变现',
      rootCause: '用户是攒起来了，但付费意愿或商业模式还没跑通——烧钱换来的热闹，撑不起长期的生意。',
      earlySignals: ['MAU 在涨但 MRR 纹丝不动', '付费转化 < 0.5%', '免费用户占比居高不下'],
      preventionActions: ['验证用户真正愿付的价格与套餐', '把付费价值做进核心使用路径', '试水 B2B / 增值服务'],
    },
    regulatory: {
      title: '合规 / 模式风险',
      rootCause: '业务踩在监管红线附近，或商业模式本身难以持续——这类风险一旦爆发就是硬伤，宜早不宜迟地正面处理。',
      earlySignals: ['合规咨询发出警告', '关键资质/牌照缺失', '用户投诉开始涉及欺诈/隐私'],
      preventionActions: ['尽早请合规顾问把关', '把模式调整到可审计的链路上', '留存完整操作日志'],
    },
    aiCommoditization: {
      title: 'AI 能力商品化 / 被上游替代',
      rootCause: '核心能力建立在第三方模型/平台之上，上游一旦降价、免费或亲自下场，护城河可能一夜蒸发。',
      earlySignals: ['上游发布同类功能', 'API 涨价或限流', '用户开始问「这和通用 AI 有什么区别」'],
      preventionActions: ['深耕垂直数据与工作流，做上游做不了的事', '积累专有数据集或评测基准', '架构上多模型可迁移，但价值绑定在业务层'],
    },
    headlinePublish: (outcome, weakest) => `可以放心发布、边跑边迭代：最可能走向「${outcome}」，记得盯紧${weakest}这块短板`,
    headlineHighDeath: (death, risk) => `先别急着发布：死亡概率 ${death} 偏高，把「${risk}」这道坎迈过去再上路，会稳得多`,
    headlineValidate: (death, direction) => `建议小步试水：死亡概率 ${death}，先把「${direction}」补强，胜算会大不少`,
    diagnosisSummary: (p) => {
      const dv = p.deathValue ?? 0.4
      const bench = p.benchmark ? '结合真实案例库对标' : '基于蒙特卡洛模拟分布'
      let body: string
      if (dv >= 0.5) {
        body =
          `先说结论：${p.product}（${p.type}·${p.stage}）这一版的处境确实有点严峻——${bench}，最可能的走向是「${p.outcome}」，死亡概率 ${p.death}。` +
          `但先别灰心，同一批模拟里也看到了 ${p.success} 的成功可能，路没有堵死。` +
          `眼下最拖后腿的是「${p.topRisk}」，破局点也很明确：从${p.optimize}开始，一步一步把胜率拉回来。`
      } else if (dv >= 0.3) {
        body =
          `${p.product}（${p.type}·${p.stage}）这次的推演结果算是喜忧参半：${bench}，最可能走向「${p.outcome}」，死亡概率 ${p.death}，成功概率 ${p.success}——胜负都在可争取的区间。` +
          `目前最值得警惕的是「${p.topRisk}」；好消息是杠杆也找到了：优先把${p.optimize}做扎实，天平就会往成功那边倾斜。`
      } else {
        body =
          `好消息：${p.product}（${p.type}·${p.stage}）的底子相当扎实——${bench}，最可能走向「${p.outcome}」，死亡概率被压到了 ${p.death}，成功概率有 ${p.success}。` +
          `当然别掉以轻心，「${p.topRisk}」仍是最需要盯住的变量；想更进一步，就从${p.optimize}发力。`
      }
      return body + p.stageHint + (p.lowConf ? ' 另外提醒一句：当前画像完整度偏低，这份结论先当参考，补全数据后再跑一次会更准。' : '')
    },
    stageHintEarly: ' 作品还在早期阶段，先别急着大规模投放——把 PMF 验证扎实，后面每一步都更有底气。',
    stageHintDecline: ' 作品正处在停滞/衰退期，这份报告侧重帮你找转型出路与止损点——及时调头也是一种前进。',
    confHigh: '评分维度比较完整，这份结论可以放心参考',
    confMid: '建议再补几项维度评分、或提高模拟次数，结论会更有底气',
    confLow: '目前数据还太少，先补全作品画像再做大决定——磨刀不误砍柴工',
    publishYes: '✅ 可以发布（边跑边迭代）',
    publishNo: '⚠️ 建议先优化再上',
    successOpportunities: {
      compound_growth: {
        title: '长期复利增长', trigger: '留存强 + 习惯形成 + 持续迭代', rootCause: '',
        earlySignals: [], preventionActions: [],
        actions: ['保持更新节奏', '深耕核心用户工作流', '建立社区或模板生态'],
        metrics: ['D30 留存', '周活跃率', '自然新增占比'],
      },
      niche_breakthrough: {
        title: '垂直利基突破', trigger: '细分场景强痛点 + 可触达圈层', rootCause: '',
        earlySignals: [], preventionActions: [],
        actions: ['深耕一个垂直行业/角色', '做案例库与口碑推荐', '参与垂直社区运营'],
        metrics: ['垂直渠道转化率', 'NPS', '复购率'],
      },
      steady_saas: {
        title: '稳健中等规模', trigger: '痛点成立 + 留存达标 + 分发受限但可持续', rootCause: '',
        earlySignals: [], preventionActions: [],
        actions: ['优化 onboarding 与付费转化', '扩展集成与工作流', '控制 CAC 与 burn'],
        metrics: ['MRR 增速', '毛利率', 'CAC 回收周期'],
      },
      viral_breakout: {
        title: '病毒式破圈', trigger: '超强痛点×分发×分享动机对齐', rootCause: '',
        earlySignals: [], preventionActions: [],
        actions: ['优化平台推荐适配', '设计可分享的结果/时刻', '快速承接流量做好留存'],
        metrics: ['K-factor', '峰值并发承载', '爆款后 D7 留存'],
      },
      clear_scale: {
        title: '明显规模化', trigger: '三维均衡 + 竞争未碾压', rootCause: '',
        earlySignals: [], preventionActions: [],
        actions: ['扩团队与客服能力', '标准化获客 playbook', '加固技术与合规'],
        metrics: ['月活增速', '故障率', '客诉率'],
      },
      survival_pivot: {
        title: '存活并转型', trigger: '先活下来，再寻找第二增长曲线', rootCause: '',
        earlySignals: [], preventionActions: [],
        actions: ['削减 burn、聚焦单点场景', '与种子用户共创 pivot', '设定 90 天验证里程碑'],
        metrics: ['runway 月数', '试点转化率'],
      },
    },
    improveSteps: {
      audiencePain: {
        steps: ['访谈 8–12 个目标用户，提炼 Top3 痛点', '重写 Hero：问题→方案→证据', '砍掉非核心功能，聚焦主场景'],
        metrics: ['首日转化率', '用户「必须性」评分'],
        effort: 'medium',
      },
      clarity: {
        steps: ['5 秒理解测试（录屏观察）', '首屏 A/B：标题/副标题/社会证明', '统一全站术语与价值主张'],
        metrics: ['落地页转化率', 'onboarding 完成率'],
        effort: 'low',
      },
      retentionPotential: {
        steps: ['绘制激活漏斗，定位最大流失步', '设计 D1/D3/D7 触达', '增加习惯回路（提醒/收藏/协作）'],
        metrics: ['D7/D30 留存', '周活跃率'],
        effort: 'medium',
      },
      distributionPower: {
        steps: ['选主渠道并设定周获客目标', '内置分享卡片/邀请机制', '准备 3 套发布素材模板'],
        metrics: ['渠道 CPA', 'K-factor / 分享率'],
        effort: 'medium',
      },
      differentiation: {
        steps: ['列竞品对比表，找唯一差异点', '把差异写进定价页与 onboarding', '为差异点做可演示的 demo'],
        metrics: ['竞品切换率', 'NPS 开放题'],
        effort: 'medium',
      },
      monetizationFit: {
        steps: ['定义免费/付费边界', '测试 2 档价格', '追踪试用→付费漏斗'],
        metrics: ['付费转化率', 'ARPU'],
        effort: 'low',
      },
      shareability: {
        steps: ['让用户产出可分享的结果/徽章', '设计邀请奖励', '在关键成就点触发分享'],
        metrics: ['分享率', '邀请注册占比'],
        effort: 'low',
      },
    },
    improveFallbackStep: '将 {variable} 相关能力提升 15 分（当前 {value}）',
    improveFallbackMetrics: ['Top10% 概率', '死亡概率'],
    improveFallbackTitle: '强化{variable}',
    improveWhyNowTop: '当前最薄弱的一环是「{label}」——它的敏感性排名第 {rank}，先改它，投入产出比最高。',
    improveWhyNowRank: '敏感性排名第 {rank}，对成败概率的影响强度 {impact}%，值得排进日程。',
    improveExpectedImpact: '这一维度 +15 分后，死亡概率约 {death}%（较当前 {base}% {dir} {pp}pp）· Top10% 概率可提升约 {topPp}pp',
    dirDown: '降低',
    dirUp: '升高',
    whyBase: '推荐等级 {stars}；死亡概率 {death}，Top10% {top10}。',
    whyClarityWeak: ' 清晰度是短板，先把「说清楚自己」这件事做好。',
    whyRetentionShort: ' 留存跟不上分发——先把人留住，再谈增长。',
    whyNeedAcquisition: ' 获客引擎还缺一台，需要尽快补上。',
    whyNeedMonetization: ' 商业化要同步推进，别等弹药耗尽才想起收钱。',
    whyWeakestDim: ' 综合看最弱的一环：{label}。',
    reportSections: reportSectionsZh(),
    markdownReport: markdownReportZh(),
  }
}

function reportSectionsZh(): InsightNarrative['reportSections'] {
  return {
    insightSummary: '产品诊断摘要',
    decisionTable: '决策项',
    publishDecision: '是否建议发布',
    mostLikely: '最可能结局',
    deathProb: '死亡概率',
    successProb: '成功概率（含中等成功）',
    confidenceNote: '置信说明',
    artifactType: '作品类型',
    stage: '当前阶段',
    scoreDiag: '评分诊断',
    strengths: '优势',
    weaknesses: '短板',
    structuralRisks: '结构性风险',
    noStrength: '暂无明显强项',
    none: '无',
    noStructural: '无显著结构风险',
    deathAnalysis: '死亡原因分析（按相关度排序）',
    rootCause: '根因',
    scoreEvidence: '评分依据',
    earlySignals: '早期信号',
    prevention: '预防措施 / 改法',
    growthOps: '增长机会（可争取方向）',
    trigger: '触发条件',
    keyActions: '关键动作',
    metricsWatch: '监控指标',
    roadmap: '行动路线图',
    goals: '目标',
    tasks: '任务',
    improvements: '改进方案（按优先级）',
    whyNow: '为何现在做',
    expectedImpact: '预期影响',
    concreteSteps: '具体动作',
    strategyRec: '优化策略推荐',
    bestFor: '适用场景',
    whyRecommended: '推荐理由',
    execList: '执行清单',
    severity: { critical: '严重', high: '高', medium: '中' },
    urgency: { immediate: '立即', short_term: '短期', long_term: '中期' },
    effort: { low: '低', medium: '中', high: '高' },
  }
}

function markdownReportZh(): InsightNarrative['markdownReport'] {
  return {
    title: '作品未来推演报告',
    disclaimer: '本报告由 Future Simulation Engine 生成。所有结论基于蒙特卡洛模拟，仅供参考，不是确定性预测。',
    basicInfo: '基本信息',
    project: '项目',
    name: '作品名称',
    type: '作品类型',
    stage: '当前阶段',
    targetUsers: '目标用户',
    period: '模拟周期',
    runs: '模拟次数',
    confidence: '置信度',
    completeness: '数据完整度',
    coreJudgment: '核心判断',
    mostLikely: '最可能走向',
    biggestOpp: '最大机会',
    biggestRisk: '最大风险',
    worthInvest: '是否值得投入',
    topOptimize: '最应该优化方向',
    yes: '是',
    no: '否',
    legacyInsight: '本结果为旧版数据，请重新运行模拟以生成完整诊断章节。',
    outcomeDist: '结果概率分布',
    ranking: '排名率',
    benchmarkYes: '基于相似案例库计算',
    benchmarkNo: '缺少 benchmark 数据，以下为内部估算',
    forecast: '关键指标预测',
    futurePaths: '最可能未来路径',
    failurePaths: '失败路径分析',
    successPaths: '成功路径分析',
    sensitivity: '敏感性分析',
    strategyCompare: '策略对比',
    optimization: '最优优化方案',
    warnings: '早期预警指标',
    conclusion: '结论',
    worthPublish: '当前版本是否值得发布',
    optimizeBeforePublish: '是否需要先优化再发布',
    directPublish: '可以直接发布，持续迭代',
    keepInvesting: '建议继续投入',
    cautionInvest: '需要谨慎评估',
    footer: 'Powered by Future Simulation Engine',
    notFilled: '未填写',
    days: '天',
    colOutcome: '结果类型',
    colProb: '概率',
    colIndicator: '指标',
    colValue: '概率 / 数值',
    colMedian: '中位数',
    colVariable: '变量',
    colScore: '当前评分',
    colTop10Impact: '对 Top10% 影响',
    colPriority: '优化优先级',
    colStrategy: '策略',
    colDeath: '死亡概率',
    colBlockbuster: '爆款概率',
    colUsers: '中位用户',
    colRevenue: '中位收入',
    colRecommend: '推荐级别',
    colHealthy: '健康阈值',
    colDanger: '危险阈值',
    colDesc: '说明',
    rankAboveMedian: '超过同类中位数概率',
    rankExpectedPctl: '预期排名百分位',
    rankMedianPctl: '中位排名百分位',
    phase0_7: '0-7 天',
    phase8_30: '8-30 天',
    phase31_90: '31-90 天',
    phase91_365: '91-365 天',
    notCovered: '模拟周期未覆盖该阶段',
    pathStat: '用户中位约 {users}，活跃约 {active}（活跃率 {rate}%），累计收入约 ¥{rev}',
    phaseTrend: '阶段趋势：{trend}（环比 {growth}%）',
    keyRisk: '关键风险',
    keyOpp: '关键机会',
    trendFast: '快速增长',
    trendSteady: '平稳增长',
    trendPlateau: '增长见顶/放缓',
    trendDecline: '明显回落',
    riskHint0_7: '首屏表达不清晰导致初始用户流失',
    oppHint0_7: '获得平台推荐可快速起量',
    riskHint8_30: '留存不达标导致增长停滞',
    oppHint8_30: '口碑传播开始发挥作用',
    riskHint31_90: '竞品冲击与新鲜感衰减',
    oppHint31_90: '社区形成、长期价值显现',
    riskHint91_365: '创作者持续性与技术债拖累',
    oppHint91_365: '二次传播与生态效应',
    pTrigger: '触发条件',
    pProb: '发生概率',
    pSignals: '早期信号',
    pSolution: '解决方法',
    pKeyVars: '关键变量',
    pHowImprove: '如何提高概率',
    oPriority: '优先级',
    oWhy: '为什么重要',
    oSuccessImpact: '对成功概率影响',
    oFailImpact: '对失败概率影响',
    oWhatChange: '需要改什么',
    oVerify: '如何验证',
    oMetric: '监控指标',
    suggestOptimizeFirst: '建议先优化',
    generatedAt: '报告生成时间',
  }
}

function buildEn(): InsightNarrative {
  const base = buildZh()
  return {
    ...base,
    painScore: (n) => `Pain point lands (${n}/100)`,
    painWeak: (n) => `Pain not sharp enough yet (${n}/100)`,
    retentionGood: (n) => `People stick around (${n}/100)`,
    retentionWeak: (n) => `Retention needs love (${n}/100)`,
    distributionGood: (n) => `Word gets out (${n}/100)`,
    distributionWeak: (n) => `Not being heard yet (${n}/100)`,
    clarityGood: (n) => `Instantly understandable (${n}/100)`,
    clarityWeak: (n) => `Messaging needs polish (${n}/100)`,
    gapRisk: (gap) => `Distribution–retention gap ${gap} pts: beware "hot then gone"`,
    competitionRisk: 'Crowded market — differentiation is your lifeline',
    platformRisk: 'Heavy platform dependency — don\'t bet it all on someone else\'s rules',
    techDebtRisk: 'Technical debt is quietly slowing you down',
    painFit: (pain, label) => `Pain intensity ${pain}/100 (${label})`,
    distVsRet: (dist, ret, gap) => `Distribution ${dist} vs retention ${ret}, gap ${gap}`,
    retentionScore: (ret) => `Retention potential ${ret}/100`,
    channelScore: (dist) => `Channel strength ${dist}/100`,
    competitionScore: (comp) => `Competition intensity ${comp}/100`,
    platformScore: (dep) => `Platform dependency ${dep}/100`,
    monetizationScore: (fit) => `Monetization fit ${fit}/100`,
    legalScore: (legal) => `Legal risk ${legal}/100`,
    generalRoot: 'Under the current scores, the weakest link is what breaks first — shore things up in sensitivity order, and don\'t let one gap sink the whole ship.',
    generalEvidence: (vuln) => `Most vulnerable: ${vuln}`,
    generalEarly: ['Core metrics below the healthy line for 2+ weeks — the earliest distress signal', 'Negative feedback starts clustering around the same pain'],
    generalPrevent: ['Do a weekly review against the warning metrics — don\'t wait for things to break', 'Fix the highest-sensitivity variable first; spend effort where it counts'],
    knownCompetitors: (names) => `Known competitors: ${names}`,
    crashWindow: (t) => `Likely crash window: ${t} — get ahead of it`,
    weakPain: {
      title: 'Weak pain / faux demand',
      rootCause: 'Put bluntly: users see this as "nice to have". The pain isn\'t sharp enough to make them use it, pay for it, or come back.',
      earlySignals: ['Landing bounce > 70%', 'Interviews keep saying "nice, but I could live without it"', 'Organic D7 < 5%'],
      preventionActions: ['Narrow ICP to the most pained segment', 'Replace feature lists with scenario proof', 'Validate the "cost of not using it"'],
    },
    hypeMismatch: {
      title: 'High reach, low retention',
      rootCause: 'The buzz brought a crowd of curious visitors through the door, but the product couldn\'t hold them — once the novelty faded, they drifted away.',
      earlySignals: ['D7 cliff right after the spike', 'Buzz without DAU', 'Reviews: "tried it once"'],
      preventionActions: ['Fix retention before scaling spend — in that order', 'Separate reach KPIs from retention KPIs', 'Design re-activation paths for trial users'],
    },
    retentionCollapse: {
      title: 'Retention collapse',
      rootCause: 'First-time users never saw the value clearly, and no habit formed — so they left. It\'s not that users are fickle; the product hasn\'t given them a reason to stay yet.',
      earlySignals: ['D7 < 8%', 'D30 < 3%', 'WAU/signups falling'],
      preventionActions: ['Define and polish the aha moment', 'Build comeback hooks: D1/D7 touchpoints, workflows, data lock-in', 'Run cohort analysis on churn'],
    },
    distributionFailure: {
      title: 'Distribution failure',
      rootCause: 'The product may genuinely be good, but there\'s no durable channel bringing new users in — built it, and nobody knows. Great wine still needs a storefront.',
      earlySignals: ['Organic adds below plan for 2 weeks', 'CPA too high everywhere', 'No organic shares/UGC'],
      preventionActions: ['Pick one primary channel and go deep', 'Build shareable outputs — let users do the talking', 'Co-build with 10 seed users'],
    },
    competitionShock: {
      title: 'Competitive squeeze',
      rootCause: 'The market is crowded — or big tech could walk in any day. Without hard differentiation, switching away from you costs users nothing.',
      earlySignals: ['Churn accelerates on rival launch', 'Price/feature war squeezing margins', 'Comparison reviews piling up'],
      preventionActions: ['Own a vertical niche and build the moat there', 'Raise switching costs with data and workflows', 'Skip head-on feature parity — be the champion of a segment'],
    },
    platformRiskBlock: {
      title: 'Platform / policy risk',
      rootCause: 'Growth or core capability is tied to a single platform or API — one rule change on their side and your business takes the hit. Your lifeline is in someone else\'s hands.',
      earlySignals: ['Traffic drops after algo/policy change', 'API price hikes or rate limits', 'Account flags getting more frequent'],
      preventionActions: ['Spread across channels and build an owned audience', 'Bring core capabilities in-house over time', 'Do compliance and ToS review upfront'],
    },
    monetizationFailure: {
      title: 'Users without revenue',
      rootCause: 'The users showed up, but willingness to pay or the business model hasn\'t clicked yet — a crowd bought with burn can\'t sustain a business.',
      earlySignals: ['MAU up, MRR flat', 'Paid conversion < 0.5%', 'Free tier dominating'],
      preventionActions: ['Test what users will actually pay, and how it\'s packaged', 'Embed paid value into the core path', 'Pilot B2B / add-ons'],
    },
    regulatory: {
      title: 'Compliance / model risk',
      rootCause: 'The business sits close to regulatory red lines, or the model itself isn\'t sustainable — when this kind of risk lands, it lands hard. Face it early.',
      earlySignals: ['Legal warnings', 'Missing licenses', 'Complaints touching fraud/privacy'],
      preventionActions: ['Bring in compliance counsel early', 'Move to an auditable model', 'Keep full audit logs'],
    },
    aiCommoditization: {
      title: 'AI commoditization',
      rootCause: 'Core value is built on upstream models/platforms — if they cut prices, go free, or ship it themselves, your moat could evaporate overnight.',
      earlySignals: ['Upstream ships the same feature', 'API price/limit changes', 'Users asking "why not just ChatGPT?"'],
      preventionActions: ['Go deep on vertical data and workflows — do what upstream can\'t', 'Build proprietary datasets or benchmarks', 'Keep the architecture multi-model, but anchor value in your business layer'],
    },
    headlinePublish: (outcome, weakest) => `Ship it and iterate: most likely "${outcome}" — just keep an eye on ${weakest}`,
    headlineHighDeath: (death, risk) => `Hold the launch for now: death probability ${death} is high — clear "${risk}" first and you\'ll ship on much firmer ground`,
    headlineValidate: (death, direction) => `Test the waters in small steps: death ${death} — strengthen "${direction}" first and your odds improve a lot`,
    diagnosisSummary: (p) => {
      const dv = p.deathValue ?? 0.4
      const bench = p.benchmark ? 'calibrated against real-world cases' : 'based on the Monte Carlo distribution'
      let body: string
      if (dv >= 0.5) {
        body =
          `Straight talk: ${p.product} (${p.type} · ${p.stage}) is in a tough spot right now — ${bench}, the most likely path is "${p.outcome}" with a ${p.death} death probability. ` +
          `But don\'t lose heart: the same simulation still sees a ${p.success} chance of success, so the road isn\'t closed. ` +
          `The biggest drag is "${p.topRisk}", and the way out is clear — start with ${p.optimize} and claw the odds back step by step.`
      } else if (dv >= 0.3) {
        body =
          `${p.product} (${p.type} · ${p.stage}) came back mixed: ${bench}, the most likely path is "${p.outcome}" — death ${p.death}, success ${p.success}. Both outcomes are within reach. ` +
          `The thing to watch most is "${p.topRisk}"; the good news is the lever is identified — nail ${p.optimize} first and the scales tip your way.`
      } else {
        body =
          `Good news: ${p.product} (${p.type} · ${p.stage}) is standing on solid ground — ${bench}, the most likely path is "${p.outcome}", with death held down to ${p.death} and a ${p.success} chance of success. ` +
          `Don\'t coast, though: "${p.topRisk}" is still the variable to watch, and if you want more upside, push on ${p.optimize}.`
      }
      return body + p.stageHint + (p.lowConf ? ' One more note: profile completeness is low, so treat this as directional — fill in the data and rerun for a sharper read.' : '')
    },
    stageHintEarly: ' You\'re still early — don\'t rush into big spend; validate PMF first and every next step gets easier.',
    stageHintDecline: ' The product is in a stagnant/declining phase, so this report focuses on pivot paths and stop-loss — turning around in time is progress too.',
    confHigh: 'Scores are fairly complete — you can lean on this conclusion',
    confMid: 'Add a few more dimension scores or increase runs; the conclusion will stand firmer',
    confLow: 'Data is still thin — complete the profile before any big decision; sharpening the axe won\'t delay the woodcutting',
    publishYes: '✅ OK to ship (iterate as you go)',
    publishNo: '⚠️ Optimize first, then launch',
    successOpportunities: {
      compound_growth: { title: 'Long compound growth', trigger: 'Strong retention + habits + shipping cadence', rootCause: '', earlySignals: [], preventionActions: [], actions: ['Keep release rhythm', 'Deepen core workflow', 'Community/templates'], metrics: ['D30 retention', 'WAU', 'Organic share'] },
      niche_breakthrough: { title: 'Niche breakthrough', trigger: 'Sharp pain in reachable segment', rootCause: '', earlySignals: [], preventionActions: [], actions: ['Own one vertical', 'Case studies + referrals', 'Community ops'], metrics: ['Vertical conversion', 'NPS', 'Repeat rate'] },
      steady_saas: { title: 'Steady mid-scale', trigger: 'Pain + retention OK, distribution capped', rootCause: '', earlySignals: [], preventionActions: [], actions: ['Onboarding + monetization', 'Integrations/workflows', 'Control CAC/burn'], metrics: ['MRR growth', 'Gross margin', 'CAC payback'] },
      viral_breakout: { title: 'Viral breakout', trigger: 'Pain × distribution × sharing aligned', rootCause: '', earlySignals: [], preventionActions: [], actions: ['Platform fit', 'Shareable moments', 'Retain spike traffic'], metrics: ['K-factor', 'Peak capacity', 'Post-viral D7'] },
      clear_scale: { title: 'Clear scale-up', trigger: 'Balanced scores, competition manageable', rootCause: '', earlySignals: [], preventionActions: [], actions: ['Scale team/support', 'Playbook acquisition', 'Harden tech/compliance'], metrics: ['MAU growth', 'Incident rate', 'Complaints'] },
      survival_pivot: { title: 'Survive and pivot', trigger: 'Stay alive, find second curve', rootCause: '', earlySignals: [], preventionActions: [], actions: ['Cut burn, one scenario', 'Co-build pivot with seeds', '90-day validation milestones'], metrics: ['Runway months', 'Pilot conversion'] },
    },
    improveSteps: {
      audiencePain: {
        steps: ['Interview 8–12 target users; distill top-3 pains', 'Rewrite hero: problem → solution → proof', 'Cut non-core features; focus the main scenario'],
        metrics: ['Day-1 conversion', 'User "must-have" score'],
        effort: 'medium',
      },
      clarity: {
        steps: ['Run 5-second comprehension tests (screen recording)', 'A/B the hero: title / subtitle / social proof', 'Unify terminology and value proposition'],
        metrics: ['Landing conversion', 'Onboarding completion'],
        effort: 'low',
      },
      retentionPotential: {
        steps: ['Map the activation funnel; find the biggest drop', 'Design D1/D3/D7 touchpoints', 'Add habit loops (reminders/saves/collab)'],
        metrics: ['D7/D30 retention', 'Weekly active rate'],
        effort: 'medium',
      },
      distributionPower: {
        steps: ['Pick a primary channel with weekly targets', 'Build share cards / invite mechanics', 'Prepare 3 launch asset templates'],
        metrics: ['Channel CPA', 'K-factor / share rate'],
        effort: 'medium',
      },
      differentiation: {
        steps: ['Build a competitor matrix; find the unique edge', 'Put the edge into pricing page and onboarding', 'Make the edge demoable'],
        metrics: ['Competitor switch rate', 'NPS verbatims'],
        effort: 'medium',
      },
      monetizationFit: {
        steps: ['Define the free/paid boundary', 'Test two price points', 'Track trial→paid funnel'],
        metrics: ['Paid conversion', 'ARPU'],
        effort: 'low',
      },
      shareability: {
        steps: ['Let users produce shareable results/badges', 'Design referral incentives', 'Trigger sharing at achievement moments'],
        metrics: ['Share rate', 'Invite signup share'],
        effort: 'low',
      },
    },
    improveFallbackStep: 'Raise {variable} by ~15 points (currently {value})',
    improveFallbackMetrics: ['Top10% probability', 'Death probability'],
    improveFallbackTitle: 'Strengthen {variable}',
    improveWhyNowTop: 'Your weakest link is "{label}" — it ranks #{rank} in sensitivity, so fixing it first gives the best return on effort.',
    improveWhyNowRank: 'Sensitivity rank #{rank}, with {impact}% impact on your odds — worth a spot on the roadmap.',
    improveExpectedImpact: 'At +15 on this dimension, death probability ≈ {death}% (vs current {base}%, {dir} {pp}pp) · Top10% up ≈ {topPp}pp',
    dirDown: 'down',
    dirUp: 'up',
    whyBase: 'Recommendation {stars}; death {death}, Top10% {top10}.',
    whyClarityWeak: ' Clarity is the gap — get "explaining yourself" right first.',
    whyRetentionShort: ' Retention lags distribution — keep people around before chasing growth.',
    whyNeedAcquisition: ' An acquisition engine is still missing — build one soon.',
    whyNeedMonetization: ' Push monetization in parallel — don\'t wait until the runway runs out.',
    whyWeakestDim: ' Weakest dimension overall: {label}.',
    reportSections: {
      ...reportSectionsZh(),
      insightSummary: 'Product diagnosis',
      decisionTable: 'Decision',
      publishDecision: 'Ship recommendation',
      mostLikely: 'Most likely outcome',
      deathProb: 'Death probability',
      successProb: 'Success probability (incl. moderate)',
      confidenceNote: 'Confidence note',
      artifactType: 'Product type',
      stage: 'Stage',
      scoreDiag: 'Score diagnosis',
      strengths: 'Strengths',
      weaknesses: 'Weaknesses',
      structuralRisks: 'Structural risks',
      noStrength: 'No clear strengths',
      none: 'None',
      noStructural: 'No major structural risk',
      deathAnalysis: 'Death reasons (by relevance)',
      rootCause: 'Root cause',
      scoreEvidence: 'Score evidence',
      earlySignals: 'Early signals',
      prevention: 'Prevention / fixes',
      growthOps: 'Growth opportunities',
      trigger: 'Trigger',
      keyActions: 'Key actions',
      metricsWatch: 'Metrics to watch',
      roadmap: 'Action roadmap',
      goals: 'Goals',
      tasks: 'Tasks',
      improvements: 'Improvements (priority)',
      whyNow: 'Why now',
      expectedImpact: 'Expected impact',
      concreteSteps: 'Concrete steps',
      strategyRec: 'Strategy recommendations',
      bestFor: 'Best for',
      whyRecommended: 'Why recommended',
      execList: 'Execution checklist',
      severity: { critical: 'critical', high: 'high', medium: 'medium' },
      urgency: { immediate: 'now', short_term: 'short term', long_term: 'mid term' },
      effort: { low: 'low', medium: 'medium', high: 'high' },
    },
    markdownReport: {
      ...markdownReportZh(),
      title: 'Product future simulation report',
      disclaimer: 'Generated by Future Simulation Engine. Monte Carlo results are indicative, not predictions.',
      basicInfo: 'Basics',
      project: 'Item',
      name: 'Product name',
      type: 'Type',
      stage: 'Stage',
      targetUsers: 'Target users',
      period: 'Simulation period',
      runs: 'Run count',
      confidence: 'Confidence',
      completeness: 'Data completeness',
      coreJudgment: 'Core judgment',
      mostLikely: 'Most likely path',
      biggestOpp: 'Biggest opportunity',
      biggestRisk: 'Biggest risk',
      worthInvest: 'Worth investing',
      topOptimize: 'Top optimization',
      yes: 'Yes',
      no: 'No',
      legacyInsight: 'Legacy result — rerun for full diagnosis chapters.',
      outcomeDist: 'Outcome distribution',
      ranking: 'Ranking rates',
      benchmarkYes: 'Calibrated against similar cases',
      benchmarkNo: 'No benchmark — internal estimate only',
      forecast: 'Key metric forecast',
      futurePaths: 'Likely future paths',
      failurePaths: 'Failure path analysis',
      successPaths: 'Success path analysis',
      sensitivity: 'Sensitivity analysis',
      strategyCompare: 'Strategy comparison',
      optimization: 'Top optimizations',
      warnings: 'Early warning metrics',
      conclusion: 'Conclusion',
      worthPublish: 'Worth shipping now',
      optimizeBeforePublish: 'Optimize before launch',
      directPublish: 'Can ship and iterate',
      keepInvesting: 'Continue investing',
      cautionInvest: 'Invest with caution',
      footer: 'Powered by Future Simulation Engine',
      colOutcome: 'Outcome',
      colProb: 'Probability',
      colIndicator: 'Metric',
      colValue: 'Value',
      colMedian: 'Median',
      colVariable: 'Variable',
      colScore: 'Score',
      colTop10Impact: 'Top10% impact',
      colPriority: 'Priority',
      colStrategy: 'Strategy',
      colDeath: 'Death prob.',
      colBlockbuster: 'Blockbuster',
      colUsers: 'Median users',
      colRevenue: 'Median revenue',
      colRecommend: 'Recommend',
      colHealthy: 'Healthy',
      colDanger: 'Danger',
      colDesc: 'Notes',
      rankAboveMedian: 'Above-median probability',
      rankExpectedPctl: 'Expected percentile',
      rankMedianPctl: 'Median percentile',
      phase0_7: 'Day 0-7',
      phase8_30: 'Day 8-30',
      phase31_90: 'Day 31-90',
      phase91_365: 'Day 91-365',
      notCovered: 'Period not covered by simulation',
      pathStat: 'Median users ≈ {users}, active ≈ {active} ({rate}% active), cumulative revenue ≈ ¥{rev}',
      phaseTrend: 'Phase trend: {trend} ({growth}% MoM)',
      keyRisk: 'Key risk',
      keyOpp: 'Key opportunity',
      trendFast: 'Fast growth',
      trendSteady: 'Steady growth',
      trendPlateau: 'Plateauing',
      trendDecline: 'Clear decline',
      riskHint0_7: 'Unclear hero message loses early users',
      oppHint0_7: 'Platform boost can accelerate takeoff',
      riskHint8_30: 'Weak retention stalls growth',
      oppHint8_30: 'Word of mouth starts compounding',
      riskHint31_90: 'Competitor shock and novelty decay',
      oppHint31_90: 'Community forms, long-term value shows',
      riskHint91_365: 'Creator consistency and tech-debt drag',
      oppHint91_365: 'Secondary spread and ecosystem effects',
      pTrigger: 'Trigger',
      pProb: 'Probability',
      pSignals: 'Early signals',
      pSolution: 'Solution',
      pKeyVars: 'Key variables',
      pHowImprove: 'How to improve odds',
      oPriority: 'Priority',
      oWhy: 'Why it matters',
      oSuccessImpact: 'Impact on success',
      oFailImpact: 'Impact on failure',
      oWhatChange: 'What to change',
      oVerify: 'How to verify',
      oMetric: 'Metric to watch',
      suggestOptimizeFirst: 'Optimize first',
      generatedAt: 'Generated at',
      notFilled: 'Not provided',
      days: 'days',
    },
  }
}

function buildJa(): InsightNarrative {
  const en = buildEn()
  return {
    ...en,
    painScore: (n) => `ペインを的確に捉えている（${n}/100）`,
    painWeak: (n) => `ペインの切実さがまだ弱い（${n}/100）`,
    retentionGood: (n) => `ユーザーが定着している（${n}/100）`,
    retentionWeak: (n) => `リテンションに伸び代あり（${n}/100）`,
    distributionGood: (n) => `届ける力がある（${n}/100）`,
    distributionWeak: (n) => `まだ声が届いていない（${n}/100）`,
    clarityGood: (n) => `ひと目で伝わる（${n}/100）`,
    clarityWeak: (n) => `伝え方に磨きが必要（${n}/100）`,
    gapRisk: (gap) => `配信-リテンション落差 ${gap} pt：「一瞬バズって終わり」に注意`,
    competitionRisk: 'market は激戦区——差別化こそが生命線',
    platformRisk: 'プラットフォーム依存が高め——命綱を他人に預けすぎない',
    techDebtRisk: '技術的負債が静かにイテレーションを遅らせている',
    generalRoot: '現在のスコアでは、最も弱い環から先に綻びます——感度の優先順位に沿って一つずつ補強し、一つの穴に全体を沈ませないこと。',
    generalEvidence: (vuln) => `最も脆弱な次元：${vuln}`,
    generalEarly: ['コア指標が2週間以上健全ラインを下回る——最初のSOSサイン', 'ネガティブな声が同じペインに集まり始める'],
    generalPrevent: ['週次で警告指標を見直す——壊れてから振り返らない', '感度が最も高い変数から直す——力は要所に注ぐ'],
    knownCompetitors: (names) => `既知の競合：${names}`,
    crashWindow: (t) => `最も起こりやすいクラッシュ時期：${t}——先回りして備える`,
    weakPain: { ...en.weakPain, title: 'ペイン不足 / 疑似ニーズ', rootCause: '率直に言えば、ユーザーにとって「あれば便利、なくても困らない」存在——使う・払う・戻る動機を生むほど、痛みがまだ鋭くありません。' },
    hypeMismatch: { ...en.hypeMismatch, title: '高リーチ・低リテンション', rootCause: '話題性が多くの「お試しユーザー」を連れてきましたが、プロダクトがまだ受け止めきれていません——新鮮さが薄れると人は離れ、賑わいは虚火で終わります。' },
    retentionCollapse: { ...en.retentionCollapse, title: 'リテンション崩壊', rootCause: '初回で価値が伝わらず、戻る習慣も生まれず、使い捨てで終わっています——ユーザーが薄情なのではなく、留まる理由をまだ提供できていないのです。' },
    distributionFailure: { ...en.distributionFailure, title: '配信失敗', rootCause: 'プロダクト自体は良くても、新規ユーザーを継続的に連れてくる経路がない——「作ったのに誰も知らない」。良酒も路地の奥では香りません。' },
    competitionShock: { ...en.competitionShock, title: '競合圧迫', rootCause: '市場はすでに混み合い、大手の参入もあり得ます——差別化が固くなければ、ユーザーは何の躊躇もなく乗り換えます。' },
    platformRiskBlock: { ...en.platformRiskBlock, title: 'プラットフォーム依存', rootCause: '成長やコア能力が単一のプラットフォーム/APIに縛られています——先方のルールが変われば事業ごと揺らぐ。命綱が他人の手の中にある状態です。' },
    monetizationFailure: { ...en.monetizationFailure, title: 'ユーザーはいるが収益化できない', rootCause: 'ユーザーは集まったものの、支払い意欲やビジネスモデルがまだ回っていません——資金を燃やして買った賑わいでは、長い商売は支えられません。' },
    regulatory: { ...en.regulatory, title: 'コンプライアンスリスク', rootCause: '事業が規制のレッドラインに近いか、モデル自体の持続性に課題があります——この種のリスクは表面化すると致命傷。早めに正面から向き合うのが吉です。' },
    aiCommoditization: { ...en.aiCommoditization, title: 'AI 商品化リスク', rootCause: 'コア能力が第三者モデル/プラットフォームの上に築かれています——上流が値下げ・無料化・自前参入すれば、堀は一夜で蒸発しかねません。' },
    headlinePublish: (outcome, weakest) => `安心してリリースし、走りながら改善を：最有力シナリオは「${outcome}」——ただし${weakest}だけは見張り続けて`,
    headlineHighDeath: (death, risk) => `今は焦らないで：死亡確率 ${death} は高め——「${risk}」の壁を越えてから出発する方がずっと安全です`,
    headlineValidate: (death, direction) => `小さく試すのがおすすめ：死亡確率 ${death}——まず「${direction}」を補強すれば勝算はぐっと上がります`,
    diagnosisSummary: (p) => {
      const dv = p.deathValue ?? 0.4
      const bench = p.benchmark ? '実例ベンチマーク対照の結果' : 'モンテカルロ分布の結果'
      let body: string
      if (dv >= 0.5) {
        body =
          `率直にお伝えすると、${p.product}（${p.type}・${p.stage}）は今かなり厳しい局面です——${bench}、最有力の行方は「${p.outcome}」、死亡確率は ${p.death}。` +
          `ただ悲観は禁物。同じシミュレーションが ${p.success} の成功可能性も示しており、道は塞がっていません。` +
          `最大の足かせは「${p.topRisk}」。突破口も明確で、${p.optimize}から着手すれば勝率は一歩ずつ取り戻せます。`
      } else if (dv >= 0.3) {
        body =
          `${p.product}（${p.type}・${p.stage}）の推演結果は一長一短でした：${bench}、最有力は「${p.outcome}」、死亡確率 ${p.death}、成功確率 ${p.success}——どちらもまだ勝負できる範囲です。` +
          `最も警戒すべきは「${p.topRisk}」。幸いレバーも見つかっています：まず${p.optimize}を固めれば、天秤は成功側に傾きます。`
      } else {
        body =
          `良い知らせです：${p.product}（${p.type}・${p.stage}）の土台はかなり堅実——${bench}、最有力は「${p.outcome}」、死亡確率は ${p.death} まで抑えられ、成功確率は ${p.success}。` +
          `とはいえ油断は禁物。「${p.topRisk}」は引き続き要注視の変数で、さらに上を目指すなら${p.optimize}に力を注ぎましょう。`
      }
      return body + p.stageHint + (p.lowConf ? ' なお、プロフィールの完成度が低めのため、この結論はまず参考程度に——データを補完して再実行すると精度が上がります。' : '')
    },
    stageHintEarly: ' まだ早期段階です。大規模投下を急がず、まずPMFをしっかり検証すれば、その後の一歩一歩に自信が持てます。',
    stageHintDecline: ' プロダクトは停滞/衰退期にあるため、本レポートは転換の出口と損切りポイントに重点を置いています——早めの方向転換もまた前進です。',
    confHigh: 'スコアの網羅性は十分——この結論は安心して参考にできます',
    confMid: 'あと数項目のスコア追加か実行回数の増加を——結論がより確かになります',
    confLow: 'データがまだ少なめです。大きな判断の前にプロフィールを補完しましょう——急がば回れ',
    publishYes: '✅ リリース可（走りながら改善）',
    publishNo: '⚠️ まず改善してから',
    improveSteps: {
      audiencePain: {
        steps: ['ターゲットユーザー8–12名にインタビューし、上位3つのペインを抽出', 'ヒーローを書き直す：課題→解決→根拠', '非コア機能を削り、主要シナリオに集中'],
        metrics: ['初日転換率', '「必須度」スコア'],
        effort: 'medium',
      },
      clarity: {
        steps: ['5秒理解テスト（画面録画で観察）', 'ファーストビューのA/B：見出し・サブコピー・社会的証明', '全体の用語と価値提案を統一'],
        metrics: ['LP転換率', 'オンボーディング完了率'],
        effort: 'low',
      },
      retentionPotential: {
        steps: ['アクティベーション・ファネルを可視化し最大離脱点を特定', 'D1/D3/D7のタッチポイントを設計', '習慣ループを追加（通知・保存・コラボ）'],
        metrics: ['D7/D30残存率', '週間アクティブ率'],
        effort: 'medium',
      },
      distributionPower: {
        steps: ['主要チャネルを選び週次獲得目標を設定', 'シェアカード・招待機能を組み込む', 'ローンチ素材テンプレを3種用意'],
        metrics: ['チャネルCPA', 'K係数 / シェア率'],
        effort: 'medium',
      },
      differentiation: {
        steps: ['競合比較表を作り唯一の差別化点を特定', '差別化点を料金ページとオンボーディングに明記', '差別化点をデモ可能にする'],
        metrics: ['競合スイッチ率', 'NPS自由回答'],
        effort: 'medium',
      },
      monetizationFit: {
        steps: ['無料/有料の境界を定義', '2段階の価格をテスト', 'トライアル→課金ファネルを追跡'],
        metrics: ['課金転換率', 'ARPU'],
        effort: 'low',
      },
      shareability: {
        steps: ['シェアできる成果物・バッジを作る', '招待インセンティブを設計', '達成の瞬間にシェアを促す'],
        metrics: ['シェア率', '招待経由登録比率'],
        effort: 'low',
      },
    },
    improveFallbackStep: '{variable} を約15ポイント引き上げる（現在 {value}）',
    improveFallbackMetrics: ['Top10%確率', '死亡確率'],
    improveFallbackTitle: '{variable} を強化',
    improveWhyNowTop: '最も弱い環は「{label}」。この変数は感度ランキング{rank}位で、先に直すROIが最大。',
    improveWhyNowRank: '感度ランキング{rank}位。成功/失敗確率への影響強度 {impact}%。',
    improveExpectedImpact: '+15後の死亡確率は約{death}%（現在{base}%から{pp}pp{dir}）· Top10%は約{topPp}pp上昇',
    dirDown: '低下',
    dirUp: '上昇',
    whyBase: '推奨度 {stars}；死亡確率 {death}、Top10% {top10}。',
    whyClarityWeak: ' 明確さが弱く、まず表現を磨くべき。',
    whyRetentionShort: ' リテンションが配信力に劣る。',
    whyNeedAcquisition: ' 獲得エンジンの補強が必要。',
    whyNeedMonetization: ' 収益化も並行して進めるべき。',
    whyWeakestDim: ' 総合の最弱次元：{label}。',
    reportSections: {
      ...en.reportSections,
      insightSummary: 'プロダクト診断サマリー',
      decisionTable: '判断項目',
      publishDecision: 'リリース推奨',
      mostLikely: '最も可能性の高い結末',
      deathProb: '死亡確率',
      successProb: '成功確率（中程度含む）',
      confidenceNote: '信頼度メモ',
      artifactType: '作品タイプ',
      stage: '現在ステージ',
      scoreDiag: 'スコア診断',
      strengths: '強み',
      weaknesses: '弱み',
      structuralRisks: '構造的リスク',
      noStrength: '明確な強みなし',
      none: 'なし',
      noStructural: '重大な構造リスクなし',
      deathAnalysis: '死亡原因分析（関連度順）',
      rootCause: '根本原因',
      scoreEvidence: 'スコア根拠',
      earlySignals: '早期シグナル',
      prevention: '予防策 / 改善',
      growthOps: '成長機会',
      trigger: 'トリガー',
      keyActions: '主要アクション',
      metricsWatch: '監視指標',
      roadmap: '行動ロードマップ',
      goals: '目標',
      tasks: 'タスク',
      improvements: '改善案（優先度順）',
      whyNow: 'なぜ今か',
      expectedImpact: '期待効果',
      concreteSteps: '具体的ステップ',
      strategyRec: '戦略推奨',
      bestFor: '適する状況',
      whyRecommended: '推奨理由',
      execList: '実行チェックリスト',
      severity: { critical: '致命的', high: '高', medium: '中' },
      urgency: { immediate: '今すぐ', short_term: '短期', long_term: '中期' },
      effort: { low: '低', medium: '中', high: '高' },
    },
    markdownReport: {
      ...en.markdownReport,
      title: '作品未来シミュレーションレポート',
      disclaimer: '本レポートはFuture Simulation Engineによる生成。モンテカルロ結果は参考情報であり、確定的予測ではありません。',
      basicInfo: '基本情報',
      project: '項目',
      name: '作品名',
      type: '作品タイプ',
      stage: '現在ステージ',
      targetUsers: 'ターゲットユーザー',
      period: 'シミュレーション期間',
      runs: '実行回数',
      confidence: '信頼度',
      completeness: 'データ完全性',
      coreJudgment: 'コア判断',
      mostLikely: '最も可能性の高い方向',
      biggestOpp: '最大の機会',
      biggestRisk: '最大のリスク',
      worthInvest: '投資価値',
      topOptimize: '最優先の改善方向',
      yes: 'はい',
      no: 'いいえ',
      legacyInsight: '旧バージョンの結果です。再実行すると完全な診断章が生成されます。',
      outcomeDist: '結果確率分布',
      ranking: 'ランキング率',
      benchmarkYes: '類似事例ライブラリに基づく',
      benchmarkNo: 'ベンチマーク不足のため内部推定',
      forecast: '主要指標予測',
      futurePaths: '最も可能性の高い未来パス',
      failurePaths: '失敗パス分析',
      successPaths: '成功パス分析',
      sensitivity: '感度分析',
      strategyCompare: '戦略比較',
      optimization: '最適化プラン',
      warnings: '早期警告指標',
      conclusion: '結論',
      worthPublish: '現バージョンはリリースに値するか',
      optimizeBeforePublish: 'リリース前に改善が必要か',
      directPublish: 'リリースして継続改善が可能',
      keepInvesting: '継続投資を推奨',
      cautionInvest: '慎重な評価が必要',
      notFilled: '未入力',
      days: '日',
      colOutcome: '結果タイプ',
      colProb: '確率',
      colIndicator: '指標',
      colValue: '確率 / 数値',
      colMedian: '中央値',
      colVariable: '変数',
      colScore: '現在スコア',
      colTop10Impact: 'Top10%への影響',
      colPriority: '優先度',
      colStrategy: '戦略',
      colDeath: '死亡確率',
      colBlockbuster: 'ヒット確率',
      colUsers: '中央ユーザー',
      colRevenue: '中央収益',
      colRecommend: '推奨度',
      colHealthy: '健全閾値',
      colDanger: '危険閾値',
      colDesc: '説明',
      rankAboveMedian: '同類中央値超え確率',
      rankExpectedPctl: '期待順位パーセンタイル',
      rankMedianPctl: '中央順位パーセンタイル',
      phase0_7: '0-7日',
      phase8_30: '8-30日',
      phase31_90: '31-90日',
      phase91_365: '91-365日',
      notCovered: 'シミュレーション期間外',
      pathStat: 'ユーザー中央値約{users}、アクティブ約{active}（アクティブ率{rate}%）、累計収益約¥{rev}',
      phaseTrend: 'フェーズ傾向：{trend}（前期比{growth}%）',
      keyRisk: '主要リスク',
      keyOpp: '主要機会',
      trendFast: '急成長',
      trendSteady: '安定成長',
      trendPlateau: '頭打ち/減速',
      trendDecline: '明確な下落',
      riskHint0_7: 'ファーストビューが不明瞭で初期ユーザーが離脱',
      oppHint0_7: 'プラットフォーム推薦で急速に立ち上がる可能性',
      riskHint8_30: 'リテンション不足で成長停滞',
      oppHint8_30: '口コミが効き始める',
      riskHint31_90: '競合ショックと新鮮さの減衰',
      oppHint31_90: 'コミュニティ形成、長期価値の顕在化',
      riskHint91_365: 'クリエイターの持続性と技術的負債',
      oppHint91_365: '二次拡散とエコシステム効果',
      pTrigger: 'トリガー',
      pProb: '発生確率',
      pSignals: '早期シグナル',
      pSolution: '解決策',
      pKeyVars: '主要変数',
      pHowImprove: '確率の高め方',
      oPriority: '優先度',
      oWhy: 'なぜ重要か',
      oSuccessImpact: '成功確率への影響',
      oFailImpact: '失敗確率への影響',
      oWhatChange: '何を変えるか',
      oVerify: '検証方法',
      oMetric: '監視指標',
      suggestOptimizeFirst: '先に改善を推奨',
      generatedAt: 'レポート生成時刻',
    },
  }
}

function buildKo(): InsightNarrative {
  const en = buildEn()
  return {
    ...en,
    painScore: (n) => `페인을 정확히 짚었어요 (${n}/100)`,
    painWeak: (n) => `페인이 아직 충분히 아프지 않아요 (${n}/100)`,
    retentionGood: (n) => `사용자가 머물러요 (${n}/100)`,
    retentionWeak: (n) => `리텐션 보강이 필요해요 (${n}/100)`,
    distributionGood: (n) => `퍼져나갈 힘이 있어요 (${n}/100)`,
    distributionWeak: (n) => `아직 목소리가 닿지 않아요 (${n}/100)`,
    clarityGood: (n) => `한눈에 이해돼요 (${n}/100)`,
    clarityWeak: (n) => `전달 방식을 더 다듬어야 해요 (${n}/100)`,
    gapRisk: (gap) => `유통-리텐션 격차 ${gap}점: '반짝하고 식는' 패턴 주의`,
    competitionRisk: '경쟁이 치열한 시장 — 차별화가 곧 생존선',
    platformRisk: '플랫폼 의존도가 높아요 — 생명줄을 남의 손에 다 맡기지 마세요',
    techDebtRisk: '기술 부채가 조용히 이터레이션을 늦추고 있어요',
    generalRoot: '현재 점수에서는 가장 약한 고리부터 무너집니다 — 민감도 우선순위대로 하나씩 보강해, 약점 하나가 전체를 가라앉히지 않게 하세요.',
    generalEvidence: (vuln) => `가장 취약한 차원: ${vuln}`,
    generalEarly: ['핵심 지표가 2주 이상 건강선 아래 — 가장 이른 구조 신호', '부정 피드백이 같은 페인에 몰리기 시작'],
    generalPrevent: ['매주 경고 지표를 점검하세요 — 터진 뒤에 돌아보지 말고', '민감도 최상위 변수부터 고치세요 — 힘은 급소에 쓰는 것'],
    knownCompetitors: (names) => `알려진 경쟁자: ${names}`,
    crashWindow: (t) => `가장 가능성 높은 붕괴 시점: ${t} — 미리 대비하세요`,
    weakPain: { ...en.weakPain, title: '페인 부족 / 가짜 수요', rootCause: '솔직히 말해, 사용자에겐 "있으면 좋고 없어도 그만"인 존재예요 — 쓰고, 결제하고, 다시 돌아올 만큼 아픈 문제가 아직 아닙니다.' },
    hypeMismatch: { ...en.hypeMismatch, title: '높은 유입·낮은 리텐션', rootCause: '화제성이 호기심 많은 사용자를 잔뜩 데려왔지만, 제품이 아직 그 트래픽을 받아내지 못했어요 — 신선함이 가시면 사람들은 떠나고, 그 열기는 허상으로 끝납니다.' },
    retentionCollapse: { ...en.retentionCollapse, title: '리텐션 붕괴', rootCause: '첫 방문에서 가치가 보이지 않았고 돌아올 습관도 생기지 않아 한 번 쓰고 떠납니다 — 사용자가 매정한 게 아니라, 머물 이유를 아직 주지 못한 것뿐이에요.' },
    distributionFailure: { ...en.distributionFailure, title: '유통 실패', rootCause: '제품 자체는 정말 괜찮을 수 있어요. 다만 새 사용자를 꾸준히 데려올 채널이 없어 "만들었는데 아무도 모르는" 상태 — 좋은 술도 골목 깊숙이 있으면 향이 닿지 않죠.' },
    competitionShock: { ...en.competitionShock, title: '경쟁 압박', rootCause: '시장은 이미 붐비고 대기업이 언제든 들어올 수 있어요 — 차별화가 단단하지 않으면, 사용자는 아무 부담 없이 갈아탑니다.' },
    platformRiskBlock: { ...en.platformRiskBlock, title: '플랫폼 의존', rootCause: '성장이나 핵심 역량이 단일 플랫폼/API에 묶여 있어요 — 저쪽 규칙이 바뀌면 사업 전체가 흔들립니다. 생명줄이 남의 손에 있는 셈이죠.' },
    monetizationFailure: { ...en.monetizationFailure, title: '사용자는 있으나 수익화 어려움', rootCause: '사용자는 모였지만 결제 의향이나 비즈니스 모델이 아직 돌아가지 않아요 — 돈을 태워 산 북적임으로는 긴 장사를 지탱할 수 없습니다.' },
    regulatory: { ...en.regulatory, title: '컴플라이언스 리스크', rootCause: '사업이 규제 레드라인 가까이에 있거나 모델 자체의 지속 가능성에 문제가 있어요 — 이런 리스크는 터지면 치명상이니, 미루지 말고 정면으로 다루는 게 좋습니다.' },
    aiCommoditization: { ...en.aiCommoditization, title: 'AI 상품화 리스크', rootCause: '핵심 역량이 서드파티 모델/플랫폼 위에 세워져 있어요 — 상류가 가격을 내리거나 무료화하거나 직접 뛰어들면, 해자는 하룻밤에 증발할 수 있습니다.' },
    headlinePublish: (outcome, weakest) => `안심하고 출시하고, 달리면서 개선하세요: 가장 유력한 시나리오는 「${outcome}」 — 다만 ${weakest}만은 계속 지켜보세요`,
    headlineHighDeath: (death, risk) => `지금은 서두르지 마세요: 실패 확률 ${death}로 높은 편 — 「${risk}」의 고비를 넘기고 출발하는 편이 훨씬 안전합니다`,
    headlineValidate: (death, direction) => `작게 시험해 보길 권해요: 실패 확률 ${death} — 먼저 「${direction}」을 보강하면 승산이 크게 올라갑니다`,
    diagnosisSummary: (p) => {
      const dv = p.deathValue ?? 0.4
      const bench = p.benchmark ? '실사례 벤치마크 대조 결과' : '몬테카를로 분포 기준'
      let body: string
      if (dv >= 0.5) {
        body =
          `솔직히 말씀드리면, ${p.product}(${p.type}·${p.stage})은 지금 꽤 어려운 국면입니다 — ${bench}, 가장 유력한 행방은 「${p.outcome}」, 실패 확률은 ${p.death}. ` +
          `하지만 낙담은 이릅니다. 같은 시뮬레이션이 ${p.success}의 성공 가능성도 보여주고 있어요 — 길이 막힌 건 아닙니다. ` +
          `지금 가장 발목을 잡는 건 「${p.topRisk}」. 돌파구도 분명합니다: ${p.optimize}부터 시작해 한 걸음씩 승률을 되찾아 오세요.`
      } else if (dv >= 0.3) {
        body =
          `${p.product}(${p.type}·${p.stage})의 이번 추연 결과는 희비가 엇갈립니다: ${bench}, 가장 유력한 건 「${p.outcome}」, 실패 확률 ${p.death}, 성공 확률 ${p.success} — 둘 다 아직 해볼 만한 범위예요. ` +
          `가장 경계할 것은 「${p.topRisk}」. 다행히 지렛대도 찾았습니다: ${p.optimize}부터 단단히 다지면 저울이 성공 쪽으로 기웁니다.`
      } else {
        body =
          `좋은 소식이에요: ${p.product}(${p.type}·${p.stage})의 기초는 상당히 탄탄합니다 — ${bench}, 가장 유력한 건 「${p.outcome}」, 실패 확률은 ${p.death}까지 눌러놨고 성공 확률은 ${p.success}. ` +
          `물론 방심은 금물. 「${p.topRisk}」은 계속 주시해야 할 변수이고, 한 단계 더 오르고 싶다면 ${p.optimize}에 힘을 실으세요.`
      }
      return body + p.stageHint + (p.lowConf ? ' 한 가지 덧붙이면, 프로필 완성도가 낮아 이 결론은 우선 참고용으로 — 데이터를 보완해 다시 돌리면 훨씬 정확해집니다.' : '')
    },
    stageHintEarly: ' 아직 초기 단계예요. 대규모 투자를 서두르지 말고 PMF부터 확실히 검증하면, 이후 한 걸음 한 걸음이 훨씬 든든해집니다.',
    stageHintDecline: ' 제품이 정체/쇠퇴기에 있어, 이 리포트는 전환 출구와 손절 지점을 찾는 데 무게를 뒀습니다 — 제때 방향을 트는 것도 전진입니다.',
    confHigh: '점수 차원이 충분히 채워졌어요 — 이 결론은 믿고 참고하셔도 됩니다',
    confMid: '차원 점수를 몇 개 더 보완하거나 실행 횟수를 늘려 보세요 — 결론이 더 단단해집니다',
    confLow: '아직 데이터가 부족해요. 큰 결정 전에 프로필부터 채우세요 — 도끼를 가는 시간은 낭비가 아닙니다',
    publishYes: '✅ 출시 가능 (달리면서 개선)',
    publishNo: '⚠️ 먼저 개선하고 출시',
    improveSteps: {
      audiencePain: {
        steps: ['타깃 사용자 8–12명 인터뷰로 상위 3개 페인 도출', '히어로 재작성: 문제→해결→근거', '비핵심 기능 제거, 주요 시나리오 집중'],
        metrics: ['첫날 전환율', '「필수성」점수'],
        effort: 'medium',
      },
      clarity: {
        steps: ['5초 이해 테스트(화면 녹화 관찰)', '첫 화면 A/B: 제목·부제·사회적 증거', '전체 용어와 가치 제안 통일'],
        metrics: ['랜딩 전환율', '온보딩 완료율'],
        effort: 'low',
      },
      retentionPotential: {
        steps: ['활성화 퍼널을 그려 최대 이탈 지점 파악', 'D1/D3/D7 터치포인트 설계', '습관 루프 추가(알림·저장·협업)'],
        metrics: ['D7/D30 리텐션', '주간 활성률'],
        effort: 'medium',
      },
      distributionPower: {
        steps: ['주력 채널 선정과 주간 획득 목표 설정', '공유 카드·초대 기능 내장', '출시 소재 템플릿 3종 준비'],
        metrics: ['채널 CPA', 'K-factor / 공유율'],
        effort: 'medium',
      },
      differentiation: {
        steps: ['경쟁 비교표로 유일한 차별점 도출', '차별점을 가격 페이지와 온보딩에 명시', '차별점을 시연 가능하게 제작'],
        metrics: ['경쟁 전환율', 'NPS 주관식'],
        effort: 'medium',
      },
      monetizationFit: {
        steps: ['무료/유료 경계 정의', '2단계 가격 테스트', '체험→결제 퍼널 추적'],
        metrics: ['유료 전환율', 'ARPU'],
        effort: 'low',
      },
      shareability: {
        steps: ['공유 가능한 결과물·배지 제작', '초대 보상 설계', '성취 순간에 공유 유도'],
        metrics: ['공유율', '초대 가입 비중'],
        effort: 'low',
      },
    },
    improveFallbackStep: '{variable} 을(를) 약 15점 끌어올리기 (현재 {value})',
    improveFallbackMetrics: ['Top10% 확률', '실패 확률'],
    improveFallbackTitle: '{variable} 강화',
    improveWhyNowTop: '가장 약한 고리는 「{label}」. 이 변수는 민감도 {rank}위로, 먼저 고치는 ROI가 가장 높음.',
    improveWhyNowRank: '민감도 {rank}위. 성공/실패 확률 영향 강도 {impact}%.',
    improveExpectedImpact: '+15 후 실패 확률 약 {death}% (현재 {base}%에서 {pp}pp {dir}) · Top10% 약 {topPp}pp 상승',
    dirDown: '감소',
    dirUp: '증가',
    whyBase: '추천 등급 {stars}; 실패 확률 {death}, Top10% {top10}.',
    whyClarityWeak: ' 명확성이 약해 표현부터 다듬어야 함.',
    whyRetentionShort: ' 리텐션이 유통력에 못 미침.',
    whyNeedAcquisition: ' 획득 엔진 보강 필요.',
    whyNeedMonetization: ' 수익화도 병행 추진 필요.',
    whyWeakestDim: ' 종합 최약 차원: {label}.',
    reportSections: {
      ...en.reportSections,
      insightSummary: '제품 진단 요약',
      decisionTable: '판단 항목',
      publishDecision: '출시 권고',
      mostLikely: '가장 가능성 높은 결말',
      deathProb: '실패 확률',
      successProb: '성공 확률(중간 성공 포함)',
      confidenceNote: '신뢰도 메모',
      artifactType: '작품 유형',
      stage: '현재 단계',
      scoreDiag: '점수 진단',
      strengths: '강점',
      weaknesses: '약점',
      structuralRisks: '구조적 리스크',
      noStrength: '뚜렷한 강점 없음',
      none: '없음',
      noStructural: '중대한 구조 리스크 없음',
      deathAnalysis: '실패 원인 분석(관련도순)',
      rootCause: '근본 원인',
      scoreEvidence: '점수 근거',
      earlySignals: '조기 신호',
      prevention: '예방책 / 개선',
      growthOps: '성장 기회',
      trigger: '트리거',
      keyActions: '핵심 액션',
      metricsWatch: '모니터링 지표',
      roadmap: '실행 로드맵',
      goals: '목표',
      tasks: '작업',
      improvements: '개선안(우선순위)',
      whyNow: '왜 지금인가',
      expectedImpact: '기대 효과',
      concreteSteps: '구체적 단계',
      strategyRec: '전략 추천',
      bestFor: '적합 상황',
      whyRecommended: '추천 이유',
      execList: '실행 체크리스트',
      severity: { critical: '치명적', high: '높음', medium: '중간' },
      urgency: { immediate: '즉시', short_term: '단기', long_term: '중기' },
      effort: { low: '낮음', medium: '중간', high: '높음' },
    },
    markdownReport: {
      ...en.markdownReport,
      title: '작품 미래 시뮬레이션 리포트',
      disclaimer: '본 리포트는 Future Simulation Engine이 생성했습니다. 몬테카를로 결과는 참고용이며 확정적 예측이 아닙니다.',
      basicInfo: '기본 정보',
      project: '항목',
      name: '작품명',
      type: '작품 유형',
      stage: '현재 단계',
      targetUsers: '타깃 사용자',
      period: '시뮬레이션 기간',
      runs: '실행 횟수',
      confidence: '신뢰도',
      completeness: '데이터 완성도',
      coreJudgment: '핵심 판단',
      mostLikely: '가장 가능성 높은 방향',
      biggestOpp: '최대 기회',
      biggestRisk: '최대 리스크',
      worthInvest: '투자 가치',
      topOptimize: '최우선 개선 방향',
      yes: '예',
      no: '아니오',
      legacyInsight: '구버전 결과입니다. 재실행하면 전체 진단 챕터가 생성됩니다.',
      outcomeDist: '결과 확률 분포',
      ranking: '랭킹 비율',
      benchmarkYes: '유사 사례 라이브러리 기반',
      benchmarkNo: '벤치마크 부족으로 내부 추정치',
      forecast: '핵심 지표 예측',
      futurePaths: '가장 가능성 높은 미래 경로',
      failurePaths: '실패 경로 분석',
      successPaths: '성공 경로 분석',
      sensitivity: '민감도 분석',
      strategyCompare: '전략 비교',
      optimization: '최적화 플랜',
      warnings: '조기 경고 지표',
      conclusion: '결론',
      worthPublish: '현재 버전 출시 가치',
      optimizeBeforePublish: '출시 전 개선 필요 여부',
      directPublish: '출시 후 지속 개선 가능',
      keepInvesting: '지속 투자 권장',
      cautionInvest: '신중한 평가 필요',
      notFilled: '미입력',
      days: '일',
      colOutcome: '결과 유형',
      colProb: '확률',
      colIndicator: '지표',
      colValue: '확률 / 수치',
      colMedian: '중앙값',
      colVariable: '변수',
      colScore: '현재 점수',
      colTop10Impact: 'Top10% 영향',
      colPriority: '우선순위',
      colStrategy: '전략',
      colDeath: '실패 확률',
      colBlockbuster: '대히트 확률',
      colUsers: '중앙 사용자',
      colRevenue: '중앙 수익',
      colRecommend: '추천 등급',
      colHealthy: '건강 임계값',
      colDanger: '위험 임계값',
      colDesc: '설명',
      rankAboveMedian: '동종 중앙값 초과 확률',
      rankExpectedPctl: '기대 순위 백분위',
      rankMedianPctl: '중앙 순위 백분위',
      phase0_7: '0-7일',
      phase8_30: '8-30일',
      phase31_90: '31-90일',
      phase91_365: '91-365일',
      notCovered: '시뮬레이션 기간 미포함',
      pathStat: '사용자 중앙값 약 {users}, 활성 약 {active} (활성률 {rate}%), 누적 수익 약 ¥{rev}',
      phaseTrend: '단계 추세: {trend} (전기 대비 {growth}%)',
      keyRisk: '핵심 리스크',
      keyOpp: '핵심 기회',
      trendFast: '급성장',
      trendSteady: '안정 성장',
      trendPlateau: '정체/둔화',
      trendDecline: '뚜렷한 하락',
      riskHint0_7: '첫 화면 메시지가 불명확해 초기 사용자 이탈',
      oppHint0_7: '플랫폼 추천으로 빠른 상승 가능',
      riskHint8_30: '리텐션 미달로 성장 정체',
      oppHint8_30: '입소문이 작동하기 시작',
      riskHint31_90: '경쟁 충격과 신선함 감쇠',
      oppHint31_90: '커뮤니티 형성, 장기 가치 가시화',
      riskHint91_365: '크리에이터 지속성과 기술 부채 부담',
      oppHint91_365: '2차 확산과 생태계 효과',
      pTrigger: '트리거',
      pProb: '발생 확률',
      pSignals: '조기 신호',
      pSolution: '해결책',
      pKeyVars: '핵심 변수',
      pHowImprove: '확률 높이는 방법',
      oPriority: '우선순위',
      oWhy: '왜 중요한가',
      oSuccessImpact: '성공 확률 영향',
      oFailImpact: '실패 확률 영향',
      oWhatChange: '무엇을 바꿀까',
      oVerify: '검증 방법',
      oMetric: '모니터링 지표',
      suggestOptimizeFirst: '먼저 개선 권장',
      generatedAt: '리포트 생성 시각',
    },
  }
}

export function getInsightNarrative(locale: Locale): InsightNarrative {
  return NARRATIVE[locale] ?? NARRATIVE['zh-CN']
}
