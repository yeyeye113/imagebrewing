// ============================================================
// i18n types
// ============================================================

export type Locale = 'zh-CN' | 'en-US' | 'ja-JP' | 'ko-KR'

export const LOCALES: Locale[] = ['zh-CN', 'en-US', 'ja-JP', 'ko-KR']

export const LOCALE_LABELS: Record<Locale, string> = {
  'zh-CN': '简体中文',
  'en-US': 'English',
  'ja-JP': '日本語',
  'ko-KR': '한국어',
}

export const LOCALE_SHORT: Record<Locale, string> = {
  'zh-CN': '中',
  'en-US': 'EN',
  'ja-JP': '日',
  'ko-KR': '한',
}

export const BCP47: Record<Locale, string> = {
  'zh-CN': 'zh-CN',
  'en-US': 'en-US',
  'ja-JP': 'ja-JP',
  'ko-KR': 'ko-KR',
}
