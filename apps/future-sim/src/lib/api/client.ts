// ============================================================
// API 客户端 — 配置 VITE_API_BASE_URL 即切换真实后端，否则本地 stub
// ============================================================

import { useAccountStore } from '@/store/account'

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

export class ApiError extends Error {
  constructor(
    message: string,
    readonly code: string,
    readonly status?: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

/** 统一请求封装：自动注入 Bearer token；未配置 baseUrl 时抛出并由调用方回退 stub */
export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  if (!API_BASE_URL) {
    throw new ApiError('API 未配置，请使用本地 stub', 'API_NOT_CONFIGURED')
  }
  const token = useAccountStore.getState().session?.token
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token && !token.startsWith('stub_') ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new ApiError(body || res.statusText, 'HTTP_ERROR', res.status)
  }
  return res.json() as Promise<T>
}

export function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` }
}
