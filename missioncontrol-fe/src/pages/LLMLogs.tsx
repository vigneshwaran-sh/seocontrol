import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import {
  ScrollText,
  ChevronDown,
  ChevronUp,
  Clock,
  Zap,
  Search,
  X,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import api from '../lib/api'
import type { Agent, Space } from '../types'
import { PIPELINE_ROLES, type PipelineRole } from '../types'

interface LLMMessage {
  role: string
  content: string
}

interface LLMLog {
  id: string
  task_id: string
  task_title: string
  space_id: string
  agent_id: string
  agent_name: string
  agent_role: string
  provider: string
  model: string
  request: LLMMessage[]
  response: string
  is_cached: boolean
  duration_ms: number
  created_at: string
}

const ROLE_LABELS: Record<string, string> = {
  system: 'System',
  user: 'User',
  assistant: 'Assistant',
}

const MSG_ROLE_STYLES: Record<string, string> = {
  system: 'bg-warm-100 text-warm-600',
  user: 'bg-blue-50 text-blue-700',
  assistant: 'bg-violet-50 text-violet-700',
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

  const istOptions: Intl.DateTimeFormatOptions = {
    timeZone: 'Asia/Kolkata',
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  }

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

  return new Intl.DateTimeFormat('en-IN', istOptions).format(date)
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

const ROLE_COLORS: Record<string, string> = {
  content_researcher: 'bg-blue-50 text-blue-700 border-blue-200',
  topic_validator: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  content_writer: 'bg-violet-50 text-violet-700 border-violet-200',
  content_validator: 'bg-amber-50 text-amber-700 border-amber-200',
}

export default function LLMLogs() {
  const { spaceId } = useParams<{ spaceId: string }>()
  const [space, setSpace] = useState<Space | null>(null)
  const [agents, setAgents] = useState<Agent[]>([])
  const [logs, setLogs] = useState<LLMLog[]>([])
  const [loading, setLoading] = useState(true)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pages, setPages] = useState(1)
  const limit = 15

  // Filters
  const [agentFilter, setAgentFilter] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [searchInput, setSearchInput] = useState('')

  // Expanded rows
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())

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

  // Fetch space + agents for filters
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

  const toggleExpand = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

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
        {/* Agent filter */}
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

        {/* Date from */}
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

        {/* Date to */}
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

        {/* Task search */}
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

        {/* Clear filters */}
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
        <div className="space-y-2 flex-1 overflow-y-auto pb-4">
          {logs.map((log) => {
            const isExpanded = expandedIds.has(log.id)
            const roleConfig =
              PIPELINE_ROLES[log.agent_role as PipelineRole] || null
            const roleColor =
              ROLE_COLORS[log.agent_role] ||
              'bg-warm-50 text-warm-600 border-warm-200'

            return (
              <div
                key={log.id}
                className="bg-card border border-border rounded-xl overflow-hidden"
              >
                {/* Log header — always visible */}
                <button
                  onClick={() => toggleExpand(log.id)}
                  className="w-full px-4 py-3 flex items-start gap-3 text-left hover:bg-warm-50/50 transition-colors"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-1.5">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-medium border ${roleColor}`}
                      >
                        {roleConfig?.label || log.agent_role}
                      </span>
                      <span className="text-xs text-warm-500">
                        {log.agent_name}
                      </span>
                      <span className="text-warm-300">|</span>
                      <span className="text-xs text-warm-400 font-mono">
                        {log.model}
                      </span>
                    </div>

                    <p className="text-sm font-medium text-warm-800 truncate">
                      {log.task_title || 'Untitled Task'}
                    </p>

                    <div className="flex items-center gap-3 mt-1.5">
                      {log.is_cached && (
                        <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-600">
                          <Zap className="h-3 w-3" />
                          Cached
                        </span>
                      )}
                      <span className="inline-flex items-center gap-1 text-[11px] text-warm-400">
                        <Clock className="h-3 w-3" />
                        {formatDuration(log.duration_ms)}
                      </span>
                      <span className="text-[11px] text-warm-400">
                        {formatTime(log.created_at)}
                      </span>
                    </div>
                  </div>

                  <div className="pt-1 text-warm-400">
                    {isExpanded ? (
                      <ChevronUp className="h-4 w-4" />
                    ) : (
                      <ChevronDown className="h-4 w-4" />
                    )}
                  </div>
                </button>

                {/* Expanded content */}
                {isExpanded && (
                  <div className="border-t border-border px-4 py-3 space-y-4">
                    {/* Request — full messages array */}
                    <div>
                      <div className="flex items-center gap-2 mb-2">
                        <p className="text-[11px] font-semibold text-warm-500 uppercase tracking-wider">
                          Request
                        </p>
                        <span className="text-[10px] text-warm-400">
                          {log.request.length} message
                          {log.request.length !== 1 ? 's' : ''}
                        </span>
                      </div>
                      <div className="space-y-2">
                        {log.request.map((msg, idx) => (
                          <div
                            key={idx}
                            className="bg-surface-sunk rounded-lg overflow-hidden"
                          >
                            <div className="flex items-center justify-between px-3 py-1.5 border-b border-border/60">
                              <span
                                className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider ${
                                  MSG_ROLE_STYLES[msg.role] ||
                                  'bg-warm-100 text-warm-600'
                                }`}
                              >
                                {ROLE_LABELS[msg.role] || msg.role}
                              </span>
                            </div>
                            <pre className="text-xs text-warm-700 p-3 overflow-x-auto whitespace-pre-wrap max-h-[280px] overflow-y-auto font-mono leading-relaxed">
                              {msg.content}
                            </pre>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Response */}
                    <div>
                      <p className="text-[11px] font-semibold text-warm-500 uppercase tracking-wider mb-2">
                        Response
                      </p>
                      <div className="bg-surface-sunk rounded-lg overflow-hidden">
                        <div className="flex items-center px-3 py-1.5 border-b border-border/60">
                          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider bg-violet-50 text-violet-700">
                            Assistant
                          </span>
                        </div>
                        <pre className="text-xs text-warm-700 p-3 overflow-x-auto whitespace-pre-wrap max-h-[400px] overflow-y-auto font-mono leading-relaxed">
                          {log.response}
                        </pre>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )
          })}
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
    </div>
  )
}
