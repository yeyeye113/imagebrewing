// ============================================================
// OnboardingGuide — 新建项目后的分步引导条
// ============================================================

import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { X, Sparkles, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui'
import { getOnboardingForPath, shouldShowOnboarding, dismissOnboarding, completeOnboarding } from '@/lib/onboarding'
import { useAppStore } from '@/store'
import { useLocaleStore } from '@/store/locale'
import { useT } from '@/hooks/useT'

export function OnboardingGuide() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const result = useAppStore((s) => s.result)
  const locale = useLocaleStore((s) => s.locale)
  const tr = useT()
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    setVisible(shouldShowOnboarding())
  }, [pathname])

  useEffect(() => {
    if (result && pathname === '/dashboard') {
      completeOnboarding()
      setVisible(false)
    }
  }, [result, pathname])

  const step = getOnboardingForPath(pathname, locale)
  if (!visible || !step) return null

  return (
    <div className="border-b border-indigo-200 dark:border-indigo-900/50 bg-indigo-50 dark:bg-indigo-950/40 px-4 py-3">
      <div className="max-w-5xl mx-auto flex flex-col sm:flex-row sm:items-start gap-3">
        <div className="flex items-start gap-3 flex-1 min-w-0">
          <div className="shrink-0 p-2 rounded-lg bg-indigo-100 dark:bg-indigo-900/50 text-indigo-600 dark:text-indigo-300">
            <Sparkles className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs font-medium text-indigo-600 dark:text-indigo-400">
                {tr('onboarding.badge')} {step.step}/{step.total}
              </span>
              <div className="flex gap-1">
                {Array.from({ length: step.total }, (_, i) => (
                  <span
                    key={i}
                    className={`h-1 w-4 rounded-full ${i < step.step ? 'bg-indigo-500' : 'bg-indigo-200 dark:bg-indigo-800'}`}
                  />
                ))}
              </div>
            </div>
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100 mt-1">{step.title}</p>
            <p className="text-xs text-gray-600 dark:text-gray-400 mt-0.5 leading-relaxed">{step.body}</p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0 sm:pt-1">
          {step.nextPath && step.nextLabel && (
            <Button size="sm" onClick={() => navigate(step.nextPath!)}>
              {step.nextLabel}
              <ChevronRight className="w-3.5 h-3.5 ml-1" />
            </Button>
          )}
          <button
            type="button"
            onClick={() => {
              dismissOnboarding()
              setVisible(false)
            }}
            className="p-1.5 rounded-md text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-white/60 dark:hover:bg-gray-800"
            aria-label={tr('onboarding.close')}
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
