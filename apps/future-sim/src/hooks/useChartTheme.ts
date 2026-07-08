// ============================================================
// useChartTheme — Recharts 深色/浅色自适应
// ============================================================

import { useEffect, useState } from 'react'

export interface ChartTheme {
  isDark: boolean
  grid: string
  axis: string
  tick: string
  tooltipBg: string
  tooltipBorder: string
  linePrimary: string
  lineSecondary: string
}

function readDark(): boolean {
  return document.documentElement.classList.contains('dark')
}

export function useChartTheme(): ChartTheme {
  const [isDark, setIsDark] = useState(readDark)

  useEffect(() => {
    const obs = new MutationObserver(() => setIsDark(readDark()))
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
    return () => obs.disconnect()
  }, [])

  return {
    isDark,
    grid: isDark ? '#374151' : '#f3f4f6',
    axis: isDark ? '#6B7280' : '#9CA3AF',
    tick: isDark ? '#9CA3AF' : '#6B7280',
    tooltipBg: isDark ? '#111827' : '#ffffff',
    tooltipBorder: isDark ? '#374151' : '#e5e7eb',
    linePrimary: isDark ? '#F9FAFB' : '#111827',
    lineSecondary: isDark ? '#9CA3AF' : '#6B7280',
  }
}
