// ============================================================
// WorkflowStepper — 引导用户走完流程
// ============================================================

import { Link, useLocation } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { useT } from '@/hooks/useT'
import { Check } from 'lucide-react'

const STEPS = [
  { path: '/profile', labelKey: 'tab.profile' as const },
  { path: '/scores', labelKey: 'tab.scores' as const },
  { path: '/config', labelKey: 'tab.config' as const },
  { path: '/run', labelKey: 'tab.run' as const },
  { path: '/dashboard', labelKey: 'tab.results' as const },
] as const

function stepIndex(pathname: string): number {
  if (pathname === '/report') return 4
  const i = STEPS.findIndex((s) => s.path === pathname)
  return i >= 0 ? i : -1
}

export function WorkflowStepper() {
  const { pathname } = useLocation()
  const tr = useT()
  const current = stepIndex(pathname)
  if (current < 0) return null

  return (
    <nav
      className="bg-white/80 dark:bg-gray-900/70 backdrop-blur-md border-b border-gray-200/90 dark:border-gray-800/90 px-4 sm:px-6 py-3"
      aria-label={tr('workflow.aria')}
    >
      <ol className="max-w-5xl mx-auto flex items-center gap-1 sm:gap-2 overflow-x-auto">
        {STEPS.map((step, i) => {
          const done = i < current
          const active = i === current
          const reachable = i <= current || done

          return (
            <li key={step.path} className="flex items-center shrink-0">
              {i > 0 && (
                <span
                  className={cn('hidden sm:block w-6 h-px mx-1', done ? 'bg-gray-400' : 'bg-gray-200')}
                  aria-hidden
                />
              )}
              <Link
                to={step.path}
                className={cn(
                  'flex items-center gap-1.5 px-2 py-1 rounded-md text-xs transition-colors',
                  active &&
                    'bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 font-medium shadow-[0_0_16px_-4px_rgb(139_92_246/0.55)]',
                  !active && done && 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800',
                  !active && !done && reachable && 'text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800/60',
                  !active && !done && !reachable && 'text-gray-300 dark:text-gray-600 pointer-events-none',
                )}
                aria-current={active ? 'step' : undefined}
              >
                <span
                  className={cn(
                    'flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-semibold border',
                    active && 'border-white/30 dark:border-gray-900/20 bg-white/10 dark:bg-gray-900/10',
                    !active && done && 'border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-950/40 text-green-700 dark:text-green-400',
                    !active && !done && 'border-gray-200 dark:border-gray-700 text-gray-400',
                  )}
                >
                  {done ? <Check className="w-3 h-3" /> : i + 1}
                </span>
                <span className="whitespace-nowrap">{tr(step.labelKey)}</span>
              </Link>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
