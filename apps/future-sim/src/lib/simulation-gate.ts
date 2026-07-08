// ============================================================
// simulation-gate — 模拟运行门禁（登录 / 点数 / 会员 / 每日额度）
// ============================================================
//
// 付费区口径（与 simulation-tiers / billing 目录一致）：
// - 基础区 quick：免费额度 免费版 5 次/天、Pro/Team 15 次/天，
//   超额后 1 点/次（需登录且余额充足）
// - 专业区 standard：3 点/次，Pro/Team 免
// - 旗舰区 deep：6 点/次，Pro/Team 免
// - 机构级 ultra：25 点/次，仅 Team 免（Pro 也需按次点数）

import type { SimMode } from '@/types'
import type { AccountUser } from '@/types/account'
import { formatGateDenied, gateActionLabel, getStoredLocale, getMessage, interpolate, type Locale } from '@/lib/i18n'

export interface SimulationGateResult {
  allowed: boolean
  reason?: 'ok' | 'login_required' | 'plan_required' | 'credits_insufficient' | 'daily_quota_exceeded'
  message?: string
  creditCost?: number
  actionHref?: string
  actionLabel?: string
  /** 基础区今日剩余免费次数（仅 quick 模式返回） */
  freeQuotaLeft?: number
}

const MODE_CREDIT_COST: Record<SimMode, number> = {
  quick: 1, // 仅在超出每日免费额度后收取
  standard: 3,
  deep: 6,
  ultra: 25,
}

/** 会员是否免除该模式点数：standard/deep 对 Pro+Team 免，ultra 仅对 Team 免 */
function planCoversMode(mode: SimMode, user: AccountUser): boolean {
  if (mode === 'ultra') return user.plan === 'team'
  return user.plan === 'pro' || user.plan === 'team'
}

// ---- 基础区每日免费额度（本地计数） ----

const QUOTA_KEY_PREFIX = 'fs_quick_quota_'

function quotaKeyToday(): string {
  return QUOTA_KEY_PREFIX + new Date().toISOString().slice(0, 10)
}

function storageAvailable(): boolean {
  return typeof localStorage !== 'undefined'
}

/** 今日已用的免费快速模拟次数 */
export function getQuickRunsToday(): number {
  if (!storageAvailable()) return 0
  const v = localStorage.getItem(quotaKeyToday())
  const n = v ? parseInt(v, 10) : 0
  return Number.isNaN(n) ? 0 : n
}

/** 记录一次快速模拟（启动成功后调用），顺带清理历史日期键 */
export function recordQuickRun(): void {
  if (!storageAvailable()) return
  const today = quotaKeyToday()
  localStorage.setItem(today, String(getQuickRunsToday() + 1))
  for (let i = localStorage.length - 1; i >= 0; i--) {
    const key = localStorage.key(i)
    if (key && key.startsWith(QUOTA_KEY_PREFIX) && key !== today) {
      localStorage.removeItem(key)
    }
  }
}

/** 基础区每日免费额度：会员 15 次，免费/未登录 5 次 */
export function quickDailyFreeLimit(user: AccountUser | null): number {
  return user && (user.plan === 'pro' || user.plan === 'team') ? 15 : 5
}

function checkQuickGate(user: AccountUser | null, locale: Locale): SimulationGateResult {
  const limit = quickDailyFreeLimit(user)
  const used = getQuickRunsToday()
  const left = Math.max(0, limit - used)

  if (left > 0) {
    return { allowed: true, reason: 'ok', creditCost: 0, freeQuotaLeft: left }
  }

  // 免费额度用尽：登录且余额足够可按次扣 1 点
  const cost = MODE_CREDIT_COST.quick
  if (!user) {
    return {
      allowed: false,
      reason: 'daily_quota_exceeded',
      message: interpolate(getMessage(locale, 'run.quotaExceededLogin'), { limit }),
      creditCost: cost,
      actionHref: `/login?return=${encodeURIComponent('/run')}`,
      actionLabel: gateActionLabel(locale, 'login_required'),
      freeQuotaLeft: 0,
    }
  }
  if (user.credits >= cost) {
    return { allowed: true, reason: 'ok', creditCost: cost, freeQuotaLeft: 0 }
  }
  return {
    allowed: false,
    reason: 'daily_quota_exceeded',
    message: interpolate(getMessage(locale, 'run.quotaExceededNoCredits'), { limit, cost, balance: user.credits }),
    creditCost: cost,
    actionHref: '/recharge',
    actionLabel: gateActionLabel(locale, 'credits_insufficient'),
    freeQuotaLeft: 0,
  }
}

export function checkSimulationGate(
  mode: SimMode,
  user: AccountUser | null,
  locale: Locale = getStoredLocale(),
): SimulationGateResult {
  if (mode === 'quick') {
    return checkQuickGate(user, locale)
  }

  const cost = MODE_CREDIT_COST[mode]

  if (!user) {
    return {
      allowed: false,
      reason: 'login_required',
      message: formatGateDenied(locale, mode, 'login_required', { cost }),
      creditCost: cost,
      actionHref: `/login?return=${encodeURIComponent('/run')}`,
      actionLabel: gateActionLabel(locale, 'login_required'),
    }
  }

  if (planCoversMode(mode, user)) {
    return { allowed: true, reason: 'ok', creditCost: 0 }
  }

  if (user.credits >= cost) {
    return { allowed: true, reason: 'ok', creditCost: cost }
  }

  return {
    allowed: false,
    reason: 'credits_insufficient',
    message: formatGateDenied(locale, mode, 'credits_insufficient', { cost, balance: user.credits }),
    creditCost: cost,
    actionHref: '/recharge',
    actionLabel: gateActionLabel(locale, 'credits_insufficient'),
  }
}

/** 本次运行应扣点数（与 checkSimulationGate 同口径） */
export function deductSimulationCredits(mode: SimMode, user: AccountUser | null): number {
  if (mode === 'quick') {
    // 免费额度内 0 点；超额 1 点（未登录本就过不了门禁）
    return getQuickRunsToday() < quickDailyFreeLimit(user) ? 0 : MODE_CREDIT_COST.quick
  }
  if (!user) return MODE_CREDIT_COST[mode]
  if (planCoversMode(mode, user)) return 0
  return MODE_CREDIT_COST[mode]
}
