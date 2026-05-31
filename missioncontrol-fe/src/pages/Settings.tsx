import { useState, useEffect, useCallback } from 'react'
import { Eye, EyeOff, Check, Loader2, ExternalLink, Link2, CheckCircle2, XCircle } from 'lucide-react'
import { useWorkspace } from '../contexts/WorkspaceContext'
import api from '../lib/api'

interface APIKeys {
  openai_api_key: string
  gemini_api_key: string
  claude_api_key: string
}

interface NotionSettings {
  notion_token: string
  notion_database_id: string
  connected: boolean
}

type SaveState = 'idle' | 'saving' | 'saved' | 'error'

const EMPTY_KEYS: APIKeys = {
  openai_api_key: '',
  gemini_api_key: '',
  claude_api_key: '',
}

const EMPTY_NOTION: NotionSettings = {
  notion_token: '',
  notion_database_id: '',
  connected: false,
}

export default function Settings() {
  const { currentOrg } = useWorkspace()
  const [loading, setLoading] = useState(true)

  // API Keys state
  const [maskedKeys, setMaskedKeys] = useState<APIKeys>(EMPTY_KEYS)
  const [draft, setDraft] = useState<APIKeys>(EMPTY_KEYS)
  const [touched, setTouched] = useState<Set<string>>(new Set())
  const [visible, setVisible] = useState<Record<string, boolean>>({})
  const [saveState, setSaveState] = useState<SaveState>('idle')

  // Notion state
  const [notionSettings, setNotionSettings] = useState<NotionSettings>(EMPTY_NOTION)
  const [notionDraft, setNotionDraft] = useState({ token: '', databaseId: '' })
  const [notionTouched, setNotionTouched] = useState(false)
  const [notionSaveState, setNotionSaveState] = useState<SaveState>('idle')
  const [notionSaveError, setNotionSaveError] = useState('')
  const [notionTokenVisible, setNotionTokenVisible] = useState(false)
  const [testingNotion, setTestingNotion] = useState(false)
  const [notionTestResult, setNotionTestResult] = useState<{
    status: string
    bot_name?: string
    workspace?: string
  } | null>(null)

  const fetchKeys = useCallback(async () => {
    if (!currentOrg) return
    try {
      const res = await api.get(`/api/orgs/${currentOrg.id}/settings/api-keys`)
      setMaskedKeys(res.data)
    } catch {
      // silently handle
    }
  }, [currentOrg])

  const fetchNotion = useCallback(async () => {
    if (!currentOrg) return
    try {
      const res = await api.get(`/api/orgs/${currentOrg.id}/settings/notion`)
      setNotionSettings(res.data)
    } catch {
      // silently handle
    }
  }, [currentOrg])

  useEffect(() => {
    if (!currentOrg) return
    Promise.all([fetchKeys(), fetchNotion()]).finally(() => setLoading(false))
  }, [fetchKeys, fetchNotion, currentOrg])

  // API Keys handlers
  const handleChange = (field: keyof APIKeys, value: string) => {
    setDraft((prev) => ({ ...prev, [field]: value }))
    setTouched((prev) => new Set(prev).add(field))
  }

  const toggleVisibility = (field: string) => {
    setVisible((prev) => ({ ...prev, [field]: !prev[field] }))
  }

  const handleSave = async () => {
    if (!currentOrg || touched.size === 0) return
    setSaveState('saving')
    try {
      const payload: Record<string, string> = {}
      for (const field of touched) {
        payload[field] = draft[field as keyof APIKeys]
      }
      const res = await api.put(
        `/api/orgs/${currentOrg.id}/settings/api-keys`,
        payload
      )
      setMaskedKeys(res.data)
      setDraft(EMPTY_KEYS)
      setTouched(new Set())
      setVisible({})
      setSaveState('saved')
      setTimeout(() => setSaveState('idle'), 2500)
    } catch {
      setSaveState('error')
      setTimeout(() => setSaveState('idle'), 3000)
    }
  }

  // Notion handlers
  const handleNotionSave = async () => {
    if (!currentOrg || !notionTouched) return
    setNotionSaveState('saving')
    setNotionSaveError('')
    try {
      const payload: Record<string, string> = {}
      if (notionDraft.token) payload.notion_token = notionDraft.token
      if (notionDraft.databaseId) payload.notion_database_id = notionDraft.databaseId

      const res = await api.put(
        `/api/orgs/${currentOrg.id}/settings/notion`,
        payload
      )
      setNotionSettings(res.data)
      setNotionDraft({ token: '', databaseId: '' })
      setNotionTouched(false)
      setNotionTokenVisible(false)
      setNotionSaveState('saved')
      setTimeout(() => setNotionSaveState('idle'), 2500)
    } catch (err: any) {
      const detail = err?.response?.data?.detail || 'Failed to save'
      setNotionSaveError(detail)
      setNotionSaveState('error')
      setTimeout(() => setNotionSaveState('idle'), 4000)
    }
  }

  const handleTestNotion = async () => {
    if (!currentOrg) return
    setTestingNotion(true)
    setNotionTestResult(null)
    try {
      const res = await api.post(`/api/orgs/${currentOrg.id}/settings/notion/test`)
      setNotionTestResult(res.data)
    } catch (err: any) {
      setNotionTestResult({
        status: 'error',
        bot_name: err?.response?.data?.detail || 'Connection failed',
      })
    } finally {
      setTestingNotion(false)
    }
  }

  const getPlaceholder = (field: keyof APIKeys) => {
    const masked = maskedKeys[field]
    if (masked) return masked
    switch (field) {
      case 'openai_api_key':
        return 'sk-...'
      case 'gemini_api_key':
        return 'AIza...'
      case 'claude_api_key':
        return 'sk-ant-...'
      default:
        return ''
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-warm-200 border-t-accent" />
      </div>
    )
  }

  return (
    <div className="max-w-2xl">
      {/* Header */}
      <div className="mb-8">
        <p className="text-xs font-medium text-warm-400 uppercase tracking-wider mb-1">
          Admin
        </p>
        <h1 className="text-xl font-semibold text-warm-900">Settings</h1>
        <p className="text-sm text-warm-500 mt-1">
          Configure API keys and integrations.
        </p>
      </div>

      {/* ─── AI Provider Keys ────────────────────────────────────── */}
      <div className="space-y-6 mb-10">
        <h2 className="text-sm font-semibold text-warm-800 uppercase tracking-wider">
          AI Providers
        </h2>

        <KeySection
          title="OpenAI"
          description="Used for GPT-4o, GPT-4, and other OpenAI models."
          field="openai_api_key"
          value={draft.openai_api_key}
          placeholder={getPlaceholder('openai_api_key')}
          isVisible={visible.openai_api_key}
          onChange={(v) => handleChange('openai_api_key', v)}
          onToggleVisibility={() => toggleVisibility('openai_api_key')}
          helpLink="https://platform.openai.com/api-keys"
          helpText="Get your API key"
        />

        <KeySection
          title="Google Gemini"
          description="Used for Gemini Pro and other Google AI models."
          field="gemini_api_key"
          value={draft.gemini_api_key}
          placeholder={getPlaceholder('gemini_api_key')}
          isVisible={visible.gemini_api_key}
          onChange={(v) => handleChange('gemini_api_key', v)}
          onToggleVisibility={() => toggleVisibility('gemini_api_key')}
          helpLink="https://aistudio.google.com/apikey"
          helpText="Get your API key"
        />

        <KeySection
          title="Anthropic Claude"
          description="Used for Claude Sonnet, Opus, and other Anthropic models."
          field="claude_api_key"
          value={draft.claude_api_key}
          placeholder={getPlaceholder('claude_api_key')}
          isVisible={visible.claude_api_key}
          onChange={(v) => handleChange('claude_api_key', v)}
          onToggleVisibility={() => toggleVisibility('claude_api_key')}
          helpLink="https://console.anthropic.com/settings/keys"
          helpText="Get your API key"
        />

        {/* Save bar */}
        <div className="flex items-center justify-between pt-2">
          <div className="text-xs text-warm-400">
            {touched.size > 0 && saveState === 'idle' && (
              <span>{touched.size} unsaved change{touched.size !== 1 ? 's' : ''}</span>
            )}
            {saveState === 'saved' && (
              <span className="flex items-center gap-1 text-success">
                <Check className="h-3.5 w-3.5" />
                Keys saved successfully
              </span>
            )}
            {saveState === 'error' && (
              <span className="text-danger">Failed to save. Please try again.</span>
            )}
          </div>
          <button
            onClick={handleSave}
            disabled={touched.size === 0 || saveState === 'saving'}
            className="px-5 py-2 text-sm font-medium text-white bg-lumen rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saveState === 'saving' ? (
              <span className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                Saving...
              </span>
            ) : (
              'Save API Keys'
            )}
          </button>
        </div>
      </div>

      {/* ─── Notion Integration ──────────────────────────────────── */}
      <div className="space-y-4">
        <h2 className="text-sm font-semibold text-warm-800 uppercase tracking-wider">
          Integrations
        </h2>

        <div className="bg-card rounded-xl shadow-e1 p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 bg-warm-900 rounded-lg flex items-center justify-center">
                <span className="text-white text-lg font-bold">N</span>
              </div>
              <div>
                <h3 className="text-sm font-semibold text-warm-900">Notion</h3>
                <p className="text-xs text-warm-500">
                  Blog content is published to your Notion database.
                </p>
              </div>
            </div>
            {notionSettings.connected && (
              <span className="flex items-center gap-1 px-2 py-1 text-[10px] font-medium bg-success-light text-success rounded-full">
                <CheckCircle2 className="h-3 w-3" />
                Connected
              </span>
            )}
          </div>

          {/* Token */}
          <div className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-warm-600 mb-1">
                Integration Token
              </label>
              <div className="relative">
                <input
                  type={notionTokenVisible ? 'text' : 'password'}
                  value={notionDraft.token}
                  onChange={(e) => {
                    setNotionDraft((p) => ({ ...p, token: e.target.value }))
                    setNotionTouched(true)
                  }}
                  placeholder={notionSettings.connected ? notionSettings.notion_token : 'ntn_...'}
                  className="w-full px-3 py-2.5 pr-10 bg-surface-sunk border-0 rounded-lg text-sm text-warm-900 font-mono placeholder:text-warm-400 focus:outline-none focus:ring-2 focus:ring-accent/20"
                />
                <button
                  type="button"
                  onClick={() => setNotionTokenVisible(!notionTokenVisible)}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 p-1 text-warm-400 hover:text-warm-600 rounded transition-colors"
                >
                  {notionTokenVisible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              <a
                href="https://www.notion.so/profile/integrations"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 mt-1.5 text-xs text-accent hover:text-accent-dark transition-colors"
              >
                Create an integration
                <ExternalLink className="h-3 w-3" />
              </a>
            </div>

            {/* Database ID */}
            <div>
              <label className="block text-xs font-medium text-warm-600 mb-1">
                Database ID
              </label>
              <div className="relative">
                <Link2 className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-warm-400" />
                <input
                  type="text"
                  value={notionDraft.databaseId || (notionTouched ? '' : notionSettings.notion_database_id)}
                  onChange={(e) => {
                    setNotionDraft((p) => ({ ...p, databaseId: e.target.value }))
                    setNotionTouched(true)
                  }}
                  placeholder="Paste Notion database URL or ID"
                  className="w-full pl-9 pr-3 py-2.5 bg-surface-sunk border-0 rounded-lg text-sm text-warm-900 font-mono placeholder:text-warm-400 focus:outline-none focus:ring-2 focus:ring-accent/20"
                />
              </div>
              <p className="text-[10px] text-warm-400 mt-1">
                Blog entries will be created in this Notion database. Share it with your integration.
              </p>
            </div>
          </div>

          {/* Error */}
          {notionSaveError && (
            <div className="mt-3 flex items-start gap-2 p-3 bg-danger-light rounded-lg">
              <XCircle className="h-4 w-4 text-danger shrink-0 mt-0.5" />
              <p className="text-xs text-danger">{notionSaveError}</p>
            </div>
          )}

          {/* Test result */}
          {notionTestResult && (
            <div
              className={`mt-3 flex items-start gap-2 p-3 rounded-lg ${
                notionTestResult.status === 'connected'
                  ? 'bg-success-light'
                  : 'bg-danger-light'
              }`}
            >
              {notionTestResult.status === 'connected' ? (
                <CheckCircle2 className="h-4 w-4 text-success shrink-0 mt-0.5" />
              ) : (
                <XCircle className="h-4 w-4 text-danger shrink-0 mt-0.5" />
              )}
              <div className="text-xs">
                {notionTestResult.status === 'connected' ? (
                  <>
                    <p className="font-medium text-success">Connected successfully</p>
                    <p className="text-warm-600 mt-0.5">
                      Bot: {notionTestResult.bot_name} &middot; Workspace: {notionTestResult.workspace}
                    </p>
                  </>
                ) : (
                  <p className="text-danger">{notionTestResult.bot_name}</p>
                )}
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center justify-between mt-4 pt-4 border-t border-border">
            <button
              type="button"
              onClick={handleTestNotion}
              disabled={testingNotion || !notionSettings.connected}
              className="px-4 py-2 text-xs font-medium text-warm-600 bg-warm-50 rounded-lg hover:bg-warm-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {testingNotion ? (
                <span className="flex items-center gap-1.5">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Testing...
                </span>
              ) : (
                'Test Connection'
              )}
            </button>

            <div className="flex items-center gap-3">
              {notionSaveState === 'saved' && (
                <span className="flex items-center gap-1 text-xs text-success">
                  <Check className="h-3.5 w-3.5" />
                  Saved
                </span>
              )}
              <button
                onClick={handleNotionSave}
                disabled={!notionTouched || notionSaveState === 'saving'}
                className="px-5 py-2 text-sm font-medium text-white bg-lumen rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {notionSaveState === 'saving' ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Saving...
                  </span>
                ) : (
                  'Save Notion Settings'
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ----------------------------------------------------------------
   Sub-components
   ---------------------------------------------------------------- */

function KeySection({
  title,
  description,
  field,
  value,
  placeholder,
  isVisible,
  onChange,
  onToggleVisibility,
  helpLink,
  helpText,
}: {
  title: string
  description: string
  field: string
  value: string
  placeholder: string
  isVisible: boolean
  onChange: (v: string) => void
  onToggleVisibility: () => void
  helpLink: string
  helpText: string
}) {
  return (
    <div className="bg-card rounded-xl shadow-e1 p-6">
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-warm-900">{title}</h3>
        <p className="text-xs text-warm-500 mt-0.5">{description}</p>
      </div>
      <KeyInput
        field={field}
        value={value}
        placeholder={placeholder}
        isVisible={isVisible}
        onChange={onChange}
        onToggleVisibility={onToggleVisibility}
      />
      <a
        href={helpLink}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 mt-2.5 text-xs text-accent hover:text-accent-dark transition-colors"
      >
        {helpText}
        <ExternalLink className="h-3 w-3" />
      </a>
    </div>
  )
}

function KeyInput({
  field,
  value,
  placeholder,
  isVisible,
  onChange,
  onToggleVisibility,
}: {
  field: string
  value: string
  placeholder: string
  isVisible: boolean
  onChange: (v: string) => void
  onToggleVisibility: () => void
}) {
  return (
    <div className="relative">
      <input
        id={field}
        type={isVisible ? 'text' : 'password'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full px-3 py-2.5 pr-10 bg-surface-sunk border-0 rounded-lg text-sm text-warm-900 font-mono placeholder:text-warm-400 focus:outline-none focus:ring-2 focus:ring-accent/20"
      />
      <button
        type="button"
        onClick={onToggleVisibility}
        className="absolute right-2.5 top-1/2 -translate-y-1/2 p-1 text-warm-400 hover:text-warm-600 rounded transition-colors"
      >
        {isVisible ? (
          <EyeOff className="h-4 w-4" />
        ) : (
          <Eye className="h-4 w-4" />
        )}
      </button>
    </div>
  )
}
