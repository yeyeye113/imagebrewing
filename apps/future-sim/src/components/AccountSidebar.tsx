// ============================================================
// AccountSidebar — 侧栏账户区
// ============================================================

import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useAccountStore } from '@/store/account'
import { apiLogout } from '@/lib/api/auth'
import { useLabels } from '@/hooks/useLabels'
import { useT } from '@/hooks/useT'
import { cn } from '@/lib/utils'
import { LogIn, LogOut, Wallet } from 'lucide-react'

export function AccountSidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { session, hydrated, hydrate, logout } = useAccountStore()
  const labels = useLabels()
  const tr = useT()

  useEffect(() => {
    hydrate()
  }, [hydrate])

  if (!hydrated) {
    return <div className="h-10 animate-pulse rounded-md bg-gray-100 dark:bg-gray-800" />
  }

  if (!session) {
    return (
      <div className="space-y-1">
        <Link
          to="/login"
          onClick={onNavigate}
          className={cn(
            'flex items-center gap-2 px-3 py-2 text-sm rounded-md',
            'text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800/60',
          )}
        >
          <LogIn className="w-4 h-4" />
          {tr('account.login')}
        </Link>
        <Link
          to="/recharge"
          onClick={onNavigate}
          className={cn(
            'flex items-center gap-2 px-3 py-2 text-sm rounded-md',
            'text-gray-500 dark:text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800/60',
          )}
        >
          <Wallet className="w-4 h-4" />
          {tr('account.rechargeStub')}
        </Link>
      </div>
    )
  }

  const { user } = session

  return (
    <div className="space-y-2">
      <div className="px-3 py-2 rounded-md bg-gray-50 dark:bg-gray-800/50">
        <p className="text-xs text-gray-500 dark:text-gray-400 truncate" title={user.email}>
          {user.displayName}
        </p>
        <p className="text-[11px] text-gray-400 dark:text-gray-500 truncate">{user.email}</p>
        <div className="flex items-center justify-between mt-1.5 text-xs">
          <span className="text-gray-600 dark:text-gray-300 tabular-nums">
            {user.credits} {tr('common.credits')}
          </span>
          <span className="text-gray-500 dark:text-gray-400">{labels.plan[user.plan]}</span>
        </div>
      </div>
      <Link
        to="/recharge"
        onClick={onNavigate}
        className="flex items-center gap-2 px-3 py-1.5 text-sm rounded-md text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800/60"
      >
        <Wallet className="w-4 h-4" />
        {tr('account.recharge')}
      </Link>
      <button
        type="button"
        onClick={() => {
          // 服务端可用时同步登出（失败不阻塞本地清理）
          void apiLogout().catch(() => logout())
          onNavigate?.()
        }}
        className="flex items-center gap-2 w-full px-3 py-1.5 text-sm rounded-md text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800/60 text-left"
      >
        <LogOut className="w-4 h-4" />
        {tr('account.logout')}
      </button>
    </div>
  )
}
