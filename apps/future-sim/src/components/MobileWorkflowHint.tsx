// ============================================================
// MobileWorkflowHint — 手机端当前步骤提示
// ============================================================

import { Link, useLocation } from 'react-router-dom'
import { useT } from '@/hooks/useT'

const STEPS = [
  { path: '/profile', labelKey: 'tab.profile' as const },
  { path: '/scores', labelKey: 'tab.scores' as const },
  { path: '/config', labelKey: 'tab.config' as const },
  { path: '/run', labelKey: 'tab.run' as const },
  { path: '/dashboard', labelKey: 'tab.results' as const },
] as const

function stepIndex(pathname: string): number {
  if (pathname === '/report') return 4
  return STEPS.findIndex((s) => s.path === pathname)
}

export function MobileWorkflowHint() {
  const { pathname } = useLocation()
  const tr = useT()
  const current = stepIndex(pathname)
  if (current < 0) return null

  const step = STEPS[current]
  const next = STEPS[current + 1]

  return (
    <div className="md:hidden flex items-center justify-between gap-2 px-4 py-2 text-xs border-b border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900">
      <span className="text-gray-500 dark:text-gray-400">
        {tr('workflow.step')}{' '}
        <strong className="text-gray-800 dark:text-gray-200">{current + 1}</strong>/{STEPS.length}
        <span className="mx-1.5">·</span>
        {tr(step.labelKey)}
      </span>
      {next && (
        <Link to={next.path} className="text-gray-900 dark:text-gray-100 font-medium shrink-0">
          {tr('workflow.next')} →
        </Link>
      )}
    </div>
  )
}
