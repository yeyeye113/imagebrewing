// ============================================================
// Auth API 预留 — 接口契约 + 本地 stub 回退
// ============================================================

import type { AccountSession } from '@/types/account'
import { apiRequest, ApiError } from './client'
import { useAccountStore } from '@/store/account'

export interface LoginRequest {
  email: string
  password: string
}

export interface LoginResponse {
  session: AccountSession
}

/** 服务端登录（会话写入本地）；无 API 时由 store.loginStub 处理 */
export async function apiLogin(req: LoginRequest): Promise<LoginResponse> {
  try {
    const res = await apiRequest<LoginResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(req),
    })
    useAccountStore.getState().setSession(res.session)
    return res
  } catch (e) {
    if (e instanceof ApiError && e.code === 'API_NOT_CONFIGURED') {
      useAccountStore.getState().loginStub(req.email)
      const session = useAccountStore.getState().session
      if (!session) throw new ApiError('Local stub login failed', 'STUB_LOGIN_FAILED')
      return { session }
    }
    throw e
  }
}

export async function apiLogout(): Promise<void> {
  try {
    await apiRequest('/auth/logout', { method: 'POST' })
  } catch (e) {
    if (!(e instanceof ApiError && e.code === 'API_NOT_CONFIGURED')) throw e
  } finally {
    // 无论走服务端还是 stub，本地会话一律清除
    useAccountStore.getState().logout()
  }
}

export async function apiGetSession(): Promise<AccountSession | null> {
  try {
    const res = await apiRequest<{ session: AccountSession | null }>('/auth/session')
    // 服务端滚动续期：同步最新 token/用户态到本地
    if (res.session) useAccountStore.getState().setSession(res.session)
    return res.session
  } catch (e) {
    if (e instanceof ApiError && e.code === 'API_NOT_CONFIGURED') {
      return useAccountStore.getState().session
    }
    throw e
  }
}
