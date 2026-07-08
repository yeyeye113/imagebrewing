// ============================================================
// insight-texts — 模拟诊断报告文案（四语）
// ============================================================

import type { Locale } from './types.ts'
import { getLabels } from './labels.ts'

export interface InsightTexts {
  strategyActions: Record<string, string[]>
  strategyBestFor: Record<string, string>
  scoreLabel: (v: number) => string
  dims: { pain: string; clarity: string; retention: string; distribution: string }
  /** 最可能崩盘时间的阶段文案（对应 0-7 / 7-30 / 30-90 / 90-180 天） */
  crashPhases: { p1: string; p2: string; p3: string; p4: string }
  /** 早期预警指标表（指标名/阈值/说明） */
  warningIndicators: { metric: string; healthyThreshold: string; dangerThreshold: string; description: string }[]
  pickOutcome: (op: {
    blockbuster: number
    clearSuccess: number
    moderateSuccess: number
    nicheSuccess: number
    longCompound: number
    lowAlive: number
  }) => string
  riskTopFailure: (composite: {
    painScore: number
    distributionScore: number
    retentionScore: number
    riskScore: number
    marketScore: number
  }) => string
  riskVulnerable: (composite: {
    distributionScore: number
    retentionScore: number
    painScore: number
  }) => string
  generic: string
  productFallback: string
  unspecified: string
  artifactTypicalRisk: (typeLabel: string) => string
}

const STRATEGY_ACTIONS: Record<Locale, Record<string, string[]>> = {
  'zh-CN': {
    original: ['维持当前路线，用数据验证假设后再加大投入'],
    clarity_boost: ['重做首屏：5 秒内说清「为谁、解决什么、凭什么」', '做 5 秒理解测试 + 落地页 A/B', '统一卖点文案与 onboarding 引导'],
    distribution_boost: ['设计可分享的产出物/结果页', '布局 2–3 个低成本获客渠道（SEO/社区/联盟）', '准备发布节奏与话题素材'],
    retention_boost: ['优化首次会话价值（Aha moment）', '建立 D1/D7 触达与习惯回路', '增加工作流绑定或数据沉淀'],
    monetization_boost: ['明确付费墙与核心价值对齐', '测试定价梯度与试用策略', '追踪免费→付费转化漏斗'],
    quality_boost: ['修复影响首体验的稳定性问题', '建立核心路径监控与回归测试', '降低崩溃率与关键操作失败率'],
    community_boost: ['建立核心用户群/Discord/论坛', '设计 UGC 或模板生态', '让超级用户参与共建与传播'],
  },
  'en-US': {
    original: ['Stay the course; validate with data before scaling spend'],
    clarity_boost: ['Redesign hero: who, what problem, why you in 5 seconds', 'Run 5-second comprehension tests + landing A/B', 'Align copy across onboarding'],
    distribution_boost: ['Build shareable outputs/results pages', 'Focus 2–3 low-cost channels (SEO/community/partners)', 'Plan launch cadence and talking points'],
    retention_boost: ['Improve first-session value (aha moment)', 'Build D1/D7 touchpoints and habit loops', 'Bind workflows or data lock-in'],
    monetization_boost: ['Align paywall with core value', 'Test pricing tiers and trials', 'Track free→paid funnel'],
    quality_boost: ['Fix stability on first-run path', 'Monitor core flows + regression tests', 'Reduce crashes and critical failures'],
    community_boost: ['Seed a core community (Discord/forum)', 'Design UGC or template ecosystem', 'Empower champions to co-build and spread'],
  },
  'ja-JP': {
    original: ['現状路線を維持し、データで検証してから投資を拡大'],
    clarity_boost: ['ヒーローを再設計：5秒で誰の何を解決するか', '5秒理解テスト＋LP A/B', 'オンボーディングの文案を統一'],
    distribution_boost: ['共有可能な成果物/結果ページを設計', '低コストチャネル2–3本に集中', 'ローンチ节奏と話題素材を準備'],
    retention_boost: ['初回セッション価値を最適化', 'D1/D7タッチと習慣ループ', 'ワークフロー/データの定着'],
    monetization_boost: ['ペイウォールと価値の整合', '価格帯とトライアルをテスト', '無料→有料ファネル追跡'],
    quality_boost: ['初回体験の安定性を修正', 'コアパス監視と回帰テスト', 'クラッシュ率を下げる'],
    community_boost: ['コアコミュニティを立ち上げ', 'UGC/テンプレ生態', 'スーパーユーザーと共創'],
  },
  'ko-KR': {
    original: ['현 경로 유지, 데이터 검증 후 확대 투자'],
    clarity_boost: ['히어로 재설계: 5초 안에 누구·무엇·왜', '5초 이해 테스트 + 랜딩 A/B', '온보딩 카피 통일'],
    distribution_boost: ['공유 가능한 결과물/페이지 설계', '저비용 채널 2–3개 집중', '출시 리듬·소재 준비'],
    retention_boost: ['첫 세션 가치 최적화', 'D1/D7 터치·습관 루프', '워크플로·데이터 락인'],
    monetization_boost: ['페이월과 핵심 가치 정렬', '가격·트라이얼 테스트', '무료→유료 퍼널 추적'],
    quality_boost: ['첫 경험 안정성 수정', '핵심 경로 모니터링·회귀 테스트', '크래시율 감소'],
    community_boost: ['코어 커뮤니티 구축', 'UGC/템플릿 생태', '파워 유저와 공동 성장'],
  },
}

