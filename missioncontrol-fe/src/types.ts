export interface Org {
  id: string
  name: string
  created_at: string
  updated_at: string
}

export interface Space {
  id: string
  org_id: string
  name: string
  icon: string
  color: string
  description: string
  niche: string
  topic_count: number
  created_at: string
  updated_at: string
}

export interface TaskStatus {
  id: string
  name: string
  color: string
  order: number
}

export interface Task {
  id: string
  space_id: string
  title: string
  description: string
  status_id: string
  status_name?: string
  priority: string
  assignee_id: string | null
  assignee_type: 'user' | 'agent' | null
  assignee_name?: string
  due_date: string | null
  tags: string[]
  revision_count: number
  created_at: string
  updated_at: string
}

export interface Folder {
  id: string
  space_id: string
  name: string
  parent_id: string | null
  created_at: string
  updated_at: string
}

export interface Doc {
  id: string
  space_id: string
  folder_id: string | null
  title: string
  content: string
  created_by: string
  created_by_name?: string
  created_at: string
  updated_at: string
}

export const PRIORITY_OPTIONS = {
  urgent: { label: 'Urgent', color: 'bg-danger-light text-danger', dot: 'bg-danger' },
  high: { label: 'High', color: 'bg-warning-light text-warning', dot: 'bg-warning' },
  medium: { label: 'Medium', color: 'bg-accent-100 text-accent-dark', dot: 'bg-accent' },
  low: { label: 'Low', color: 'bg-purple-light text-purple', dot: 'bg-purple' },
  none: { label: 'None', color: 'bg-warm-50 text-warm-500', dot: 'bg-warm-400' },
} as const

export type Priority = keyof typeof PRIORITY_OPTIONS

export interface Agent {
  id: string
  space_id: string
  name: string
  avatar: string
  description: string
  role: string
  provider: string
  model: string
  skill_content: string
  is_active: boolean
  created_by: string
  created_at: string
  updated_at: string
}

export const PIPELINE_ROLES = {
  content_researcher: { label: 'Content Researcher', color: 'bg-blue-50 text-blue-700' },
  topic_validator: { label: 'Topic Validator', color: 'bg-emerald-50 text-emerald-700' },
  content_writer: { label: 'Content Writer', color: 'bg-violet-50 text-violet-700' },
  content_validator: { label: 'Content Validator', color: 'bg-amber-50 text-amber-700' },
} as const

export type PipelineRole = keyof typeof PIPELINE_ROLES

export const PROVIDER_OPTIONS = [
  { id: 'openai', label: 'OpenAI', icon: '🟢' },
  { id: 'gemini', label: 'Gemini', icon: '🔵' },
  { id: 'claude', label: 'Claude', icon: '🟠' },
] as const

export type ProviderId = (typeof PROVIDER_OPTIONS)[number]['id']

export interface Assignee {
  id: string
  name: string
  type: 'user' | 'agent'
  avatar: string | null
}

export interface Mention {
  id: string
  type: 'user' | 'agent'
  name: string
}

export interface Comment {
  id: string
  task_id: string
  content: string
  mentions: Mention[]
  created_by: string
  created_by_name: string
  created_at: string
  updated_at: string
}
