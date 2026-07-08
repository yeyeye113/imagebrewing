// ============================================================
// billing i18n — 定价/充值文案（四语）
// ============================================================

import type { Locale } from './types.ts'
import type { PlanId } from '@/types/account'

export interface BillingCatalog {
  notice: string
  audience: { primary: string; secondary: string; anchor: string }
  simulationTiers: { mode: string; runs: number; payg: string; proIncluded: string; deepNote: string }[]
  creditPacks: { id: string; credits: number; priceLabel: string; priceCents: number; unit: string; tag: string }[]
  creditRules: { action: string; cost: string }[]
  membershipPlans: {
    id: PlanId
    name: string
    priceLabel: string
    period: string
    yearly?: string
    highlight: boolean
    features: string[]
    limits: string[]
  }[]
  subscriptionSkus: { id: string; planId: PlanId; label: string; priceLabel: string; priceCents: number; cycle: 'monthly' | 'yearly' }[]
}

const CATALOG: Record<Locale, BillingCatalog> = {
  'zh-CN': {
    notice: '支付与会员能力为预留方案，当前未接入真实支付通道。',
    audience: {
      primary: '独立开发者、产品经理、一人公司创始人',
      secondary: '小型工作室、天使前轮创业团队、个人 IP 创作者',
      anchor: '一次「找顾问聊 1 小时」≈ ¥300–800；本工具一次深度推演 ≈ 一杯咖啡钱',
    },
    simulationTiers: [
      { mode: '快速 · 基础区', runs: 10000, payg: '¥1.9 / 次', proIncluded: '免费（每日 15 次）', deepNote: '摸方向、改一版 UI 后快速复测' },
      { mode: '标准 · 专业区', runs: 50000, payg: '¥6.9 / 次', proIncluded: '¥0（每月 60 次）', deepNote: '日常迭代前「该不该发」决策' },
      { mode: '深度 · 旗舰区', runs: 100000, payg: '¥12.9 / 次', proIncluded: '¥0（每月 25 次）', deepNote: '融资 BP、重大版本、付费转化前' },
      { mode: '机构级', runs: 500000, payg: '¥49 / 次', proIncluded: 'Team 含 15 次/月', deepNote: '多作品组合、投资侧批量筛查' },
    ],
    creditPacks: [
      { id: 'pack_30', credits: 30, priceLabel: '¥19.9', priceCents: 1990, unit: '≈ ¥0.66/次（按快速计）', tag: '首充推荐' },
      { id: 'pack_120', credits: 120, priceLabel: '¥69', priceCents: 6900, unit: '≈ ¥0.58/次', tag: '月 casual' },
      { id: 'pack_400', credits: 400, priceLabel: '¥199', priceCents: 19900, unit: '≈ ¥0.50/次', tag: '重度个人' },
    ],
    creditRules: [
      { action: '快速模拟（1 万次）', cost: '1 点' },
      { action: '标准模拟（5 万次）', cost: '3 点' },
      { action: '深度模拟（10 万次）', cost: '6 点' },
      { action: '机构级（50 万次）', cost: '25 点' },
      { action: 'PDF 报告导出', cost: '2 点 / 份' },
      { action: '案例库对标（单案）', cost: '4 点 / 案' },
    ],
    membershipPlans: [
      {
        id: 'free',
        name: '免费版',
        priceLabel: '¥0',
        period: '永久',
        highlight: false,
        features: ['最多 5 个项目', '基础区：快速模拟 5 次 / 天', '死亡概率 + 置信区间 + 诊断摘要', 'Markdown 报告复制', '本地运行，零上传'],
        limits: ['专业/旗舰区按次消耗点数', '无 JSON 导出', '无案例库对标'],
      },
      {
        id: 'pro',
        name: 'Pro 会员',
        priceLabel: '¥39',
        period: '/ 月',
        yearly: '年付 ¥299（约 ¥25/月）',
        highlight: true,
        features: ['无限项目', '三大付费区额度内 ¥0', '专业区：路径带 + 里程碑 + 完整诊断', '旗舰区：生存分析 + 场景分解 + LTV + 案例对标', 'JSON / Markdown 导出', '超额按次 8 折'],
        limits: [],
      },
      {
        id: 'team',
        name: 'Team',
        priceLabel: '¥149',
        period: '/ 月',
        yearly: '年付 ¥1,199（5 席位）',
        highlight: false,
        features: ['Pro 能力 × 5 席位', '共享空间 & 报告批注', '机构级模拟 15 次 / 月', '多作品对比看板'],
        limits: [],
      },
    ],
    subscriptionSkus: [
      { id: 'sub_pro_monthly', planId: 'pro', label: 'Pro 月付', priceLabel: '¥39/月', priceCents: 3900, cycle: 'monthly' },
      { id: 'sub_pro_yearly', planId: 'pro', label: 'Pro 年付', priceLabel: '¥299/年', priceCents: 29900, cycle: 'yearly' },
      { id: 'sub_team_monthly', planId: 'team', label: 'Team 月付', priceLabel: '¥149/月', priceCents: 14900, cycle: 'monthly' },
    ],
  },
  'en-US': {
    notice: 'Payments and membership are preview-only; no real payment channel is connected.',
    audience: {
      primary: 'Indie devs, PMs, solo founders',
      secondary: 'Small studios, pre-seed teams, creator IPs',
      anchor: '1h advisor chat ≈ ¥300–800; one deep run here ≈ a coffee',
    },
    simulationTiers: [
      { mode: 'Quick · Basic', runs: 10000, payg: '¥1.9 / run', proIncluded: 'Free (15/day)', deepNote: 'Direction checks & quick UI retests' },
      { mode: 'Standard · Pro Zone', runs: 50000, payg: '¥6.9 / run', proIncluded: '¥0 (60/mo)', deepNote: 'Ship / no-ship before iteration' },
      { mode: 'Deep · Flagship', runs: 100000, payg: '¥12.9 / run', proIncluded: '¥0 (25/mo)', deepNote: 'Fundraising, major releases, monetization' },
      { mode: 'Institutional', runs: 500000, payg: '¥49 / run', proIncluded: 'Team 15/mo', deepNote: 'Portfolio screening & batch review' },
    ],
    creditPacks: [
      { id: 'pack_30', credits: 30, priceLabel: '¥19.9', priceCents: 1990, unit: '≈ ¥0.66/run (quick)', tag: 'First top-up' },
      { id: 'pack_120', credits: 120, priceLabel: '¥69', priceCents: 6900, unit: '≈ ¥0.58/run', tag: 'Casual monthly' },
      { id: 'pack_400', credits: 400, priceLabel: '¥199', priceCents: 19900, unit: '≈ ¥0.50/run', tag: 'Power user' },
    ],
    creditRules: [
      { action: 'Quick (10K runs)', cost: '1 credit' },
      { action: 'Standard (50K runs)', cost: '3 credits' },
      { action: 'Deep (100K runs)', cost: '6 credits' },
      { action: 'Institutional (500K)', cost: '25 credits' },
      { action: 'PDF export', cost: '2 credits / file' },
      { action: 'Benchmark case', cost: '4 credits / case' },
    ],
    membershipPlans: [
      {
        id: 'free',
        name: 'Free',
        priceLabel: '¥0',
        period: 'forever',
        highlight: false,
        features: ['Up to 5 projects', 'Basic zone: 5 quick runs / day', 'Death odds + CI + summary diagnosis', 'Copy Markdown report', 'Runs locally, no upload'],
        limits: ['Pro/Flagship zones cost credits', 'No JSON export', 'No benchmark cases'],
      },
      {
        id: 'pro',
        name: 'Pro',
        priceLabel: '¥39',
        period: '/ mo',
        yearly: '¥299/yr (~¥25/mo)',
        highlight: true,
        features: ['Unlimited projects', 'All three zones at ¥0 within quota', 'Pro zone: bands + milestones + full diagnosis', 'Flagship: survival + scenarios + LTV + benchmark', 'JSON / Markdown export', '20% off overage runs'],
        limits: [],
      },
      {
        id: 'team',
        name: 'Team',
        priceLabel: '¥149',
        period: '/ mo',
        yearly: '¥1,199/yr (5 seats)',
        highlight: false,
        features: ['Pro × 5 seats', 'Shared space & report notes', '15 institutional runs / mo', 'Multi-product dashboard'],
        limits: [],
      },
    ],
    subscriptionSkus: [
      { id: 'sub_pro_monthly', planId: 'pro', label: 'Pro monthly', priceLabel: '¥39/mo', priceCents: 3900, cycle: 'monthly' },
      { id: 'sub_pro_yearly', planId: 'pro', label: 'Pro yearly', priceLabel: '¥299/yr', priceCents: 29900, cycle: 'yearly' },
      { id: 'sub_team_monthly', planId: 'team', label: 'Team monthly', priceLabel: '¥149/mo', priceCents: 14900, cycle: 'monthly' },
    ],
  },
  'ja-JP': {
    notice: '決済・メンバーシップはプレビューです。実際の決済チャネルは未接続です。',
    audience: {
      primary: 'インディー開発者、PM、一人起業家',
      secondary: '小規模スタジオ、プレシードチーム、クリエイター',
      anchor: 'アドバイザー1時間 ≈ ¥300–800；本ツールの深い1回 ≈ コーヒー1杯',
    },
    simulationTiers: [
      { mode: 'クイック · ベーシック', runs: 10000, payg: '¥1.9 / 回', proIncluded: '無料（15回/日）', deepNote: '方向性確認・UI再テスト' },
      { mode: '標準 · プロゾーン', runs: 50000, payg: '¥6.9 / 回', proIncluded: '¥0（60回/月）', deepNote: 'リリース前の判断' },
      { mode: 'ディープ · フラッグシップ', runs: 100000, payg: '¥12.9 / 回', proIncluded: '¥0（25回/月）', deepNote: '資金調達・大型リリース前' },
      { mode: '機関向け', runs: 500000, payg: '¥49 / 回', proIncluded: 'Team 15回/月', deepNote: '複数作品・投資スクリーニング' },
    ],
    creditPacks: [
      { id: 'pack_30', credits: 30, priceLabel: '¥19.9', priceCents: 1990, unit: '≈ ¥0.66/回', tag: '初回おすすめ' },
      { id: 'pack_120', credits: 120, priceLabel: '¥69', priceCents: 6900, unit: '≈ ¥0.58/回', tag: 'カジュアル' },
      { id: 'pack_400', credits: 400, priceLabel: '¥199', priceCents: 19900, unit: '≈ ¥0.50/回', tag: 'ヘビーユーザー' },
    ],
    creditRules: [
      { action: 'クイック（1万回）', cost: '1ポイント' },
      { action: '標準（5万回）', cost: '3ポイント' },
      { action: 'ディープ（10万回）', cost: '6ポイント' },
      { action: '機関向け（50万回）', cost: '25ポイント' },
      { action: 'PDFエクスポート', cost: '2ポイント / 件' },
      { action: 'ベンチマーク案件', cost: '4ポイント / 件' },
    ],
    membershipPlans: [
      {
        id: 'free',
        name: '無料',
        priceLabel: '¥0',
        period: '永久',
        highlight: false,
        features: ['最大5プロジェクト', 'ベーシック：クイック5回/日', '死亡確率+信頼区間+診断サマリー', 'Markdownコピー', 'ローカル実行・アップロードなし'],
        limits: ['プロ/フラッグシップはポイント制', 'JSONエクスポートなし', 'ベンチマークなし'],
      },
      {
        id: 'pro',
        name: 'Pro',
        priceLabel: '¥39',
        period: '/ 月',
        yearly: '年払い ¥299',
        highlight: true,
        features: ['無制限プロジェクト', '3ゾーン枠内¥0', 'プロ：バンド+マイルストーン+完全診断', 'フラッグシップ：生存分析+シナリオ+LTV+ベンチマーク', 'JSON/Markdown', '超過20%オフ'],
        limits: [],
      },
      {
        id: 'team',
        name: 'Team',
        priceLabel: '¥149',
        period: '/ 月',
        yearly: '年払い ¥1,199（5席）',
        highlight: false,
        features: ['Pro×5席', '共有スペース', '機関向け15回/月', '複数作品ダッシュボード'],
        limits: [],
      },
    ],
    subscriptionSkus: [
      { id: 'sub_pro_monthly', planId: 'pro', label: 'Pro 月払い', priceLabel: '¥39/月', priceCents: 3900, cycle: 'monthly' },
      { id: 'sub_pro_yearly', planId: 'pro', label: 'Pro 年払い', priceLabel: '¥299/年', priceCents: 29900, cycle: 'yearly' },
      { id: 'sub_team_monthly', planId: 'team', label: 'Team 月払い', priceLabel: '¥149/月', priceCents: 14900, cycle: 'monthly' },
    ],
  },
  'ko-KR': {
    notice: '결제 및 멤버십은 미리보기이며 실제 결제 채널이 연결되지 않았습니다.',
    audience: {
      primary: '인디 개발자, PM, 1인 창업가',
      secondary: '소규모 스튜디오, 프리시드 팀, 크리에이터',
      anchor: '자문 1시간 ≈ ¥300–800; 심층 1회 ≈ 커피 한 잔',
    },
    simulationTiers: [
      { mode: '빠른 · 베이직', runs: 10000, payg: '¥1.9 / 회', proIncluded: '무료 (15회/일)', deepNote: '방향 탐색·UI 재테스트' },
      { mode: '표준 · 프로 존', runs: 50000, payg: '¥6.9 / 회', proIncluded: '¥0 (60회/월)', deepNote: '출시 전 의사결정' },
      { mode: '심층 · 플래그십', runs: 100000, payg: '¥12.9 / 회', proIncluded: '¥0 (25회/월)', deepNote: '투자·대형 릴리스·수익화 전' },
      { mode: '기관', runs: 500000, payg: '¥49 / 회', proIncluded: 'Team 15회/월', deepNote: '다작품·투자 스크리닝' },
    ],
    creditPacks: [
      { id: 'pack_30', credits: 30, priceLabel: '¥19.9', priceCents: 1990, unit: '≈ ¥0.66/회', tag: '첫 충전 추천' },
      { id: 'pack_120', credits: 120, priceLabel: '¥69', priceCents: 6900, unit: '≈ ¥0.58/회', tag: '캐주얼' },
      { id: 'pack_400', credits: 400, priceLabel: '¥199', priceCents: 19900, unit: '≈ ¥0.50/회', tag: '헤비 유저' },
    ],
    creditRules: [
      { action: '빠른 (1만 회)', cost: '1포인트' },
      { action: '표준 (5만 회)', cost: '3포인트' },
      { action: '심층 (10만 회)', cost: '6포인트' },
      { action: '기관 (50만 회)', cost: '25포인트' },
      { action: 'PDF보내기', cost: '2포인트 / 건' },
      { action: '벤치마크 케이스', cost: '4포인트 / 건' },
    ],
    membershipPlans: [
      {
        id: 'free',
        name: '무료',
        priceLabel: '¥0',
        period: '영구',
        highlight: false,
        features: ['최대 5 프로젝트', '베이직: 빠른 5회/일', '실패 확률+신뢰구간+진단 요약', 'Markdown 복사', '로컬 실행·업로드 없음'],
        limits: ['프로/플래그십은 포인트제', 'JSON보내기 없음', '벤치마크 없음'],
      },
      {
        id: 'pro',
        name: 'Pro',
        priceLabel: '¥39',
        period: '/ 월',
        yearly: '연 ¥299',
        highlight: true,
        features: ['무제한 프로젝트', '3개 존 할당량 내 ¥0', '프로: 밴드+마일스톤+전체 진단', '플래그십: 생존 분석+시나리오+LTV+벤치마크', 'JSON/Markdown', '초과 20% 할인'],
        limits: [],
      },
      {
        id: 'team',
        name: 'Team',
        priceLabel: '¥149',
        period: '/ 월',
        yearly: '연 ¥1,199 (5석)',
        highlight: false,
        features: ['Pro×5석', '공유 공간', '기관 15회/월', '다작품 대시보드'],
        limits: [],
      },
    ],
    subscriptionSkus: [
      { id: 'sub_pro_monthly', planId: 'pro', label: 'Pro 월간', priceLabel: '¥39/월', priceCents: 3900, cycle: 'monthly' },
      { id: 'sub_pro_yearly', planId: 'pro', label: 'Pro 연간', priceLabel: '¥299/년', priceCents: 29900, cycle: 'yearly' },
      { id: 'sub_team_monthly', planId: 'team', label: 'Team 월간', priceLabel: '¥149/월', priceCents: 14900, cycle: 'monthly' },
    ],
  },
}

export function getBillingCatalog(locale: Locale): BillingCatalog {
  return CATALOG[locale] ?? CATALOG['zh-CN']
}
