// ============================================================
// Onboarding — 首次使用引导（i18n）
// ============================================================

import { getOnboardingByPath, type Locale } from '@/lib/i18n'
import { getStoredLocale } from '@/lib/i18n'

const KEY = 'fs_onboarding_v1'

export function shouldShowOnboarding(): boolean {
  return localStorage.getItem(KEY) === 'active'
}

export function startOnboarding(): void {
  localStorage.setItem(KEY, 'active')
}

export function completeOnboarding(): void {
  localStorage.setItem(KEY, 'done')
}

export function dismissOnboarding(): void {
  localStorage.setItem(KEY, 'done')
}

export function getOnboardingForPath(pathname: string, locale?: Locale) {
  const loc = locale ?? getStoredLocale()
  return getOnboardingByPath(loc)[pathname]
}

/** @deprecated use getOnboardingForPath */
export const ONBOARDING_BY_PATH = getOnboardingByPath('zh-CN')
