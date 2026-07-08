// ============================================================
// Layout — 侧栏 + 移动端抽屉 + 主题 / 引导
// ============================================================

import { type ReactNode, useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { useAppStore } from '@/store'
import { WorkflowStepper } from './WorkflowStepper'
import { OnboardingGuide } from './OnboardingGuide'
import { ThemeToggle } from './ThemeToggle'
import { ToastHost } from './Toast'
import { AccountSidebar } from './AccountSidebar'
import { MobileBottomNav, MOBILE_BOTTOM_PAD } from './MobileBottomNav'
import { MobileWorkflowHint } from './MobileWorkflowHint'
import { LanguageToggle } from './LanguageToggle'
import { AmbientBackground, GlobalGlowTrail } from './fx'
import { useT } from '@/hooks/useT'
import { useLocaleStore } from '@/store/locale'
import { Menu, X } from 'lucide-react'

const navItemDefs = [
  { path: '/', labelKey: 'nav.projects' as const },
  { path: '/compare', labelKey: 'nav.compare' as const },
  { path: '/pricing', labelKey: 'nav.pricing' as const },
  { path: '/settings', labelKey: 'nav.settings' as const },
]

const projectLinkDefs = [
  { path: '/profile', labelKey: 'tab.profile' as const },
  { path: '/scores', labelKey: 'tab.scores' as const },
  { path: '/config', labelKey: 'tab.config' as const },
  { path: '/run', labelKey: 'tab.run' as const },
  { path: '/dashboard', labelKey: 'tab.results' as const },
  { path: '/report', labelKey: 'tab.report' as const },
]

const workflowPaths = new Set(['/profile', '/scores', '/config', '/run', '/dashboard', '/report'])

function NavLink({
  to,
  label,
  active,
  onNavigate,
}: {
  to: string
  label: string
  active: boolean
  onNavigate?: () => void
}) {
  return (
    <Link
      to={to}
      onClick={onNavigate}
      className={cn(
        'relative block px-3 py-2 text-sm rounded-md transition-colors',
        active
          ? 'bg-gray-100/90 dark:bg-gray-800/80 text-gray-900 dark:text-gray-100 font-medium'
          : 'text-gray-600 dark:text-gray-400 hover:bg-gray-50/80 dark:hover:bg-gray-800/60 hover:text-gray-900 dark:hover:text-gray-100',
      )}
    >
      {/* 当前项左侧竖起一道电光刻度，呼应 HUD 语言 */}
      {active && (
        <span
          aria-hidden
          className="absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-gradient-to-b from-cyan-400 to-violet-500 shadow-[0_0_8px_rgb(34_211_238/0.7)]"
        />
      )}
      {label}
    </Link>
  )
}

export function Layout({ children }: { children: ReactNode }) {
  const location = useLocation()
  const currentProject = useAppStore((s) => s.currentProject)
  const showWorkflow = currentProject && workflowPaths.has(location.pathname)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const tr = useT()
  const hydrateLocale = useLocaleStore((s) => s.hydrate)

  useEffect(() => {
    hydrateLocale()
  }, [hydrateLocale])

  useEffect(() => {
    setSidebarOpen(false)
  }, [location.pathname])

  useEffect(() => {
    if (!sidebarOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSidebarOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [sidebarOpen])

  const closeSidebar = () => setSidebarOpen(false)

  const sidebarContent = (
    <>
      <div className="px-4 py-5 border-b border-gray-100 dark:border-gray-800 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <Link
            to="/"
            onClick={closeSidebar}
            className="group/logo flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-gray-100"
          >
            {/* 品牌辉光徽标：呼吸光点嵌于电光渐变方块 */}
            <span className="relative flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-gradient-to-br from-cyan-500 via-violet-500 to-fuchsia-500 shadow-[0_0_14px_-2px_rgb(34_211_238/0.55)] transition-shadow group-hover/logo:shadow-[0_0_20px_-2px_rgb(139_92_246/0.7)]">
              <span className="h-1.5 w-1.5 rounded-full bg-white/95" />
            </span>
            <span className="fx-text-gradient truncate">Future Simulation Engine</span>
          </Link>
          <div className="text-[11px] text-gray-400 dark:text-gray-500 mt-1">{tr('app.tagline')}</div>
        </div>
        <button
          type="button"
          className="md:hidden p-1 rounded-md text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
          onClick={closeSidebar}
          aria-label={tr('layout.closeMenu')}
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      <nav className="flex-1 px-2 py-3 space-y-0.5 overflow-y-auto">
        {navItemDefs.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            label={tr(item.labelKey)}
            active={location.pathname === item.path}
            onNavigate={closeSidebar}
          />
        ))}

        {currentProject && (
          <div className="mt-4 pt-3 border-t border-gray-100 dark:border-gray-800 space-y-0.5">
            <div
              className="px-3 py-1 text-[11px] font-medium text-gray-400 dark:text-gray-500 uppercase tracking-wider truncate"
              title={currentProject.name}
            >
              {tr('common.currentProject')} · {currentProject.name}
            </div>
            {projectLinkDefs.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                onClick={closeSidebar}
                className={cn(
                  'block px-3 py-1.5 text-sm rounded-md transition-colors',
                  location.pathname === item.path
                    ? 'bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100 font-medium'
                    : 'text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800/60 hover:text-gray-700 dark:hover:text-gray-200',
                )}
              >
                {tr(item.labelKey)}
              </Link>
            ))}
          </div>
        )}
      </nav>

      <div className="px-4 py-3 border-t border-gray-100 dark:border-gray-800 space-y-3">
        <AccountSidebar onNavigate={closeSidebar} />
        <div className="hidden md:block">
          <LanguageToggle className="w-full justify-center" />
        </div>
        <ThemeToggle />
        <p className="text-[11px] text-gray-400 dark:text-gray-500">{tr('settings.disclaimer')}</p>
      </div>
    </>
  )

  return (
    <div className="relative isolate min-h-screen bg-gray-50 dark:bg-gray-950 flex flex-col md:flex-row">
      {/* 全局氛围层：全息网格 + 极光气团 + 粒子星域（fixed / -z-10，不挡任何交互） */}
      <AmbientBackground />

      {/* 全局鼠标追踪流光 */}
      <GlobalGlowTrail />

      {/* 移动端顶栏 */}
      <header className="md:hidden sticky top-0 z-30 flex items-center justify-between gap-3 px-4 py-3 bg-white/85 dark:bg-gray-900/80 backdrop-blur-md border-b border-gray-200 dark:border-gray-800">
        <button
          type="button"
          onClick={() => setSidebarOpen(true)}
          className="p-2 -ml-2 rounded-md text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800"
          aria-label={tr('layout.openMenu')}
        >
          <Menu className="w-5 h-5" />
        </button>
        <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate flex-1 text-center px-1">
          {currentProject?.name ?? tr('app.name')}
        </span>
        <div className="flex items-center gap-1 shrink-0">
          <LanguageToggle />
          <ThemeToggle compact />
        </div>
      </header>

      {/* 移动端遮罩 */}
      {sidebarOpen && (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-black/40 md:hidden"
          onClick={closeSidebar}
          aria-label={tr('layout.closeOverlay')}
        />
      )}

      {/* 侧栏：桌面常驻 / 移动抽屉 */}
      <aside
        className={cn(
          'fixed md:static inset-y-0 left-0 z-50 w-64 md:w-56',
          // 玻璃侧栏：让氛围层的极光隐约透出，界面纵深感 +1
          'bg-white/85 dark:bg-gray-900/70 backdrop-blur-xl',
          'border-r border-gray-200/90 dark:border-gray-800/90',
          'flex flex-col shrink-0 transition-transform duration-200 ease-out',
          'md:translate-x-0',
          sidebarOpen ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        {sidebarContent}
      </aside>

      <main className="flex-1 flex flex-col min-w-0 md:max-h-screen md:overflow-hidden">
        {/* 流程条：桌面显示；手机用底部 Tab，避免双导航占屏 */}
        {showWorkflow && (
          <div className="hidden md:block">
            <WorkflowStepper />
          </div>
        )}
        {showWorkflow && <MobileWorkflowHint />}
        {showWorkflow && <OnboardingGuide />}
        <div className={cn('flex-1 overflow-auto', MOBILE_BOTTOM_PAD)}>{children}</div>
        <MobileBottomNav />
        <ToastHost />
      </main>
    </div>
  )
}