const STRATEGY_BEST_FOR: Record<Locale, Record<string, string>> = {
  'zh-CN': {
    original: '指标均衡、需要先验证 PMF',
    clarity_boost: '产品好但用户看不懂、转化低',
    distribution_boost: '留存尚可但获客乏力',
    retention_boost: '有流量但 D7/D30 留存差',
    monetization_boost: '有活跃用户但收入薄弱',
    quality_boost: '差评/崩溃拖累口碑',
    community_boost: '利基圈层强、适合口碑复利',
  },
  'en-US': {
    original: 'Balanced metrics; validate PMF first',
    clarity_boost: 'Strong product, weak comprehension/conversion',
    distribution_boost: 'Retention OK but acquisition weak',
    retention_boost: 'Traffic without D7/D30 retention',
    monetization_boost: 'Active users but weak revenue',
    quality_boost: 'Reviews/crashes hurt reputation',
    community_boost: 'Strong niche; word-of-mouth play',
  },
  'ja-JP': {
    original: 'バランス型・PMF検証優先',
    clarity_boost: '製品は良いが理解/転換が弱い',
    distribution_boost: 'リテンションはあるが獲得弱い',
    retention_boost: '流入はあるがD7/D30が弱い',
    monetization_boost: 'アクティブだが収益弱い',
    quality_boost: '低評価/クラッシュが足かせ',
    community_boost: 'ニッチが強く口コミ向き',
  },
  'ko-KR': {
    original: '균형 지표·PMF 검증 우선',
    clarity_boost: '제품은 좋으나 이해/전환 약함',
    distribution_boost: '리텐션은 되나 유입 약함',
    retention_boost: '트래픽은 있으나 D7/D30 약함',
    monetization_boost: '활성은 있으나 수익 약함',
    quality_boost: '악평/크래시가 발목',
    community_boost: '니치 강함·입소문형',
  },
}

const CRASH_PHASES: Record<Locale, { p1: string; p2: string; p3: string; p4: string }> = {
  'zh-CN': { p1: '第 1-7 天', p2: '第 7-30 天', p3: '第 30-90 天', p4: '第 90-180 天' },
  'en-US': { p1: 'Day 1-7', p2: 'Day 7-30', p3: 'Day 30-90', p4: 'Day 90-180' },
  'ja-JP': { p1: '1-7日目', p2: '7-30日目', p3: '30-90日目', p4: '90-180日目' },
  'ko-KR': { p1: '1-7일차', p2: '7-30일차', p3: '30-90일차', p4: '90-180일차' },
}

type WarningRow = { metric: string; healthyThreshold: string; dangerThreshold: string; description: string }

