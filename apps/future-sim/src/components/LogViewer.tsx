// LogViewer
import { useState, useEffect, useRef } from "react"
import { logger, type LogEntry, type LogLevel } from "@/lib/logger"
import { cn } from "@/lib/utils"
import { X, Search, Download, Trash2, Filter, AlertCircle, Info, AlertTriangle, Bug, Terminal } from "lucide-react"

const LEVEL_CONFIG: Record<LogLevel, { icon: typeof Info; color: string; bgColor: string }> = {
  debug: { icon: Bug, color: "text-gray-400", bgColor: "bg-gray-100 dark:bg-gray-800" },
  info: { icon: Info, color: "text-blue-500", bgColor: "bg-blue-50 dark:bg-blue-950" },
  warn: { icon: AlertTriangle, color: "text-amber-500", bgColor: "bg-amber-50 dark:bg-amber-950" },
  error: { icon: AlertCircle, color: "text-red-500", bgColor: "bg-red-50 dark:bg-red-950" },
}

export function LogViewer() {
  const [isOpen, setIsOpen] = useState(false)
  const [entries, setEntries] = useState<LogEntry[]>([])
  const [search, setSearch] = useState("")
  const [levelFilters, setLevelFilters] = useState<LogLevel[]>(["debug", "info", "warn", "error"])
  const [showFilters, setShowFilters] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const unsubscribe = logger.subscribe((newEntries) => setEntries([...newEntries]))
    setEntries(logger.getEntries())
    return unsubscribe
  }, [])

  useEffect(() => {
    if (isOpen && bottomRef.current) bottomRef.current.scrollIntoView({ behavior: "smooth" })
  }, [entries, isOpen])

  const filteredEntries = entries.filter((entry) => {
    if (!levelFilters.includes(entry.level)) return false
    if (search) {
      const s = search.toLowerCase()
      return entry.message.toLowerCase().includes(s) || entry.module.toLowerCase().includes(s)
    }
    return true
  })

  const toggleLevel = (level: LogLevel) => {
    setLevelFilters(prev => prev.includes(level) ? prev.filter(l => l !== level) : [...prev, level])
  }

  const handleClear = () => logger.clear()
  const handleExport = () => {
    const blob = new Blob([logger.exportAsJSON()], { type: "application/json" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `logs-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const formatTime = (ts: number) => new Date(ts).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit", fractionalSecondDigits: 3 })
  const errorCount = entries.filter(e => e.level === "error").length

  return (
    <>
      <button onClick={() => setIsOpen(!isOpen)}
        className={cn("fixed bottom-20 right-4 z-40 p-3 rounded-full shadow-lg transition-all", "bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900", "hover:scale-105 active:scale-95")}
        title="日志面板">
        <Terminal className="w-5 h-5" />
        {errorCount > 0 && (
          <span className="absolute -top-1 -right-1 bg-red-500 text-white text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center">
            {errorCount > 99 ? "99+" : errorCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div className={cn("fixed bottom-28 right-4 z-40 w-96 max-h-[60vh] rounded-xl shadow-2xl", "bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700", "flex flex-col transition-all")}>
          <div className="flex items-center gap-2 p-3 border-b border-gray-200 dark:border-gray-700">
            <Terminal className="w-4 h-4 text-gray-500" />
            <span className="text-sm font-medium flex-1">日志 ({entries.length})</span>
            <button onClick={() => setShowFilters(!showFilters)} className={cn("p-1.5 rounded-md transition-colors", showFilters ? "bg-gray-200 dark:bg-gray-700" : "hover:bg-gray-100 dark:hover:bg-gray-800")}>
              <Filter className="w-4 h-4" />
            </button>
            <button onClick={handleExport} className="p-1.5 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800" title="导出"><Download className="w-4 h-4" /></button>
            <button onClick={handleClear} className="p-1.5 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800" title="清空"><Trash2 className="w-4 h-4" /></button>
            <button onClick={() => setIsOpen(false)} className="p-1.5 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800"><X className="w-4 h-4" /></button>
          </div>
          <div className="p-2 border-b border-gray-200 dark:border-gray-700">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input type="text" value={search} onChange={e => setSearch(e.target.value)} placeholder="搜索日志..."
                className={cn("w-full pl-8 pr-3 py-1.5 text-sm rounded-md", "bg-gray-100 dark:bg-gray-800 border-none", "placeholder:text-gray-400")} />
            </div>
          </div>
          {showFilters && (
            <div className="p-2 border-b border-gray-200 dark:border-gray-700">
              <div className="flex flex-wrap gap-1">
                {(Object.keys(LEVEL_CONFIG) as LogLevel[]).map(level => (
                  <button key={level} onClick={() => toggleLevel(level)}
                    className={cn("px-2 py-0.5 text-xs rounded-full transition-colors",
                      levelFilters.includes(level) ? LEVEL_CONFIG[level].bgColor : "bg-gray-100 dark:bg-gray-800 text-gray-500")}>
                    {level}
                  </button>
                ))}
              </div>
            </div>
          )}
          <div className="flex-1 overflow-y-auto p-2 space-y-1 font-mono text-xs">
            {filteredEntries.length === 0 ? (
              <div className="text-center text-gray-400 py-8">暂无日志</div>
            ) : filteredEntries.map(entry => {
              const config = LEVEL_CONFIG[entry.level]
              const Icon = config.icon
              return (
                <div key={entry.id} className={cn("p-1.5 rounded border-l-2 hover:bg-gray-50 dark:hover:bg-gray-800/50")}>
                  <div className="flex items-start gap-2">
                    <Icon className={cn("w-3.5 h-3.5 mt-0.5 shrink-0", config.color)} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 text-gray-500">
                        <span>{formatTime(entry.timestamp)}</span>
                        <span className={cn("px-1 rounded text-[10px]", config.bgColor)}>{entry.module}</span>
                      </div>
                      <div className="text-gray-700 dark:text-gray-300 break-all">{entry.message}</div>
                    </div>
                  </div>
                </div>
              )
            })}
            <div ref={bottomRef} />
          </div>
        </div>
      )}
    </>
  )
}



// LogPanel 是 LogViewer 的别名，保持与 App.tsx 导入兼容
export const LogPanel = LogViewer
