// ============================================================
// MobileBottomNav — 手机版底部主导航
// ============================================================

import { Link, useLocation } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { useAppStore } from '@/store'
import { useT } from '@/hooks/useT'
import {
  BarChart3,
  ClipboardList,
  Home,
  Play,
  Settings,
  SlidersHorizontal,
  Wallet,
  Tag,
  Cog,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import type { MessageKey } from '@/lib/i18n'

type TabDef = {
  path: string
  labelKey: MessageKey
  icon: LucideIcon
  primary?: boolean
}

const projectTabs: TabDef[] = [
  { path: '/profile', labelKey: 'tab.profile', icon: ClipboardList },
  { path: '/scores', labelKey: 'tab.scores', icon: SlidersHorizontal },
  { path: '/config', labelKey: 'tab.config', icon: Cog },
  { path: '/run', labelKey: 'tab.run', icon: Play, primary: true },
  { path: '/dashboard', labelKey: 'tab.results', icon: BarChart3 },
]

const globalTabs: TabDef[] = [
  { path: '/', labelKey: 'tab.home', icon: Home },
  { path: '/pricing', labelKey: 'tab.pricing', icon: Tag },
  { path: '/recharge', labelKey: 'tab.recharge', icon: Wallet },
  { path: '/settings', labelKey: 'nav.settings', icon: Settings },
]

function isActive(pathname: string, tabPath: string): boolean {
  if (tabPath === '/') return pathname === '/'
  return pathname === tabPath
}

export function MobileBottomNav() {
  const { pathname } = useLocation()
  const currentProject = useAppStore((s) => s.currentProject)
  const tr = useT()
  const tabs = currentProject ? projectTabs : globalTabs

  return (
    <nav
      className="md:hidden fixed bottom-0 left-0 right-0 z-40 border-t border-gray-200 dark:border-gray-800 bg-white/95 dark:bg-gray-900/95 backdrop-blur-md pb-[env(safe-area-inset-bottom)]"
      aria-label="Main navigation"
    >
      <ul className="flex items-stretch h-14">
        {tabs.map((tab) => {
          const Icon = tab.icon
          const active = isActive(pathname, tab.path)
          const primary = tab.primary

          return (
            <li key={tab.path} className="flex-1 min-w-0">
              <Link
                to={tab.path}
                className={cn(
                  'flex flex-col items-center justify-center gap-0.5 h-full px-0.5 transition-colors',
                  active && !primary && 'text-gray-900 dark:text-gray-100',
                  !active && !primary && 'text-gray-500 dark:text-gray-400',
                  primary && active && 'text-gray-900 dark:text-gray-100',
                  primary && !active && 'text-gray-700 dark:text-gray-300',
                )}
              >
                <span
                  className={cn(
                    'flex items-center justify-center rounded-full transition-colors',
                    primary ? 'w-10 h-10 -mt-3 shadow-md' : 'w-6 h-6',
                    primary && active && 'bg-gray-900 dark:bg-gray-100',
                    primary && !active && 'bg-gray-100 dark:bg-gray-800',
                  )}
                >
                  <Icon
                    className={cn(
                      'w-5 h-5',
                      primary && active && 'text-white dark:text-gray-900',
                    )}
                  />
                </span>
                <span className={cn('text-[10px] font-medium truncate max-w-full px-0.5', primary && '-mt-0.5')}>
                  {tr(tab.labelKey)}
                </span>
              </Link>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}

export const MOBILE_BOTTOM_PAD = 'pb-[calc(3.5rem+env(safe-area-inset-bottom))] md:pb-0'
