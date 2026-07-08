// ============================================================
// ThemeToggle — 浅色 / 深色 / 跟随系统
// ============================================================

import { useEffect, useState } from 'react'
import { Moon, Sun, Monitor } from 'lucide-react'
import { cn } from '@/lib/utils'
import { getStoredTheme, setTheme, type ThemeMode } from '@/lib/theme'
import { useT } from '@/hooks/useT'

export function ThemeToggle({ compact }: { compact?: boolean }) {
  const [mode, setMode] = useState<ThemeMode>(() => getStoredTheme())
  const tr = useT()

  const modes: { key: ThemeMode; icon: typeof Sun; labelKey: 'theme.light' | 'theme.dark' | 'theme.system' }[] = [
    { key: 'light', icon: Sun, labelKey: 'theme.light' },
    { key: 'dark', icon: Moon, labelKey: 'theme.dark' },
    { key: 'system', icon: Monitor, labelKey: 'theme.system' },
  ]

  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => {
      if (getStoredTheme() === 'system') setTheme('system')
    }
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  const pick = (m: ThemeMode) => {
    setMode(m)
    setTheme(m)
  }

  if (compact) {
    const next: ThemeMode = mode === 'light' ? 'dark' : mode === 'dark' ? 'system' : 'light'
    const Icon = mode === 'dark' ? Moon : mode === 'light' ? Sun : Monitor
    const label = tr(modes.find((x) => x.key === mode)!.labelKey)
    return (
      <button
        type="button"
        onClick={() => pick(next)}
        className="p-2 rounded-md text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
        title={label}
        aria-label={tr('theme.toggle')}
      >
        <Icon className="w-4 h-4" />
      </button>
    )
  }

  return (
    <div className="flex rounded-lg border border-gray-200 dark:border-gray-700 p-0.5 bg-gray-50 dark:bg-gray-800/50">
      {modes.map(({ key, icon: Icon, labelKey }) => (
        <button
          key={key}
          type="button"
          onClick={() => pick(key)}
          className={cn(
            'flex items-center gap-1 px-2 py-1 rounded-md text-xs transition-colors',
            mode === key
              ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm'
              : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200',
          )}
          title={tr(labelKey)}
        >
          <Icon className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">{tr(labelKey)}</span>
        </button>
      ))}
    </div>
  )
}
