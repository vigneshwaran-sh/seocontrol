import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Save, Check, Loader2, Search, ChevronDown, AlertCircle } from 'lucide-react'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Underline from '@tiptap/extension-underline'
import Placeholder from '@tiptap/extension-placeholder'
import api from '../lib/api'
import type { Agent } from '../types'
import { PROVIDER_OPTIONS, PIPELINE_ROLES, type PipelineRole } from '../types'
import { useWorkspace } from '../contexts/WorkspaceContext'

interface ProviderModel {
  id: string
  name: string
}

type SaveState = 'idle' | 'saving' | 'saved'

export default function AgentDetail() {
  const { spaceId, agentId } = useParams<{ spaceId: string; agentId: string }>()
  const navigate = useNavigate()
  const { currentOrg } = useWorkspace()

  // Agent state
  const [agent, setAgent] = useState<Agent | null>(null)
  const [agentName, setAgentName] = useState('')
  const [agentDescription, setAgentDescription] = useState('')
  const [agentProvider, setAgentProvider] = useState('')
  const [agentModel, setAgentModel] = useState('')
  const [agentIsActive, setAgentIsActive] = useState(true)
  const [savingAgent, setSavingAgent] = useState(false)

  // Model autocomplete state
  const [models, setModels] = useState<ProviderModel[]>([])
  const [modelsLoading, setModelsLoading] = useState(false)
  const [modelsError, setModelsError] = useState('')
  const [modelSearch, setModelSearch] = useState('')
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false)
  const modelDropdownRef = useRef<HTMLDivElement>(null)

  // Skill content auto-save state
  const [skillSaveState, setSkillSaveState] = useState<SaveState>('idle')
  const saveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const initialLoadRef = useRef(true)

  const [loading, setLoading] = useState(true)

  // Auto-save skill content
  const saveSkillContent = useCallback(
    async (content: string) => {
      if (!spaceId || !agentId) return
      setSkillSaveState('saving')
      try {
        await api.put(`/api/spaces/${spaceId}/agents/${agentId}`, {
          skill_content: content,
        })
        setSkillSaveState('saved')
        setTimeout(() => setSkillSaveState('idle'), 2000)
      } catch {
        setSkillSaveState('idle')
      }
    },
    [spaceId, agentId]
  )

  const debouncedSaveSkill = useCallback(
    (content: string) => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current)
      }
      saveTimeoutRef.current = setTimeout(() => {
        saveSkillContent(content)
      }, 1000)
    },
    [saveSkillContent]
  )

  const editor = useEditor({
    extensions: [
      StarterKit,
      Underline,
      Placeholder.configure({
        placeholder: 'Write the agent\'s instruction manual here... Use headings, lists, and rich text to organize the content.',
      }),
    ],
    content: '',
    onUpdate: ({ editor: ed }) => {
      if (!initialLoadRef.current) {
        debouncedSaveSkill(ed.getHTML())
      }
    },
    editorProps: {
      attributes: {
        class: 'prose prose-warm max-w-none focus:outline-none min-h-[300px]',
      },
    },
  })

  const fetchAgent = useCallback(async () => {
    if (!spaceId || !agentId) return
    try {
      const response = await api.get(`/api/spaces/${spaceId}/agents/${agentId}`)
      const data: Agent = response.data
      setAgent(data)
      setAgentName(data.name)
      setAgentDescription(data.description)
      setAgentProvider(data.provider || '')
      setAgentModel(data.model || '')
      setModelSearch(data.model || '')
      setAgentIsActive(data.is_active)
      if (editor) {
        editor.commands.setContent(data.skill_content || '')
      }
      initialLoadRef.current = false
    } catch {
      // silently handle
    } finally {
      setLoading(false)
    }
  }, [spaceId, agentId, editor])

  useEffect(() => {
    fetchAgent()
  }, [fetchAgent])

  // Fetch models when provider changes
  useEffect(() => {
    if (!agentProvider || !currentOrg) {
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
          `/api/orgs/${currentOrg.id}/settings/providers/${agentProvider}/models`
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
  }, [agentProvider, currentOrg])

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

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current)
      }
    }
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
    setAgentProvider(newProvider)
    setAgentModel('')
    setModelSearch('')
    setModelDropdownOpen(false)
  }

  const handleModelSelect = (m: ProviderModel) => {
    setAgentModel(m.id)
    setModelSearch(m.id)
    setModelDropdownOpen(false)
  }

  const handleSaveAgent = async () => {
    if (!spaceId || !agentId || !agent) return
    setSavingAgent(true)
    try {
      await api.put(`/api/spaces/${spaceId}/agents/${agentId}`, {
        name: agentName.trim(),
        avatar: agent.avatar,
        description: agentDescription.trim(),
        provider: agentProvider,
        model: agentModel.trim(),
        is_active: agentIsActive,
      })
      await fetchAgent()
    } catch {
      // silently handle
    } finally {
      setSavingAgent(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-warm-200 border-t-accent" />
      </div>
    )
  }

  if (!agent) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-warm-500 text-sm">Agent not found.</p>
      </div>
    )
  }

  const selectedProviderMeta = PROVIDER_OPTIONS.find((p) => p.id === agentProvider)
  const isPipelineAgent = agent ? Boolean(agent.role && agent.role in PIPELINE_ROLES) : false
  const roleMeta = agent?.role ? PIPELINE_ROLES[agent.role as PipelineRole] : null

  return (
    <div className="h-full flex flex-col max-w-3xl">
      {/* Back button */}
      <button
        onClick={() => navigate(`/spaces/${spaceId}/agents`)}
        className="flex items-center gap-1.5 text-sm text-warm-500 hover:text-warm-700 mb-6 transition-colors self-start"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Agents
      </button>

      {/* Agent header card */}
      <div className="bg-card rounded-xl shadow-e1 p-6 mb-6">
        <div className="flex items-start gap-5">
          {/* Avatar */}
          <div className="h-16 w-16 rounded-xl bg-accent-50 flex items-center justify-center shrink-0">
            <span className="text-3xl">{agent.avatar}</span>
          </div>

          {/* Editable info */}
          <div className="flex-1 min-w-0 space-y-3">
            {/* Role badge */}
            {roleMeta && (
              <span className={`inline-block text-[11px] font-medium px-2.5 py-1 rounded-full ${roleMeta.color}`}>
                {roleMeta.label}
              </span>
            )}

            <div>
              <label htmlFor="agentDetailName" className="block text-xs font-medium text-warm-500 mb-1">
                Name
              </label>
              {isPipelineAgent ? (
                <p className="px-3 py-2 text-sm font-semibold text-warm-900">{agentName}</p>
              ) : (
                <input
                  id="agentDetailName"
                  type="text"
                  value={agentName}
                  onChange={(e) => setAgentName(e.target.value)}
                  className="w-full px-3 py-2 bg-surface-sunk border-0 rounded-lg text-sm font-semibold text-warm-900 focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent"
                />
              )}
            </div>

            <div>
              <label htmlFor="agentDetailDesc" className="block text-xs font-medium text-warm-500 mb-1">
                Description
              </label>
              {isPipelineAgent ? (
                <p className="px-3 py-2 text-sm text-warm-700">{agentDescription}</p>
              ) : (
                <textarea
                  id="agentDetailDesc"
                  value={agentDescription}
                  onChange={(e) => setAgentDescription(e.target.value)}
                  rows={2}
                  className="w-full px-3 py-2 bg-surface-sunk border-0 rounded-lg text-sm text-warm-900 focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent resize-none"
                />
              )}
            </div>

            {/* Provider */}
            <div>
              <label className="block text-xs font-medium text-warm-500 mb-1">
                Provider
              </label>
              <div className="grid grid-cols-3 gap-2">
                {PROVIDER_OPTIONS.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => handleProviderChange(p.id)}
                    className={`flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                      agentProvider === p.id
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

            {/* Model autocomplete */}
            {agentProvider && (
              <div ref={modelDropdownRef}>
                <label className="block text-xs font-medium text-warm-500 mb-1">
                  Model
                </label>

                {modelsError ? (
                  <div className="flex items-start gap-2 p-3 bg-danger-light rounded-lg">
                    <AlertCircle className="h-4 w-4 text-danger shrink-0 mt-0.5" />
                    <p className="text-xs text-danger">{modelsError}</p>
                  </div>
                ) : modelsLoading ? (
                  <div className="flex items-center gap-2 px-3 py-2 bg-surface-sunk rounded-lg">
                    <Loader2 className="h-4 w-4 animate-spin text-warm-400" />
                    <span className="text-xs text-warm-400">
                      Loading {selectedProviderMeta?.label} models...
                    </span>
                  </div>
                ) : (
                  <div className="relative">
                    <div className="relative">
                      <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-warm-400" />
                      <input
                        type="text"
                        value={modelSearch}
                        onChange={(e) => {
                          setModelSearch(e.target.value)
                          setAgentModel('')
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
                                agentModel === m.id
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

            <div className="flex items-center gap-4 flex-wrap">
              {/* Active toggle */}
              <label className="flex items-center gap-2 cursor-pointer">
                <div
                  className={`relative w-9 h-5 rounded-full transition-colors ${
                    agentIsActive ? 'bg-success' : 'bg-warm-300'
                  }`}
                  onClick={() => setAgentIsActive(!agentIsActive)}
                >
                  <div
                    className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${
                      agentIsActive ? 'translate-x-4' : 'translate-x-0.5'
                    }`}
                  />
                </div>
                <span className="text-xs font-medium text-warm-600">
                  {agentIsActive ? 'Active' : 'Inactive'}
                </span>
              </label>

              {/* Save button */}
              <button
                onClick={handleSaveAgent}
                disabled={savingAgent}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-lumen rounded-lg disabled:opacity-50 ml-auto"
              >
                <Save className="h-3.5 w-3.5" />
                {savingAgent ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Skill content section */}
      <div className="bg-card rounded-xl shadow-e1 p-6 flex-1 flex flex-col">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-sm font-semibold text-warm-900">Agent Instructions</h2>
            <p className="text-xs text-warm-400 mt-0.5">
              Write a detailed instruction manual for this agent. Changes are auto-saved.
            </p>
          </div>

          {/* Auto-save status */}
          <div className="flex items-center gap-1.5 text-xs text-warm-400">
            {skillSaveState === 'saving' && (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Saving...
              </>
            )}
            {skillSaveState === 'saved' && (
              <>
                <Check className="h-3.5 w-3.5 text-success" />
                <span className="text-success">Saved</span>
              </>
            )}
          </div>
        </div>

        {/* Toolbar */}
        {editor && (
          <div className="flex items-center gap-1 pb-4 mb-4 border-b border-border flex-wrap">
            <ToolbarButton
              active={editor.isActive('bold')}
              onClick={() => editor.chain().focus().toggleBold().run()}
              label="B"
              fontWeight="font-bold"
            />
            <ToolbarButton
              active={editor.isActive('italic')}
              onClick={() => editor.chain().focus().toggleItalic().run()}
              label="I"
              fontStyle="italic"
            />
            <ToolbarButton
              active={editor.isActive('underline')}
              onClick={() => editor.chain().focus().toggleUnderline().run()}
              label="U"
              underline
            />

            <div className="w-px h-5 bg-border mx-1" />

            <ToolbarButton
              active={editor.isActive('heading', { level: 1 })}
              onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
              label="H1"
            />
            <ToolbarButton
              active={editor.isActive('heading', { level: 2 })}
              onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
              label="H2"
            />
            <ToolbarButton
              active={editor.isActive('heading', { level: 3 })}
              onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
              label="H3"
            />

            <div className="w-px h-5 bg-border mx-1" />

            <ToolbarButton
              active={editor.isActive('bulletList')}
              onClick={() => editor.chain().focus().toggleBulletList().run()}
              label="UL"
            />
            <ToolbarButton
              active={editor.isActive('orderedList')}
              onClick={() => editor.chain().focus().toggleOrderedList().run()}
              label="OL"
            />

            <div className="w-px h-5 bg-border mx-1" />

            <ToolbarButton
              active={editor.isActive('codeBlock')}
              onClick={() => editor.chain().focus().toggleCodeBlock().run()}
              label="Code"
            />
            <ToolbarButton
              active={editor.isActive('blockquote')}
              onClick={() => editor.chain().focus().toggleBlockquote().run()}
              label="Quote"
            />
          </div>
        )}

        {/* Editor */}
        <div className="tiptap-editor flex-1">
          <EditorContent editor={editor} />
        </div>
      </div>
    </div>
  )
}

function ToolbarButton({
  active,
  onClick,
  label,
  fontWeight,
  fontStyle,
  underline,
}: {
  active: boolean
  onClick: () => void
  label: string
  fontWeight?: string
  fontStyle?: string
  underline?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-2.5 py-1.5 text-xs rounded-lg transition-colors ${
        active
          ? 'bg-accent-100 text-accent-dark'
          : 'text-warm-600 hover:bg-warm-50'
      } ${fontWeight || ''} ${fontStyle || ''} ${underline ? 'underline' : ''}`}
    >
      {label}
    </button>
  )
}