const WARNING_INDICATORS: Record<Locale, WarningRow[]> = {
  'zh-CN': [
    { metric: '首日转化率', healthyThreshold: '> 5%', dangerThreshold: '< 1%', description: '曝光到用户的转化效率' },
    { metric: 'D7 留存', healthyThreshold: '> 18%', dangerThreshold: '< 8%', description: '用户7天后是否还在使用（最关键指标）' },
    { metric: 'D30 留存', healthyThreshold: '> 10%', dangerThreshold: '< 3%', description: '用户30天后是否还在使用' },
    { metric: '分享率', healthyThreshold: '> 3%', dangerThreshold: '< 0.5%', description: '用户主动分享比例' },
    { metric: '差评率', healthyThreshold: '< 5%', dangerThreshold: '> 15%', description: '负面反馈比例' },
    { metric: '活跃增长率', healthyThreshold: '> 5%/周', dangerThreshold: '< 0%/周', description: '活跃用户增长趋势' },
    { metric: '付费转化率', healthyThreshold: '> 3%', dangerThreshold: '< 0.5%', description: '免费到付费转化' },
  ],
  'en-US': [
    { metric: 'Day-1 conversion', healthyThreshold: '> 5%', dangerThreshold: '< 1%', description: 'Exposure-to-user efficiency' },
    { metric: 'D7 retention', healthyThreshold: '> 18%', dangerThreshold: '< 8%', description: 'Still active after 7 days (most critical)' },
    { metric: 'D30 retention', healthyThreshold: '> 10%', dangerThreshold: '< 3%', description: 'Still active after 30 days' },
    { metric: 'Share rate', healthyThreshold: '> 3%', dangerThreshold: '< 0.5%', description: 'Users who share proactively' },
    { metric: 'Negative reviews', healthyThreshold: '< 5%', dangerThreshold: '> 15%', description: 'Negative feedback share' },
    { metric: 'Active growth', healthyThreshold: '> 5%/wk', dangerThreshold: '< 0%/wk', description: 'Active user trend' },
    { metric: 'Paid conversion', healthyThreshold: '> 3%', dangerThreshold: '< 0.5%', description: 'Free-to-paid conversion' },
  ],
  'ja-JP': [
    { metric: '初日転換率', healthyThreshold: '> 5%', dangerThreshold: '< 1%', description: '露出→ユーザー転換効率' },
    { metric: 'D7残存', healthyThreshold: '> 18%', dangerThreshold: '< 8%', description: '7日後の継続利用（最重要）' },
    { metric: 'D30残存', healthyThreshold: '> 10%', dangerThreshold: '< 3%', description: '30日後の継続利用' },
    { metric: 'シェア率', healthyThreshold: '> 3%', dangerThreshold: '< 0.5%', description: '自発的シェア比率' },
    { metric: '低評価率', healthyThreshold: '< 5%', dangerThreshold: '> 15%', description: 'ネガティブ反応比率' },
    { metric: 'アクティブ成長', healthyThreshold: '> 5%/週', dangerThreshold: '< 0%/週', description: 'アクティブ増加傾向' },
    { metric: '課金転換率', healthyThreshold: '> 3%', dangerThreshold: '< 0.5%', description: '無料→有料転換' },
  ],
  'ko-KR': [
    { metric: '첫날 전환율', healthyThreshold: '> 5%', dangerThreshold: '< 1%', description: '노출→사용자 전환 효율' },
    { metric: 'D7 리텐션', healthyThreshold: '> 18%', dangerThreshold: '< 8%', description: '7일 후 사용 여부 (가장 중요)' },
    { metric: 'D30 리텐션', healthyThreshold: '> 10%', dangerThreshold: '< 3%', description: '30일 후 사용 여부' },
    { metric: '공유율', healthyThreshold: '> 3%', dangerThreshold: '< 0.5%', description: '자발적 공유 비율' },
    { metric: '악평률', healthyThreshold: '< 5%', dangerThreshold: '> 15%', description: '부정 피드백 비율' },
    { metric: '활성 성장률', healthyThreshold: '> 5%/주', dangerThreshold: '< 0%/주', description: '활성 사용자 추세' },
    { metric: '유료 전환율', healthyThreshold: '> 3%', dangerThreshold: '< 0.5%', description: '무료→유료 전환' },
  ],
}

function scoreLabel(locale: Locale, v: number): string {
  const tiers =
    locale === 'zh-CN'
      ? { hi: '强', mid: '中', low: '偏弱', weak: '弱' }
      : locale === 'ja-JP'
        ? { hi: '強', mid: '中', low: 'やや弱', weak: '弱' }
        : locale === 'ko-KR'
          ? { hi: '강', mid: '중', low: '약함', weak: '약' }
          : { hi: 'strong', mid: 'medium', low: 'weak', weak: 'very weak' }
  if (v >= 75) return tiers.hi
  if (v >= 55) return tiers.mid
  if (v >= 35) return tiers.low
  return tiers.weak
}

