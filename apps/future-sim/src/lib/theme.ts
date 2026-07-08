// ============================================================
// Theme — 深色/浅色偏好（localStorage + 系统默认）
// ============================================================

export type ThemeMode = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'fs-theme'

export function getStoredTheme(): ThemeMode {
  const v = localStorage.getItem(STORAGE_KEY)
  if (v === 'light' || v === 'dark' || v === 'system') return v
  return 'system'
}

export function resolveDark(mode: ThemeMode): boolean {
  if (mode === 'dark') return true
  if (mode === 'light') return false
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

export function applyTheme(mode: ThemeMode): void {
  const dark = resolveDark(mode)
  document.documentElement.classList.toggle('dark', dark)
}

export function setTheme(mode: ThemeMode): void {
  localStorage.setItem(STORAGE_KEY, mode)
  applyTheme(mode)
}

/** 首屏渲染前调用，避免主题闪烁 */
export function initTheme(): ThemeMode {
  const mode = getStoredTheme()
  applyTheme(mode)
  return mode
}
