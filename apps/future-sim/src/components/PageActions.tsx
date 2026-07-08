// ============================================================
// PageActions — 移动端底部固定操作栏
// ============================================================

import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

export function PageActions({ children, className }: { children: ReactNode; className?: string }) {
  return (
  <>
    <div className="h-28 md:hidden" aria-hidden />
    <div
      className={cn(
        'fixed md:static z-30',
        'bottom-[calc(3.5rem+env(safe-area-inset-bottom,0px))] md:bottom-auto',
        'left-0 right-0 md:left-auto md:right-auto',
        'px-4 py-3 md:px-0 md:py-0 md:mt-6',
        'bg-white/95 dark:bg-gray-950/95 backdrop-blur-md',
        'border-t border-gray-200 dark:border-gray-800 md:border-0',
        'flex gap-2 justify-end',
        className,
      )}
    >
      {children}
    </div>
  </>
  )
}

/** 页面主容器：为移动端底栏留出空间 */
export function PageShell({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn('max-w-3xl mx-auto px-4 sm:px-6 py-6 sm:py-8', className)}>
      {children}
    </div>
  )
}

export function PageShellWide({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn('max-w-6xl mx-auto px-4 sm:px-6 py-6 sm:py-8', className)}>
      {children}
    </div>
  )
}
