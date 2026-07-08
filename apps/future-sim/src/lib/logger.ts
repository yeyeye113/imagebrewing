// ============================================================
// Logger — 前端日志系统
// 支持日志存储、过滤、导出，与 Worker 日志集成
// ============================================================

export type LogLevel = 'debug' | 'info' | 'warn' | 'error'
export type LogModule = 'simulation' | 'engine' | 'worker' | 'ui' | 'api' | 'auth'

export interface LogEntry {
  id: string
  timestamp: number
  level: LogLevel
  module: LogModule
  message: string
  metadata?: Record<string, unknown>
  sessionId?: string
  projectId?: string
}

interface LoggerState {
  entries: LogEntry[]
  maxEntries: number
  sessionId: string | null
  projectId: string | null
  filters: {
    level: LogLevel[]
    modules: LogModule[]
    search: string
  }
}

const MAX_ENTRIES = 1000

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

function createLoggerState(): LoggerState {
  return {
    entries: [],
    maxEntries: MAX_ENTRIES,
    sessionId: null,
    projectId: null,
    filters: {
      level: ['debug', 'info', 'warn', 'error'],
      modules: ['simulation', 'engine', 'worker', 'ui', 'api', 'auth'],
      search: '',
    },
  }
}

// 内存存储（生产环境可用 IndexedDB 持久化）
let state = createLoggerState()

// 观察者模式：日志变更通知
type Listener = (entries: LogEntry[]) => void
const listeners = new Set<Listener>()

export const logger = {
  // ---- 上下文设置 ----
  setSession(sessionId?: string) {
    state.sessionId = sessionId ?? generateId()
  },

  setProject(projectId: string) {
    state.projectId = projectId
  },

  clearContext() {
    state.sessionId = null
    state.projectId = null
  },

  // ---- 日志记录 ----
  debug(module: LogModule, message: string, meta?: Record<string, unknown>) {
    this.log('debug', module, message, meta)
  },

  info(module: LogModule, message: string, meta?: Record<string, unknown>) {
    this.log('info', module, message, meta)
  },

  warn(module: LogModule, message: string, meta?: Record<string, unknown>) {
    this.log('warn', module, message, meta)
  },

  error(module: LogModule, message: string, meta?: Record<string, unknown>) {
    this.log('error', module, message, meta)
  },

  log(level: LogLevel, module: LogModule, message: string, meta?: Record<string, unknown>) {
    const entry: LogEntry = {
      id: generateId(),
      timestamp: Date.now(),
      level,
      module,
      message,
      metadata: meta,
      sessionId: state.sessionId ?? undefined,
      projectId: state.projectId ?? undefined,
    }

    // 添加到内存
    state.entries.push(entry)

    // 超过上限时移除旧条目
    if (state.entries.length > state.maxEntries) {
      state.entries = state.entries.slice(-state.maxEntries)
    }

    // 通知观察者
    listeners.forEach((fn) => fn(state.entries))

    // 开发环境输出到控制台
    if (import.meta.env.DEV) {
      const prefix = `[${level.toUpperCase()}] [${module}]`
      const style =
        level === 'error'
          ? 'color: #ef4444; font-weight: bold'
          : level === 'warn'
            ? 'color: #f59e0b; font-weight: bold'
            : level === 'info'
              ? 'color: #3b82f6'
              : 'color: #6b7280'
      console.log(`%c${prefix}`, style, message, meta ?? '')
    }
  },

  // ---- 查询 ----
  getEntries(): LogEntry[] {
    return state.entries
  },

  getFilteredEntries(): LogEntry[] {
    return state.entries.filter((entry) => {
      if (!state.filters.level.includes(entry.level)) return false
      if (!state.filters.modules.includes(entry.module)) return false
      if (state.filters.search) {
        const search = state.filters.search.toLowerCase()
        return (
          entry.message.toLowerCase().includes(search) ||
          entry.module.toLowerCase().includes(search)
        )
      }
      return true
    })
  },

  getEntriesByLevel(level: LogLevel): LogEntry[] {
    return state.entries.filter((e) => e.level === level)
  },

  getEntriesByModule(module: LogModule): LogEntry[] {
    return state.entries.filter((e) => e.module === module)
  },

  // ---- 过滤 ----
  setFilters(filters: Partial<LoggerState['filters']>) {
    if (filters.level) state.filters.level = filters.level
    if (filters.modules) state.filters.modules = filters.modules
    if (filters.search !== undefined) state.filters.search = filters.search
    listeners.forEach((fn) => fn(state.entries))
  },

  clearFilters() {
    state.filters = {
      level: ['debug', 'info', 'warn', 'error'],
      modules: ['simulation', 'engine', 'worker', 'ui', 'api', 'auth'],
      search: '',
    }
    listeners.forEach((fn) => fn(state.entries))
  },

  // ---- 订阅 ----
  subscribe(listener: Listener): () => void {
    listeners.add(listener)
    return () => listeners.delete(listener)
  },

  // ---- 清理 ----
  clear() {
    state.entries = []
    listeners.forEach((fn) => fn(state.entries))
  },

  // ---- 导出 ----
  exportAsJSON(): string {
    return JSON.stringify(state.entries, null, 2)
  },

  exportAsCSV(): string {
    const headers = ['timestamp', 'level', 'module', 'message', 'sessionId', 'projectId']
    const rows = state.entries.map((e) =>
      [
        new Date(e.timestamp).toISOString(),
        e.level,
        e.module,
        `"${e.message.replace(/"/g, '""')}"`,
        e.sessionId ?? '',
        e.projectId ?? '',
      ].join(','),
    )
    return [headers.join(','), ...rows].join('\n')
  },

  // ---- 统计 ----
  getStats(): { total: number; byLevel: Record<LogLevel, number>; byModule: Record<LogModule, number> } {
    const byLevel: Record<LogLevel, number> = { debug: 0, info: 0, warn: 0, error: 0 }
    const byModule: Record<LogModule, number> = { simulation: 0, engine: 0, worker: 0, ui: 0, api: 0, auth: 0 }

    state.entries.forEach((e) => {
      byLevel[e.level]++
      byModule[e.module]++
    })

    return {
      total: state.entries.length,
      byLevel,
      byModule,
    }
  },
}

export type { LoggerState }
