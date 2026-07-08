// LogPage - Full-screen log viewer
import { useState, useEffect, useRef } from "react"
import { Card, CardContent, Button } from "@/components/ui"
import { PageShell } from "@/components/PageActions"
import { logger, type LogEntry, type LogLevel, type LogModule } from "@/lib/logger"
import { cn } from "@/lib/utils"
import { Terminal, Search, Download, Trash2, RefreshCw, AlertCircle, Info, AlertTriangle, Bug, ChevronDown } from "lucide-react"

const LEVEL_CONFIG: Record<LogLevel, { icon: typeof Info; color: string; bgColor: string }> = {
  debug: { icon: Bug, color: "text-gray-400", bgColor: "bg-gray-100 dark:bg-gray-800" },
  info: { icon: Info, color: "text-blue-500", bgColor: "bg-blue-50 dark:bg-blue-950" },
  warn: { icon: AlertTriangle, color: "text-amber-500", bgColor: "bg-amber-50 dark:bg-amber-950" },
  error: { icon: AlertCircle, color: "text-red-500", bgColor: "bg-red-50 dark:bg-red-950" },
}
const MODULES: LogModule[] = ["simulation", "engine", "worker", "ui", "api", "auth"]

export default function LogPage() {
  const [entries, setEntries] = useState<LogEntry[]>([])
  const [search, setSearch] = useState("")
  const [levelFilters, setLevelFilters] = useState<LogLevel[]>(["debug", "info", "warn", "error"])
  const [moduleFilters, setModuleFilters] = useState<LogModule[]>(MODULES)
  const [showFilters, setShowFilters] = useState(true)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    const unsubscribe = logger.subscribe((newEntries) => setEntries([...newEntries]))
    setEntries(logger.getEntries())
    return unsubscribe
  }, [refreshKey])

  const filteredEntries = entries.filter((entry) => {
    if (!levelFilters.includes(entry.level)) return false
    if (!moduleFilters.includes(entry.module as LogModule)) return false
    if (search) {
      const s = search.toLowerCase()
      return entry.message.toLowerCase().includes(s) || entry.module.toLowerCase().includes(s)
    }
    return true
  })

  const toggleLevel = (level: LogLevel) => setLevelFilters(prev => prev.includes(level) ? prev.filter(l => l !== level) : [...prev, level])
  const toggleModule = (module: LogModule) => setModuleFilters(prev => prev.includes(module) ? prev.filter(m => m !== module) : [...prev, module])
  const handleClear = () => { logger.clear(); setEntries([]) }
  const handleExportJSON = () => {
    const blob = new Blob([logger.exportAsJSON()], { type: "application/json" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = "logs-" + new Date().toISOString().slice(0, 10) + ".json"
    a.click()
    URL.revokeObjectURL(url)
  }
  const stats = logger.getStats()
  const formatTime = (ts: number) => new Date(ts).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit", fractionalSecondDigits: 3 })

  return (
    <PageShell>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <Terminal className="w-6 h-6" /> 日志 <span className="text-sm font-normal text-gray-500">({filteredEntries.length}/{entries.length})</span>
        </h1>
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={() => setRefreshKey(k => k + 1)}><RefreshCw className="w-4 h-4 mr-1"/>刷新</Button>
          <Button variant="secondary" size="sm" onClick={handleExportJSON}><Download className="w-4 h-4 mr-1"/>JSON</Button>
          <Button variant="secondary" size="sm" onClick={handleClear}><Trash2 className="w-4 h-4 mr-1"/>清空</Button>
        </div>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        <Card className="p-3"><div className="text-2xl font-bold">{stats.total}</div><div className="text-xs text-gray-500">总日志</div></Card>
        <Card className="p-3"><div className="text-2xl font-bold text-blue-500">{stats.byLevel.info}</div><div className="text-xs text-gray-500">Info</div></Card>
        <Card className="p-3"><div className="text-2xl font-bold text-amber-500">{stats.byLevel.warn}</div><div className="text-xs text-gray-500">Warning</div></Card>
        <Card className="p-3"><div className="text-2xl font-bold text-red-500">{stats.byLevel.error}</div><div className="text-xs text-gray-500">Error</div></Card>
      </div>
      <Card className="mb-4">
        <CardContent className="p-4 space-y-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input type="text" value={search} onChange={e => setSearch(e.target.value)} placeholder="搜索..." className={cn("w-full pl-9 pr-3 py-2 text-sm rounded-lg", "bg-gray-100 dark:bg-gray-800 border-none")} />
          </div>
          <div className="flex flex-wrap gap-2">
            {(Object.keys(LEVEL_CONFIG) as LogLevel[]).map(level => (
              <button key={level} onClick={() => toggleLevel(level)} className={cn("px-3 py-1 text-sm rounded-full", levelFilters.includes(level) ? LEVEL_CONFIG[level].bgColor : "bg-gray-100 dark:bg-gray-800 text-gray-500")}>{level} ({stats.byLevel[level]})</button>
            ))}
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-0 max-h-[60vh] overflow-y-auto">
          {filteredEntries.length === 0 ? <div className="text-center text-gray-400 py-12">暂无日志</div> : (
            <div className="divide-y divide-gray-100 dark:divide-gray-800">
              {filteredEntries.slice().reverse().map(entry => {
                const config = LEVEL_CONFIG[entry.level]
                const Icon = config.icon
                const isExpanded = expandedId === entry.id
                return (
                  <div key={entry.id} className={cn("p-3 hover:bg-gray-50 dark:hover:bg-gray-800/50 cursor-pointer", isExpanded ? "bg-gray-50 dark:bg-gray-800/30" : "")} onClick={() => setExpandedId(isExpanded ? null : entry.id)}>
                    <div className="flex items-start gap-3">
                      <Icon className={cn("w-4 h-4 mt-0.5 shrink-0", config.color)} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 text-xs text-gray-500 mb-1">
                          <span>{formatTime(entry.timestamp)}</span>
                          <span className={cn("px-1.5 py-0.5 rounded", config.bgColor)}>{entry.module}</span>
                        </div>
                        <div className="text-sm break-all">{entry.message}</div>
                        {isExpanded && entry.metadata && <pre className="mt-2 p-2 bg-gray-100 dark:bg-gray-800 rounded text-xs overflow-x-auto">{JSON.stringify(entry.metadata, null, 2)}</pre>}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </PageShell>
  )
}
