// i18n core
import type { Locale } from './types.ts'
import { BCP47 } from './types.ts'
import { getMessage, type MessageKey } from './messages/index.ts'

export * from './types.ts'
export * from './labels.ts'
export { getMessage, type MessageKey } from './messages/index.ts'
export { getOnboardingByPath } from './onboarding.ts'
export { formatGateDenied, gateActionLabel } from './gate.ts'
export { getInsightTexts } from './insight-texts.ts'
export { getInsightNarrative } from './insight-narrative.ts'
export { getBillingCatalog } from './billing.ts'

const STORAGE_KEY = 'fs_locale'

export function getStoredLocale(): Locale {
  const v = localStorage.getItem(STORAGE_KEY)
  if (v === 'zh-CN' || v === 'en-US' || v === 'ja-JP' || v === 'ko-KR') return v
  const nav = navigator.language
  if (nav.startsWith('zh')) return 'zh-CN'
  if (nav.startsWith('ja')) return 'ja-JP'
  if (nav.startsWith('ko')) return 'ko-KR'
  return 'en-US'
}

export function setStoredLocale(locale: Locale): void {
  localStorage.setItem(STORAGE_KEY, locale)
  document.documentElement.lang = BCP47[locale]
}

export function t(locale: Locale, key: MessageKey): string {
  return getMessage(locale, key)
}

export function initLocale(): Locale {
  const locale = getStoredLocale()
  setStoredLocale(locale)
  return locale
}

export function interpolate(template: string, vars: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? ''))
}
