// ============================================================
// Locale store
// ============================================================

import { create } from 'zustand'
import { getStoredLocale, setStoredLocale, type Locale } from '@/lib/i18n'

interface LocaleState {
  locale: Locale
  setLocale: (locale: Locale) => void
  hydrate: () => void
}

export const useLocaleStore = create<LocaleState>((set) => ({
  locale: getStoredLocale(),
  hydrate: () => set({ locale: getStoredLocale() }),
  setLocale: (locale) => {
    setStoredLocale(locale)
    set({ locale })
  },
}))
