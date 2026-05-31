import { useState, useEffect, useRef, useMemo } from 'react'
import type { FormEvent } from 'react'
import { X, ChevronDown, Search, Loader2, AlertCircle } from 'lucide-react'
import api from '../lib/api'
import type { Agent } from '../types'
import { PROVIDER_OPTIONS } from '../types'
import { useWorkspace } from '../contexts/WorkspaceContext'

const AVATAR_OPTIONS = [
  '\u{1F916}', '\u{1F9E0}', '\u{1F4DD}', '\u{1F4A1}', '\u{1F50D}', '\u{1F3AF}', '⚡', '\u{1F6E0}️',
  '\u{1F4CA}', '\u{1F3A8}', '\u{1F4E7}', '\u{1F527}', '\u{1F91D}', '\u{1F4CB}', '\u{1F9EA}', '\u{1F680}',
]

interface ProviderModel {
  id: string
  name: string
}

interface AgentModalProps {
  isOpen: boolean
  onClose: () => void
  spaceId: string
  agent: Agent | null
  onSaved: () => void
}

export default function AgentModal({
  isOpen,
  onClose,
  spaceId,
  agent,
  onSaved,
}: AgentModalProps) {
  const { currentOrg } = useWorkspace()

  const [name, setName] = useState('')
  const [avatar, setAvatar] = useState('\u{1F916}')
  const [description, setDescription] = useState('')
  const [provider, setProvider] = useState('')
  const [model, setModel] = useState('')
  const [saving, setSaving] = useState(false)

  // Model autocomplete state
  const [models, setModels] = useState<ProviderModel[]>([])
  const [modelsLoading, setModelsLoading] = useState(false)
  const [modelsError, setModelsError] = useState('')
  const [modelSearch, setModelSearch] = useState('')
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false)
  const modelInputRef = useRef<HTMLInputElement>(null)
  const modelDropdownRef = useRef<HTMLDivElement>(null)

  // Reset form when modal opens
  useEffect(() => {
    if (isOpen) {
      if (agent) {
        setName(agent.name)
        setAvatar(agent.avatar)
        setDescription(agent.description)
        setProvider(agent.provider || '')
        setModel(agent.model)
        setModelSearch(agent.model)
      } else {
        setName('')
        setAvatar('\u{1F916}')
        setDescription('')
        setProvider('')
        setModel('')
        setModelSearch('')
      }
      setModels([])
      setModelsError('')
    }
  }, [isOpen, agent])

  // Fetch models when provider changes
  useEffect(() => {
    if (!provider || !currentOrg) {
      setModels([])
      setModelsError('')
      return
    }

    let cancelled = false
    const fetchModels = async () => {
      setModelsLoading(true)
      setModelsError('')
      setModels([])
      try {
        const resp = await api.get(
          `/api/orgs/${currentOrg.id}/settings/providers/${provider}/models`
        )
        if (!cancelled) {
          setModels(resp.data.models || [])
        }
      } catch (err: any) {
        if (!cancelled) {
          const detail = err?.response?.data?.detail || 'Failed to load models'
          setModelsError(detail)
        }
      } finally {
        if (!cancelled) setModelsLoading(false)
      }
    }

    fetchModels()
    return () => { cancelled = true }
  }, [provider, currentOrg])

  // Close model dropdown on outside click
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (
        modelDropdownRef.current &&
        !modelDropdownRef.current.contains(e.target as Node)
      ) {
        setModelDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  // Filtered models for autocomplete
  const filteredModels = useMemo(() => {
    if (!modelSearch.trim()) return models
    const q = modelSearch.toLowerCase()
    return models.filter(
      (m) =>
        m.id.toLowerCase().includes(q) || m.name.toLowerCase().includes(q)
    )
  }, [models, modelSearch])

  const handleProviderChange = (newProvider: string) => {
    setProvider(newProvider)
    setModel('')
    setModelSearch('')
    setModelDropdownOpen(false)
  }

  const handleModelSelect = (m: ProviderModel) => {
    setModel(m.id)
    setModelSearch(m.id)
    setModelDropdownOpen(false)
  }

  if (!isOpen) return null

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    setSaving(true)
    try {
      const payload = {
        name: name.trim(),
        avatar,
        description: description.trim(),
        provider,
        model: model.trim(),
      }
      if (agent) {
        await api.put(`/api/spaces/${spaceId}/agents/${agent.id}`, payload)
      } else {
        await api.post(`/api/spaces/${spaceId}/agents`, payload)
      }
      onSaved()
      onClose()
    } catch {
      // silently handle
    } finally {
      setSaving(false)
    }
  }

  const selectedProviderMeta = PROVIDER_OPTIONS.find((p) => p.id === provider)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative bg-card rounded-2xl shadow-e3 w-full max-w-md mx-4">
        {/* Header */}
        <div className="flex items-center justify-between p-6 pb-0">
          <h2 className="text-lg font-semibold text-warm-900">
            {agent ? 'Edit Agent' : 'Create Agent'}
          </h2>
          <button
            onClick={onClose}
            className="p-1 text-warm-400 hover:text-warm-600 rounded"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Name */}
          <div>
            <label htmlFor="agentName" className="block text-sm font-medium text-warm-700 mb-1">
              Name
            </label>
            <input
              id="agentName"
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Content Writer"
              className="w-full px-3 py-2 bg-surface-sunk border-0 rounded-lg text-sm text-warm-900 focus:outline-none focus:ring-2 focus:ring-accent/20"
            />
          </div>

          {/* Avatar picker */}
          <div>
            <label className="block text-sm font-medium text-warm-700 mb-2">
              Avatar
            </label>
            <div className="grid grid-cols-8 gap-2">
              {AVATAR_OPTIONS.map((emoji) => (
                <button
                  key={emoji}
                  type="button"
                  onClick={() => setAvatar(emoji)}
                  className={`h-10 w-10 rounded-lg text-xl flex items-center justify-center transition-all ${
                    avatar === emoji
                      ? 'bg-accent-100 ring-2 ring-accent'
                      : 'bg-warm-50 hover:bg-warm-100'
                  }`}
                >
                  {emoji}
                </button>
              ))}
            </div>
          </div>

          {/* Description */}
          <div>
            <label htmlFor="agentDesc" className="block text-sm font-medium text-warm-700 mb-1">
              Description
            </label>
            <textarea
              id="agentDesc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              placeholder="What does this agent do?"
              className="w-full px-3 py-2 bg-surface-sunk border-0 rounded-lg text-sm text-warm-900 focus:outline-none focus:ring-2 focus:ring-accent/20 resize-none"
            />
          </div>

          {/* Provider */}
          <div>
            <label className="block text-sm font-medium text-warm-700 mb-1">
              Provider
            </label>
            <div className="grid grid-cols-3 gap-2">
              {PROVIDER_OPTIONS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => handleProviderChange(p.id)}
                  className={`flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                    provider === p.id
                      ? 'bg-accent-100 ring-2 ring-accent text-accent-dark'
                      : 'bg-surface-sunk text-warm-600 hover:bg-warm-100'
                  }`}
                >
                  <span>{p.icon}</span>
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          {/* Model (autocomplete) */}
          {provider && (
            <div ref={modelDropdownRef}>
              <label className="block text-sm font-medium text-warm-700 mb-1">
                Model
              </label>

              {modelsError ? (
                <div className="flex items-start gap-2 p-3 bg-danger-light rounded-lg">
                  <AlertCircle className="h-4 w-4 text-danger shrink-0 mt-0.5" />
                  <p className="text-xs text-danger">{modelsError}</p>
                </div>
              ) : modelsLoading ? (
                <div className="flex items-center gap-2 px-3 py-2.5 bg-surface-sunk rounded-lg">
                  <Loader2 className="h-4 w-4 animate-spin text-warm-400" />
                  <span className="text-sm text-warm-400">
                    Loading {selectedProviderMeta?.label} models...
                  </span>
                </div>
              ) : (
                <div className="relative">
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-warm-400" />
                    <input
                      ref={modelInputRef}
                      type="text"
                      value={modelSearch}
                      onChange={(e) => {
                        setModelSearch(e.target.value)
                        setModel('')
                        setModelDropdownOpen(true)
                      }}
                      onFocus={() => setModelDropdownOpen(true)}
                      placeholder={`Search ${selectedProviderMeta?.label} models...`}
                      className="w-full pl-9 pr-8 py-2 bg-surface-sunk border-0 rounded-lg text-sm text-warm-900 focus:outline-none focus:ring-2 focus:ring-accent/20"
                    />
                    <ChevronDown
                      className={`absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-warm-400 transition-transform ${
                        modelDropdownOpen ? 'rotate-180' : ''
                      }`}
                    />
                  </div>

                  {modelDropdownOpen && (
                    <div className="absolute z-10 mt-1 w-full bg-card rounded-lg shadow-e2 border border-border max-h-48 overflow-auto">
                      {filteredModels.length === 0 ? (
                        <div className="px-3 py-4 text-center text-xs text-warm-400">
                          {modelSearch ? 'No matching models' : 'No models available'}
                        </div>
                      ) : (
                        filteredModels.map((m) => (
                          <button
                            key={m.id}
                            type="button"
                            onClick={() => handleModelSelect(m)}
                            className={`w-full text-left px-3 py-2 text-sm hover:bg-warm-50 transition-colors flex items-center justify-between gap-2 ${
                              model === m.id
                                ? 'bg-accent-50 text-accent-dark'
                                : 'text-warm-700'
                            }`}
                          >
                            <span className="truncate font-medium">{m.id}</span>
                            {m.name !== m.id && (
                              <span className="text-xs text-warm-400 shrink-0 truncate max-w-[40%]">
                                {m.name}
                              </span>
                            )}
                          </button>
                        ))
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-warm-600 bg-warm-50 rounded-lg hover:bg-warm-100 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 text-sm font-medium text-white bg-lumen rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saving ? 'Saving...' : agent ? 'Update Agent' : 'Create Agent'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
