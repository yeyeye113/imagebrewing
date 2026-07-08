// ============================================================
// Toast — 轻量操作反馈
// ============================================================

import { create } from 'zustand'
import { useEffect } from 'react'
import { CheckCircle } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ToastState {
  message: string | null
  show: (message: string) => void
  hide: () => void
}

let hideTimer: ReturnType<typeof setTimeout> | null = null

export const useToastStore = create<ToastState>((set) => ({
  message: null,
  show: (message) => {
    if (hideTimer) clearTimeout(hideTimer)
    set({ message })
    hideTimer = setTimeout(() => set({ message: null }), 2600)
  },
  hide: () => {
    if (hideTimer) clearTimeout(hideTimer)
    set({ message: null })
  },
}))

export function toast(message: string) {
  useToastStore.getState().show(message)
}

export function ToastHost() {
  const message = useToastStore((s) => s.message)
  const hide = useToastStore((s) => s.hide)

  useEffect(() => {
    if (!message) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') hide()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [message, hide])

  return (
    <div
      className={cn(
        'fixed left-1/2 -translate-x-1/2 z-[60] pointer-events-none transition-all duration-300',
        'bottom-[calc(5rem+env(safe-area-inset-bottom,0px))] md:bottom-6',
        message ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2',
      )}
      role="status"
      aria-live="polite"
    >
      {message && (
        <div className="pointer-events-auto flex items-center gap-2 px-4 py-2.5 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 text-sm font-medium">
          <CheckCircle className="w-4 h-4 shrink-0" />
          {message}
        </div>
      )}
    </div>
  )
}