export function getInsightTexts(locale: Locale): InsightTexts {
  const labels = getLabels(locale)
  const o = labels.outcome

  return {
    strategyActions: STRATEGY_ACTIONS[locale] ?? STRATEGY_ACTIONS['zh-CN'],
    strategyBestFor: STRATEGY_BEST_FOR[locale] ?? STRATEGY_BEST_FOR['zh-CN'],
    scoreLabel: (v) => scoreLabel(locale, v),
    crashPhases: CRASH_PHASES[locale] ?? CRASH_PHASES['zh-CN'],
    warningIndicators: WARNING_INDICATORS[locale] ?? WARNING_INDICATORS['zh-CN'],
    dims: {
      pain:
        locale === 'zh-CN' ? '痛点强度' : locale === 'ja-JP' ? 'ペイン強度' : locale === 'ko-KR' ? '페인 강도' : 'Audience pain',
      clarity: locale === 'zh-CN' ? '清晰度' : locale === 'ja-JP' ? '明確さ' : locale === 'ko-KR' ? '명확성' : 'Clarity',
      retention:
        locale === 'zh-CN' ? '留存能力' : locale === 'ja-JP' ? 'リテンション' : locale === 'ko-KR' ? '리텐션' : 'Retention',
      distribution:
        locale === 'zh-CN' ? '分发能力' : locale === 'ja-JP' ? '配信力' : locale === 'ko-KR' ? '유통력' : 'Distribution',
    },
    pickOutcome: (op) =>
      op.blockbuster > 0.1
        ? o.blockbuster
        : op.clearSuccess > 0.2
          ? o.clear_success
          : op.moderateSuccess > 0.25
            ? o.moderate_success
            : op.nicheSuccess > 0.2
              ? o.niche_success
              : op.longCompound > 0.15
                ? o.long_compound
                : op.lowAlive > 0.3
                  ? o.low_alive
                  : o.dead,
    riskTopFailure: (c) => {
      if (c.painScore < 40) return locale === 'zh-CN' ? '痛点强度不足' : locale === 'ja-JP' ? 'ペイン不足' : locale === 'ko-KR' ? '페인 부족' : 'Insufficient audience pain'
      if (c.distributionScore < 35) return locale === 'zh-CN' ? '分发能力不足' : locale === 'ja-JP' ? '配信力不足' : locale === 'ko-KR' ? '유통력 부족' : 'Weak distribution'
      if (c.retentionScore < 40) return locale === 'zh-CN' ? '留存不达标' : locale === 'ja-JP' ? 'リテンション不足' : locale === 'ko-KR' ? '리텐션 미달' : 'Poor retention'
      if (c.riskScore < 35) return locale === 'zh-CN' ? '综合风险过高' : locale === 'ja-JP' ? '総合リスク高' : locale === 'ko-KR' ? '종합 리스크 과다' : 'High overall risk'
      if (c.marketScore < 40) return locale === 'zh-CN' ? '市场需求不足' : locale === 'ja-JP' ? '市場需要不足' : locale === 'ko-KR' ? '시장 수요 부족' : 'Weak market demand'
      return locale === 'zh-CN' ? '竞争压力过大' : locale === 'ja-JP' ? '競争過多' : locale === 'ko-KR' ? '경쟁 과열' : 'Intense competition'
    },
    riskVulnerable: (c) => {
      if (c.distributionScore < c.retentionScore) return getInsightTexts(locale).dims.distribution
      if (c.retentionScore < c.painScore) return getInsightTexts(locale).dims.retention
      return getInsightTexts(locale).dims.pain
    },
    generic: locale === 'zh-CN' ? '通用' : locale === 'ja-JP' ? '汎用' : locale === 'ko-KR' ? '일반' : 'General',
    productFallback: locale === 'zh-CN' ? '该产品' : locale === 'ja-JP' ? '当該プロダクト' : locale === 'ko-KR' ? '해당 제품' : 'This product',
    unspecified: locale === 'zh-CN' ? '未指定' : locale === 'ja-JP' ? '未指定' : locale === 'ko-KR' ? '미지정' : 'Unspecified',
    artifactTypicalRisk: (typeLabel) =>
      locale === 'zh-CN'
        ? `（${typeLabel} 典型风险）`
        : locale === 'ja-JP'
          ? `（${typeLabel}の典型リスク）`
          : locale === 'ko-KR'
            ? ` (${typeLabel} 전형적 리스크)`
            : ` (${typeLabel} typical risk)`,
  }
}
