// ============================================================
// useLocalizedResult — 结果对象的语言自适应视图
// ------------------------------------------------------------
// 报告叙事在模拟时按当时语言固化；用户切换界面语言后，本 hook 检测
// result.locale 与当前语言不一致时按新语言重建文本层（不重跑模拟），
// 使仪表盘 / 报告页的诊断叙事跟随界面语言。
// ============================================================

import { useMemo } from 'react'
import { useAppStore } from '@/store'
import { useLocale } from '@/hooks/useT'
import { localizeResult } from '@/lib/insight-locale'
import type { SimulationResult } from '@/types'

export function useLocalizedResult(): SimulationResult | null {
  const { result, scores, currentProject } = useAppStore()
  const locale = useLocale()

  return useMemo(() => {
    if (!result) return null
    const resultLocale = result.locale ?? 'zh-CN'
    if (resultLocale === locale) return result
    return localizeResult(result, scores, currentProject, locale)
  }, [result, scores, currentProject, locale])
}
