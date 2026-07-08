// ============================================================
// LanguageToggle — 四语切换（顶栏胶囊 / 设置页大按钮）
// ============================================================

import { cn } from '@/lib/utils'
import { LOCALES, LOCALE_SHORT, type Locale } from '@/lib/i18n'
import { useLocaleStore } from '@/store/locale'
import { Languages } from 'lucide-react'

interface LanguageToggleProps {
  variant?: 'compact' | 'prominent'
  className?: string
}

export function LanguageToggle({ variant = 'compact', className }: LanguageToggleProps) {
  const locale = useLocaleStore((s) => s.locale)
  const setLocale = useLocaleStore((s) => s.setLocale)

  if (variant === 'prominent') {
    return (
      <div className={cn('grid grid-cols-1 sm:grid-cols-2 gap-3', className)}>
        {LOCALES.map((loc) => {
          const active = locale === loc
          return (
            <button
              key={loc}
              type="button"
              onClick={() => setLocale(loc)}
              className={cn(
                'flex items-center gap-3 rounded-xl border-2 px-4 py-4 text-left transition-all',
                active
                  ? 'border-gray-900 dark:border-gray-100 bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 shadow-md'
                  : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-300 hover:border-gray-400',
              )}
            >
              <Languages className={cn('w-6 h-6 shrink-0', active ? 'opacity-90' : 'opacity-60')} />
              <div>
                <div className="font-semibold text-base">{LOCALE_LABELS_DISPLAY[loc]}</div>
                <div className={cn('text-xs mt-0.5', active ? 'opacity-80' : 'text-gray-500')}>{loc}</div>
              </div>
            </button>
          )
        })}
      </div>
    )
  }

  return (
    <div
      className={cn(
        'inline-flex items-center gap-0.5 rounded-full border-2 border-gray-900/15 dark:border-gray-100/20',
        'bg-white dark:bg-gray-900 p-0.5 shadow-sm max-w-[9rem]',
        className,
      )}
      role="group"
      aria-label="Language"
    >
      <Languages className="w-3 h-3 text-gray-500 dark:text-gray-400 ml-1.5 shrink-0 hidden xs:block" />
      {LOCALES.map((loc) => (
        <button
          key={loc}
          type="button"
          onClick={() => setLocale(loc)}
          className={cn(
            'px-1.5 py-1 rounded-full text-[10px] font-semibold transition-colors min-w-[1.75rem]',
            locale === loc
              ? 'bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900'
              : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200',
          )}
        >
          {LOCALE_SHORT[loc]}
        </button>
      ))}
    </div>
  )
}

const LOCALE_LABELS_DISPLAY: Record<Locale, string> = {
  'zh-CN': '简体中文',
  'en-US': 'English',
  'ja-JP': '日本語',
  'ko-KR': '한국어',
}
