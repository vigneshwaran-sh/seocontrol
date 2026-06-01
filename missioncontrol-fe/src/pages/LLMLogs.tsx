import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import {
  ScrollText,
  Clock,
  Search,
  X,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import api from '../lib/api'
import type { Agent, Space } from '../types'

interface LLMLog {
  id: string
  task_id: string
  agent_id: string
  space_id: string
  provider: string
  model: string
  request: Record<string, unknown>
  response: string
  duration_ms: number
  requested_at: string
  created_at: string
}

interface LogsResponse {
  logs: LLMLog[]
  total: number
  page: number
  limit: number
  pages: number
}

function formatTime(dateStr: string): string {
  const raw = dateStr.endsWith('Z') ? dateStr : dateStr + 'Z'
  const date = new Date(raw)
  const now = new Date()

  const istNowParts = new Intl.DateTimeFormat('en-IN', {
    timeZone: 'Asia/Kolkata',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(now)
  const nowDay = istNowParts.find((p) => p.type === 'day')?.value
  const nowMonth = istNowParts.find((p) => p.type === 'month')?.value
  const nowYear = istNowParts.find((p) => p.type === 'year')?.value

  const istDateParts = new Intl.DateTimeFormat('en-IN', {
    timeZone: 'Asia/Kolkata',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(date)
  const dateDay = istDateParts.find((p) => p.type === 'day')?.value
  const dateMonth = istDateParts.find((p) => p.type === 'month')?.value
  const dateYear = istDateParts.find((p) => p.type === 'year')?.value

  const timePart = new Intl.DateTimeFormat('en-IN', {
    timeZone: 'Asia/Kolkata',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  }).format(date)

  if (nowDay === dateDay && nowMonth === dateMonth && nowYear === dateYear) {
    return `Today ${timePart}`
  }

  const yesterday = new Date(now)
  yesterday.setDate(yesterday.getDate() - 1)
  const yParts = new Intl.DateTimeFormat('en-IN', {
    timeZone: 'Asia/Kolkata',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(yesterday)
  const yDay = yParts.find((p) => p.type === 'day')?.value
  const yMonth = yParts.find((p) => p.type === 'month')?.value
  const yYear = yParts.find((p) => p.type === 'year')?.value

  if (dateDay === yDay && dateMonth === yMonth && dateYear === yYear) {
    return `Yesterday ${timePart}`
  }

  return new Intl.DateTimeFormat('en-IN', {
    timeZone: 'Asia/Kolkata',
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  }).format(date)
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

const PROVIDER_COLORS: Record<string, string> = {
  openai: 'bg-green-50 text-green-700 border-green-200',
  gemini: 'bg-blue-50 text-blue-700 border-blue-200',
  claude: 'bg-orange-50 text-orange-700 border-orange-200',
}

// ---------------------------------------------------------------------------
// JSON syntax highlighter with collapse/expand
// ---------------------------------------------------------------------------

function JsonToken({ value }: { value: unknown }) {
  if (value === null) return <span className="text-red-400">null</span>
  if (typeof value === 'boolean')
    return <span className="text-purple-400">{String(value)}</span>
  if (typeof value === 'number')
    return <span className="text-blue-400">{value}</span>
  if (typeof value === 'string') {
    // Long strings get a read-more toggle
    const MAX = 300
    const display = value.length > MAX
      ? value
      : null
    if (display) return <JsonLongString value={value} max={MAX} />
    return <span className="text-green-400">"{value}"</span>
  }
  return <span className="text-warm-300">{String(value)}</span>
}

function JsonLongString({ value, max }: { value: string; max: number }) {
  const [expanded, setExpanded] = useState(false)
  if (expanded) {
    return (
      <span>
        <span className="text-green-400">"{value}"</span>
        <button
          onClick={() => setExpanded(false)}
          className="ml-1 text-[10px] text-warm-400 hover:text-warm-200 border border-warm-600 rounded px-1 leading-none"
        >
          collapse
        </button>
      </span>
    )
  }
  return (
    <span>
      <span className="text-green-400">"{value.slice(0, max)}<span className="text-warm-500">…</span>"</span>
      <button
        onClick={() => setExpanded(true)}
        className="ml-1 text-[10px] text-warm-400 hover:text-warm-200 border border-warm-600 rounded px-1 leading-none"
      >
        {value.length - max} more chars
      </button>
    </span>
  )
}

// Toggle button — the tiny − / + shown before { or [
function CollapseBtn({
  collapsed,
  onClick,
}: {
  collapsed: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={(e) => { e.stopPropagation(); onClick() }}
      className="inline-flex items-center justify-center w-4 h-4 mr-0.5 rounded text-[11px] font-bold leading-none text-warm-400 hover:text-warm-100 hover:bg-warm-700/60 transition-colors select-none align-middle"
      title={collapsed ? 'Expand' : 'Collapse'}
    >
      {collapsed ? '+' : '−'}
    </button>
  )
}

// Collapse-all / Expand-all button that resets the tree by remounting it
function JsonViewer({ value }: { value: unknown }) {
  const [treeKey, setTreeKey] = useState(0)
  const [allCollapsed, setAllCollapsed] = useState(false)

  const toggleAll = () => {
    setAllCollapsed((prev) => !prev)
    setTreeKey((k) => k + 1)
  }

  // We pass a wrapper that starts all nodes collapsed when allCollapsed=true
  // by using the key to remount; the root JsonNode will inherit depth=0 default
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <button
          onClick={toggleAll}
          className="text-[11px] text-warm-400 hover:text-warm-200 border border-warm-600 rounded px-2 py-0.5 transition-colors"
        >
          {allCollapsed ? 'Expand all' : 'Collapse all'}
        </button>
      </div>
      <pre className="text-xs font-mono leading-relaxed">
        <JsonNodeControlled key={treeKey} value={value} depth={0} startCollapsed={allCollapsed} />
      </pre>
    </div>
  )
}

// Variant of JsonNode that accepts an initial collapsed state (for collapse-all)
function JsonNodeControlled({
  value,
  depth = 0,
  startCollapsed = false,
}: {
  value: unknown
  depth?: number
  startCollapsed?: boolean
}) {
  const [collapsed, setCollapsed] = useState(() => startCollapsed && depth > 0)

  const indent = '  '.repeat(depth)
  const childIndent = '  '.repeat(depth + 1)

  if (value === null || typeof value !== 'object') {
    return <JsonToken value={value} />
  }

  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-warm-400">[]</span>

    if (collapsed) {
      return (
        <span>
          <CollapseBtn collapsed onClick={() => setCollapsed(false)} />
          <span className="text-warm-400">[ </span>
          <span className="text-warm-500 italic text-[11px]">{value.length} items</span>
          <span className="text-warm-400"> ]</span>
        </span>
      )
    }

    return (
      <span>
        <CollapseBtn collapsed={false} onClick={() => setCollapsed(true)} />
        <span className="text-warm-400">{'['}</span>
        {value.map((item, i) => (
          <div key={i} className="block">
            <span>{childIndent}</span>
            <JsonNodeControlled value={item} depth={depth + 1} startCollapsed={startCollapsed} />
            {i < value.length - 1 && <span className="text-warm-500">,</span>}
          </div>
        ))}
        <div>
          <span>{indent}</span>
          <span className="text-warm-400">{']'}</span>
        </div>
      </span>
    )
  }

  const entries = Object.entries(value as Record<string, unknown>)
  if (entries.length === 0) return <span className="text-warm-400">{'{}'}</span>

  if (collapsed) {
    return (
      <span>
        <CollapseBtn collapsed onClick={() => setCollapsed(false)} />
        <span className="text-warm-400">{'{ '}</span>
        <span className="text-warm-500 italic text-[11px]">{entries.length} keys</span>
        <span className="text-warm-400">{' }'}</span>
      </span>
    )
  }

  return (
    <span>
      <CollapseBtn collapsed={false} onClick={() => setCollapsed(true)} />
      <span className="text-warm-400">{'{'}</span>
      {entries.map(([k, v], i) => (
        <div key={k} className="block">
          <span>{childIndent}</span>
          <span className="text-yellow-400">"{k}"</span>
          <span className="text-warm-400">: </span>
          <JsonNodeControlled value={v} depth={depth + 1} startCollapsed={startCollapsed} />
          {i < entries.length - 1 && <span className="text-warm-500">,</span>}
        </div>
      ))}
      <div>
        <span>{indent}</span>
        <span className="text-warm-400">{'}'}</span>
      </div>
    </span>
  )
}

// ---------------------------------------------------------------------------
// Log detail modal
// ---------------------------------------------------------------------------

function LogModal({
  log,
  agent,
  onClose,
}: {
  log: LLMLog
  agent: Agent | undefined
  onClose: () => void
}) {
  const providerColor =
    PROVIDER_COLORS[log.provider] || 'bg-warm-50 text-warm-600 border-warm-200'

  // Try to parse response as JSON for pretty-printing; fall back to raw text
  let parsedResponse: unknown = null
  let responseIsJson = false
  try {
    parsedResponse = JSON.parse(log.response)
    responseIsJson = true
  } catch {
    // not JSON
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.55)' }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="bg-card border border-border rounded-2xl w-full max-w-7xl flex flex-col"
        style={{ height: 'calc(100vh - 64px)' }}
      >
        {/* Modal header */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-border flex-shrink-0">
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-medium border ${providerColor}`}
          >
            {log.provider}
          </span>
          {agent && (
            <span className="text-sm text-warm-600">
              {agent.avatar} {agent.name}
            </span>
          )}
          <span className="text-warm-300">|</span>
          <span className="text-xs text-warm-400 font-mono">{log.model}</span>
          <span className="text-warm-300">|</span>
          <span className="inline-flex items-center gap-1 text-xs text-warm-400">
            <Clock className="h-3.5 w-3.5" />
            {formatDuration(log.duration_ms)}
          </span>
          <span className="text-warm-300">|</span>
          <span className="text-xs text-warm-400">
            {formatTime(log.requested_at || log.created_at)}
          </span>
          <div className="flex-1" />
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-warm-400 hover:text-warm-700 hover:bg-warm-50 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Two-panel body */}
        <div className="flex flex-1 min-h-0 divide-x divide-border">
          {/* Left — Request */}
          <div className="flex-1 flex flex-col min-w-0">
            <div className="px-4 py-2.5 border-b border-border flex-shrink-0 bg-warm-50/40">
              <p className="text-[11px] font-semibold text-warm-500 uppercase tracking-wider">
                Request
              </p>
            </div>
            <div className="flex-1 overflow-auto p-4">
              <JsonViewer value={log.request} />
            </div>
          </div>

          {/* Right — Response */}
          <div className="flex-1 flex flex-col min-w-0">
            <div className="px-4 py-2.5 border-b border-border flex-shrink-0 bg-warm-50/40">
              <p className="text-[11px] font-semibold text-warm-500 uppercase tracking-wider">
                Response
              </p>
            </div>
            <div className="flex-1 overflow-auto p-4">
              {responseIsJson ? (
                <JsonViewer value={parsedResponse} />
              ) : (
                <pre className="text-xs font-mono leading-relaxed text-warm-700 whitespace-pre-wrap">
                  {log.response || <span className="text-warm-400 italic">empty</span>}
                </pre>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function LLMLogs() {
  const { spaceId } = useParams<{ spaceId: string }>()
  const [space, setSpace] = useState<Space | null>(null)
  const [agents, setAgents] = useState<Agent[]>([])
  const [logs, setLogs] = useState<LLMLog[]>([])
  const [loading, setLoading] = useState(true)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pages, setPages] = useState(1)
  const limit = 20

  // Filters
  const [agentFilter, setAgentFilter] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [searchInput, setSearchInput] = useState('')

  // Modal
  const [selectedLog, setSelectedLog] = useState<LLMLog | null>(null)

  const fetchLogs = useCallback(async () => {
    if (!spaceId) return
    setLoading(true)
    try {
      const params = new URLSearchParams()
      params.set('page', String(page))
      params.set('limit', String(limit))
      if (agentFilter) params.set('agent_id', agentFilter)
      if (dateFrom) params.set('date_from', dateFrom)
      if (dateTo) params.set('date_to', dateTo)
      if (searchQuery) params.set('search', searchQuery)

      const res = await api.get<LogsResponse>(
        `/api/spaces/${spaceId}/llm-logs?${params.toString()}`
      )
      setLogs(res.data.logs)
      setTotal(res.data.total)
      setPages(res.data.pages)
    } catch {
      // silently handle
    } finally {
      setLoading(false)
    }
  }, [spaceId, page, agentFilter, dateFrom, dateTo, searchQuery])

  useEffect(() => {
    fetchLogs()
  }, [fetchLogs])

  useEffect(() => {
    if (!spaceId) return
    const fetchMeta = async () => {
      try {
        const [agentsRes, orgsRes] = await Promise.all([
          api.get(`/api/spaces/${spaceId}/agents`),
          api.get('/api/orgs'),
        ])
        setAgents(agentsRes.data)
        if (orgsRes.data.length > 0) {
          const orgId = orgsRes.data[0].id
          const spacesRes = await api.get(`/api/orgs/${orgId}/spaces`)
          const found = spacesRes.data.find((s: Space) => s.id === spaceId)
          if (found) setSpace(found)
        }
      } catch {
        // silently handle
      }
    }
    fetchMeta()
  }, [spaceId])

  const handleSearch = () => {
    setPage(1)
    setSearchQuery(searchInput)
  }

  const clearFilters = () => {
    setAgentFilter('')
    setDateFrom('')
    setDateTo('')
    setSearchQuery('')
    setSearchInput('')
    setPage(1)
  }

  const hasFilters = agentFilter || dateFrom || dateTo || searchQuery

  if (loading && logs.length === 0) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-warm-200 border-t-accent" />
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="mb-6">
        <p className="text-xs font-medium text-warm-400 uppercase tracking-wider mb-1">
          {space?.name || 'Space'}
        </p>
        <h1 className="text-xl font-semibold text-warm-900">LLM Logs</h1>
        <p className="text-sm text-warm-500 mt-1">
          Track all AI agent queries and responses across the content pipeline.
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-end gap-3 mb-5">
        <div className="flex flex-col gap-1">
          <label className="text-[11px] font-medium text-warm-500 uppercase tracking-wider">
            Agent
          </label>
          <select
            value={agentFilter}
            onChange={(e) => {
              setAgentFilter(e.target.value)
              setPage(1)
            }}
            className="px-3 py-2 bg-card border border-border rounded-lg text-sm text-warm-700 focus:outline-none focus:ring-2 focus:ring-accent/20 min-w-[180px]"
          >
            <option value="">All Agents</option>
            {agents.map((a) => (
              <option key={a.id} value={a.id}>
                {a.avatar} {a.name}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-[11px] font-medium text-warm-500 uppercase tracking-wider">
            From
          </label>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => {
              setDateFrom(e.target.value)
              setPage(1)
            }}
            className="px-3 py-2 bg-card border border-border rounded-lg text-sm text-warm-700 focus:outline-none focus:ring-2 focus:ring-accent/20"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-[11px] font-medium text-warm-500 uppercase tracking-wider">
            To
          </label>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => {
              setDateTo(e.target.value)
              setPage(1)
            }}
            className="px-3 py-2 bg-card border border-border rounded-lg text-sm text-warm-700 focus:outline-none focus:ring-2 focus:ring-accent/20"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-[11px] font-medium text-warm-500 uppercase tracking-wider">
            Task
          </label>
          <div className="flex items-center gap-1">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-warm-400" />
              <input
                type="text"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                placeholder="Search task title..."
                className="pl-8 pr-3 py-2 bg-card border border-border rounded-lg text-sm text-warm-700 placeholder:text-warm-400 focus:outline-none focus:ring-2 focus:ring-accent/20 w-[220px]"
              />
            </div>
            <button
              onClick={handleSearch}
              className="px-3 py-2 bg-accent text-white text-sm font-medium rounded-lg hover:bg-accent-dark transition-colors"
            >
              Search
            </button>
          </div>
        </div>

        {hasFilters && (
          <button
            onClick={clearFilters}
            className="flex items-center gap-1.5 px-3 py-2 text-sm text-warm-500 hover:text-warm-700 hover:bg-warm-50 rounded-lg transition-colors"
          >
            <X className="h-3.5 w-3.5" />
            Clear
          </button>
        )}
      </div>

      {/* Results count */}
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs text-warm-500">
          {total} log{total !== 1 ? 's' : ''} found
          {loading && <span className="ml-2 text-warm-400">Loading...</span>}
        </p>
      </div>

      {/* Logs list */}
      {logs.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <ScrollText className="h-12 w-12 text-warm-300 mb-3" />
          <p className="text-sm text-warm-500">No LLM logs found.</p>
          {hasFilters && (
            <p className="text-xs text-warm-400 mt-1">
              Try adjusting your filters.
            </p>
          )}
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto pb-4">
          {/* Table header */}
          <div className="grid grid-cols-[1fr_160px_120px_140px_100px] gap-4 px-4 py-2 mb-1">
            <p className="text-[11px] font-semibold text-warm-400 uppercase tracking-wider">
              Agent / Model
            </p>
            <p className="text-[11px] font-semibold text-warm-400 uppercase tracking-wider">
              Task ID
            </p>
            <p className="text-[11px] font-semibold text-warm-400 uppercase tracking-wider">
              Duration
            </p>
            <p className="text-[11px] font-semibold text-warm-400 uppercase tracking-wider">
              Time
            </p>
            <p className="text-[11px] font-semibold text-warm-400 uppercase tracking-wider" />
          </div>

          <div className="space-y-1.5">
            {logs.map((log) => {
              const agent = agents.find((a) => a.id === log.agent_id)
              const providerColor =
                PROVIDER_COLORS[log.provider] ||
                'bg-warm-50 text-warm-600 border-warm-200'

              return (
                <div
                  key={log.id}
                  onClick={() => setSelectedLog(log)}
                  className="bg-card border border-border rounded-xl px-4 py-3 grid grid-cols-[1fr_160px_120px_140px_100px] gap-4 items-center cursor-pointer"
                >
                  {/* Agent / model */}
                  <div className="flex items-center gap-2 min-w-0">
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-medium border flex-shrink-0 ${providerColor}`}
                    >
                      {log.provider}
                    </span>
                    {agent && (
                      <span className="text-xs text-warm-600 truncate">
                        {agent.avatar} {agent.name}
                      </span>
                    )}
                    <span className="text-warm-300 flex-shrink-0">|</span>
                    <span className="text-xs text-warm-400 font-mono truncate">
                      {log.model}
                    </span>
                  </div>

                  {/* Task ID */}
                  <p className="text-xs text-warm-400 font-mono truncate">
                    {log.task_id ? log.task_id.slice(-8) : '—'}
                  </p>

                  {/* Duration */}
                  <span className="inline-flex items-center gap-1 text-xs text-warm-500">
                    <Clock className="h-3.5 w-3.5 flex-shrink-0" />
                    {formatDuration(log.duration_ms)}
                  </span>

                  {/* Time */}
                  <span className="text-xs text-warm-400">
                    {formatTime(log.requested_at || log.created_at)}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Pagination */}
      {pages > 1 && (
        <div className="flex items-center justify-center gap-2 pt-4 pb-2 border-t border-border mt-auto">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="p-2 rounded-lg text-warm-500 hover:bg-warm-50 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>

          {Array.from({ length: Math.min(pages, 7) }, (_, i) => {
            let pageNum: number
            if (pages <= 7) {
              pageNum = i + 1
            } else if (page <= 4) {
              pageNum = i + 1
            } else if (page >= pages - 3) {
              pageNum = pages - 6 + i
            } else {
              pageNum = page - 3 + i
            }
            return (
              <button
                key={pageNum}
                onClick={() => setPage(pageNum)}
                className={`min-w-[36px] h-9 rounded-lg text-sm font-medium transition-colors ${
                  pageNum === page
                    ? 'bg-accent text-white'
                    : 'text-warm-600 hover:bg-warm-50'
                }`}
              >
                {pageNum}
              </button>
            )
          })}

          <button
            onClick={() => setPage((p) => Math.min(pages, p + 1))}
            disabled={page >= pages}
            className="p-2 rounded-lg text-warm-500 hover:bg-warm-50 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Log detail modal */}
      {selectedLog && (
        <LogModal
          log={selectedLog}
          agent={agents.find((a) => a.id === selectedLog.agent_id)}
          onClose={() => setSelectedLog(null)}
        />
      )}
    </div>
  )
}
