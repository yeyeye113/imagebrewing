// ============================================================
// useT — 翻译 hook
// ============================================================

import { useLocaleStore } from '@/store/locale'
import { t, interpolate, type MessageKey } from '@/lib/i18n'

export function useT() {
  const locale = useLocaleStore((s) => s.locale)
  return (key: MessageKey, vars?: Record<string, string | number>) => {
    const raw = t(locale, key)
    return vars ? interpolate(raw, vars) : raw
  }
}

export function useLocale() {
  return useLocaleStore((s) => s.locale)
}
