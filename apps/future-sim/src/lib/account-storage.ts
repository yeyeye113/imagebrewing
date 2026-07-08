// ============================================================
// account-storage — 本地会话持久化（预留，后续换 API）
// ============================================================

import type { AccountSession } from '@/types/account'

const SESSION_KEY = 'fs_account_session_v1'

export function loadSession(): AccountSession | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY)
    if (!raw) return null
    const session = JSON.parse(raw) as AccountSession
    if (!session?.token || !session?.user?.id) return null
    if (new Date(session.expiresAt).getTime() < Date.now()) {
      localStorage.removeItem(SESSION_KEY)
      return null
    }
    return session
  } catch {
    return null
  }
}

export function saveSession(session: AccountSession): void {
  localStorage.setItem(SESSION_KEY, JSON.stringify(session))
}

export function clearSession(): void {
  localStorage.removeItem(SESSION_KEY)
}
