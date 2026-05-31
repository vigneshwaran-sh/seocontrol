import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Bot } from 'lucide-react'
import api from '../lib/api'
import type { Agent, Space } from '../types'
import { PROVIDER_OPTIONS, PIPELINE_ROLES, type PipelineRole } from '../types'

export default function SpaceAgents() {
  const { spaceId } = useParams<{ spaceId: string }>()
  const navigate = useNavigate()
  const [space, setSpace] = useState<Space | null>(null)
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)

  const fetchAgents = useCallback(async () => {
    if (!spaceId) return
    try {
      const response = await api.get(`/api/spaces/${spaceId}/agents`)
      setAgents(response.data)
    } catch {
      // silently handle
    } finally {
      setLoading(false)
    }
  }, [spaceId])

  useEffect(() => {
    const fetchSpace = async () => {
      if (!spaceId) return
      try {
        const orgsRes = await api.get('/api/orgs')
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

    fetchSpace()
    fetchAgents()
  }, [spaceId, fetchAgents])

  // Order agents by pipeline sequence
  const pipelineOrder: PipelineRole[] = [
    'content_researcher',
    'topic_validator',
    'content_writer',
    'content_validator',
  ]

  const sortedAgents = [...agents].sort((a, b) => {
    const aIdx = pipelineOrder.indexOf(a.role as PipelineRole)
    const bIdx = pipelineOrder.indexOf(b.role as PipelineRole)
    return (aIdx === -1 ? 99 : aIdx) - (bIdx === -1 ? 99 : bIdx)
  })

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-warm-200 border-t-accent" />
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col">
      {/* Page header */}
      <div className="mb-6">
        <p className="text-xs font-medium text-warm-400 uppercase tracking-wider mb-1">
          {space?.name || 'Space'}
        </p>
        <h1 className="text-xl font-semibold text-warm-900">Content Pipeline Agents</h1>
        <p className="text-sm text-warm-500 mt-1">
          4 AI agents work together to research, validate, write, and review content.
        </p>
      </div>

      {/* Pipeline flow indicator */}
      <div className="flex items-center gap-2 mb-6 overflow-x-auto pb-2">
        {pipelineOrder.map((role, idx) => {
          const meta = PIPELINE_ROLES[role]
          const agent = agents.find((a) => a.role === role)
          const configured = agent?.provider && agent?.model
          return (
            <div key={role} className="flex items-center gap-2 shrink-0">
              <div
                className={`px-3 py-1.5 rounded-lg text-xs font-medium ${meta.color} ${
                  configured ? 'ring-2 ring-success/30' : 'opacity-60'
                }`}
              >
                {meta.label}
              </div>
              {idx < pipelineOrder.length - 1 && (
                <span className="text-warm-300 text-lg">→</span>
              )}
            </div>
          )
        })}
      </div>

      {/* Agent grid */}
      {sortedAgents.length === 0 ? (
        <div className="bg-card rounded-xl shadow-e1 p-12 text-center">
          <Bot className="h-10 w-10 text-warm-300 mx-auto mb-3" />
          <p className="text-warm-500 text-sm">No pipeline agents found.</p>
          <p className="text-warm-400 text-xs mt-1">
            Create a new space to auto-generate pipeline agents.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {sortedAgents.map((agent) => {
            const roleMeta = PIPELINE_ROLES[agent.role as PipelineRole]
            const configured = agent.provider && agent.model

            return (
              <div
                key={agent.id}
                className="bg-card rounded-xl shadow-e1 card-hover p-5 group cursor-pointer relative"
                onClick={() => navigate(`/spaces/${spaceId}/agents/${agent.id}`)}
              >
                <div className="flex items-start gap-4">
                  {/* Avatar */}
                  <div className="h-12 w-12 rounded-xl bg-accent-50 flex items-center justify-center shrink-0">
                    <span className="text-2xl">{agent.avatar}</span>
                  </div>

                  {/* Info */}
                  <div className="min-w-0 flex-1">
                    <h3 className="text-sm font-semibold text-warm-900 truncate">
                      {agent.name}
                    </h3>
                    {agent.description && (
                      <p className="text-xs text-warm-500 mt-0.5 line-clamp-2">
                        {agent.description}
                      </p>
                    )}

                    <div className="flex items-center gap-2 mt-3 flex-wrap">
                      {/* Role badge */}
                      {roleMeta && (
                        <span
                          className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${roleMeta.color}`}
                        >
                          {roleMeta.label}
                        </span>
                      )}

                      {/* Provider badge */}
                      {agent.provider &&
                        (() => {
                          const prov = PROVIDER_OPTIONS.find((p) => p.id === agent.provider)
                          return prov ? (
                            <span className="text-[10px] font-medium px-2 py-0.5 bg-accent-50 text-accent-dark rounded-full">
                              {prov.icon} {prov.label}
                            </span>
                          ) : null
                        })()}

                      {/* Model badge */}
                      {agent.model && (
                        <span className="text-[10px] font-medium px-2 py-0.5 bg-purple-light text-purple rounded-full">
                          {agent.model}
                        </span>
                      )}

                      {/* Configuration status */}
                      <span
                        className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${
                          configured
                            ? 'bg-success-light text-success'
                            : 'bg-warning-light text-warning'
                        }`}
                      >
                        {configured ? 'Configured' : 'Needs setup'}
                      </span>

                      {/* Skill content indicator */}
                      {agent.skill_content && (
                        <span className="text-[10px] font-medium px-2 py-0.5 bg-accent-50 text-accent-dark rounded-full">
                          Has instructions
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
