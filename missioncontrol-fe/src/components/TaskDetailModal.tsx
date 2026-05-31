import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import type { FormEvent } from 'react'
import { X, Trash2, Send, MessageSquare, Bot, User } from 'lucide-react'
import api from '../lib/api'
import type { Task, TaskStatus, Assignee, Comment, Mention } from '../types'
import { PRIORITY_OPTIONS } from '../types'
import type { Priority } from '../types'
import { useAuth } from '../contexts/AuthContext'

interface TaskDetailModalProps {
  isOpen: boolean
  onClose: () => void
  task: Task | null
  spaceId: string
  statuses: TaskStatus[]
  onUpdated: () => void
}

export default function TaskDetailModal({
  isOpen,
  onClose,
  task,
  spaceId,
  statuses,
  onUpdated,
}: TaskDetailModalProps) {
  const { user: currentUser } = useAuth()

  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [statusId, setStatusId] = useState('')
  const [priority, setPriority] = useState<Priority>('none')
  const [assigneeId, setAssigneeId] = useState('')
  const [assigneeType, setAssigneeType] = useState<'user' | 'agent' | ''>('')
  const [dueDate, setDueDate] = useState('')
  const [tagsInput, setTagsInput] = useState('')
  const [assignees, setAssignees] = useState<Assignee[]>([])
  const [saving, setSaving] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)

  // Comments state
  const [comments, setComments] = useState<Comment[]>([])
  const [commentsLoading, setCommentsLoading] = useState(false)
  const [commentText, setCommentText] = useState('')
  const [mentions, setMentions] = useState<Mention[]>([])
  const [posting, setPosting] = useState(false)
  const [deletingCommentId, setDeletingCommentId] = useState<string | null>(null)

  // @mention dropdown state
  const [mentionOpen, setMentionOpen] = useState(false)
  const [mentionQuery, setMentionQuery] = useState('')
  const [mentionIndex, setMentionIndex] = useState(0)
  const [cursorPos, setCursorPos] = useState(0)
  const commentInputRef = useRef<HTMLTextAreaElement>(null)
  const mentionDropdownRef = useRef<HTMLDivElement>(null)
  const commentsEndRef = useRef<HTMLDivElement>(null)

  const fetchAssignees = useCallback(async () => {
    try {
      const response = await api.get(`/api/spaces/${spaceId}/tasks/assignees`)
      setAssignees(response.data)
    } catch {
      // silently handle
    }
  }, [spaceId])

  const fetchComments = useCallback(async () => {
    if (!task) return
    setCommentsLoading(true)
    try {
      const response = await api.get(
        `/api/spaces/${spaceId}/tasks/${task.id}/comments`
      )
      setComments(response.data)
    } catch {
      // silently handle
    } finally {
      setCommentsLoading(false)
    }
  }, [spaceId, task])

  useEffect(() => {
    if (isOpen && task) {
      setTitle(task.title)
      setDescription(task.description || '')
      setStatusId(task.status_id)
      setPriority((task.priority as Priority) || 'none')
      setAssigneeId(task.assignee_id || '')
      setAssigneeType(task.assignee_type || '')
      setDueDate(task.due_date || '')
      setTagsInput((task.tags || []).join(', '))
      setConfirmDelete(false)
      setCommentText('')
      setMentions([])
      setMentionOpen(false)
      fetchAssignees()
      fetchComments()
    }
  }, [isOpen, task, fetchAssignees, fetchComments])

  // Auto-scroll to newest comment
  useEffect(() => {
    if (commentsEndRef.current) {
      commentsEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [comments])

  // Filtered mention candidates
  const mentionCandidates = useMemo(() => {
    if (!mentionQuery) return assignees
    const q = mentionQuery.toLowerCase()
    return assignees.filter((a) => a.name.toLowerCase().includes(q))
  }, [assignees, mentionQuery])

  // ─── @mention input handling ───────────────────────────────────

  const handleCommentChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value
    const pos = e.target.selectionStart || 0
    setCommentText(value)
    setCursorPos(pos)

    // Detect @mention trigger
    const textBeforeCursor = value.slice(0, pos)
    const atMatch = textBeforeCursor.match(/@(\w*)$/)
    if (atMatch) {
      setMentionQuery(atMatch[1])
      setMentionOpen(true)
      setMentionIndex(0)
    } else {
      setMentionOpen(false)
      setMentionQuery('')
    }
  }

  const handleCommentKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (mentionOpen && mentionCandidates.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setMentionIndex((prev) => Math.min(prev + 1, mentionCandidates.length - 1))
        return
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setMentionIndex((prev) => Math.max(prev - 1, 0))
        return
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault()
        insertMention(mentionCandidates[mentionIndex])
        return
      }
      if (e.key === 'Escape') {
        e.preventDefault()
        setMentionOpen(false)
        return
      }
    }

    // Submit with Cmd/Ctrl+Enter
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault()
      handlePostComment()
    }
  }

  const insertMention = (assignee: Assignee) => {
    const textBeforeCursor = commentText.slice(0, cursorPos)
    const textAfterCursor = commentText.slice(cursorPos)

    // Replace the @query with @name
    const beforeAt = textBeforeCursor.replace(/@(\w*)$/, '')
    const mentionText = `@${assignee.name} `
    const newText = beforeAt + mentionText + textAfterCursor

    setCommentText(newText)
    setMentionOpen(false)
    setMentionQuery('')

    // Track the mention
    if (!mentions.find((m) => m.id === assignee.id)) {
      setMentions((prev) => [
        ...prev,
        { id: assignee.id, type: assignee.type, name: assignee.name },
      ])
    }

    // Focus back and place cursor after mention
    setTimeout(() => {
      if (commentInputRef.current) {
        const newPos = beforeAt.length + mentionText.length
        commentInputRef.current.focus()
        commentInputRef.current.setSelectionRange(newPos, newPos)
      }
    }, 0)
  }

  // ─── Comment CRUD ──────────────────────────────────────────────

  const handlePostComment = async () => {
    if (!commentText.trim() || !task) return
    setPosting(true)
    try {
      // Extract mentions that are actually present in the text
      const activeMentions = mentions.filter((m) =>
        commentText.includes(`@${m.name}`)
      )
      await api.post(`/api/spaces/${spaceId}/tasks/${task.id}/comments`, {
        content: commentText.trim(),
        mentions: activeMentions,
      })
      setCommentText('')
      setMentions([])
      await fetchComments()
    } catch {
      // silently handle
    } finally {
      setPosting(false)
    }
  }

  const handleDeleteComment = async (commentId: string) => {
    if (!task) return
    setDeletingCommentId(commentId)
    try {
      await api.delete(
        `/api/spaces/${spaceId}/tasks/${task.id}/comments/${commentId}`
      )
      await fetchComments()
    } catch {
      // silently handle
    } finally {
      setDeletingCommentId(null)
    }
  }

  if (!isOpen || !task) return null

  const handleSave = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      const tags = tagsInput
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean)
      await api.put(`/api/spaces/${spaceId}/tasks/${task.id}`, {
        title,
        description,
        status_id: statusId,
        priority,
        assignee_id: assigneeId || null,
        assignee_type: assigneeType || null,
        due_date: dueDate || null,
        tags,
      })
      onUpdated()
      onClose()
    } catch {
      // silently handle
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    setDeleting(true)
    try {
      await api.delete(`/api/spaces/${spaceId}/tasks/${task.id}`)
      onUpdated()
      onClose()
    } catch {
      // silently handle
    } finally {
      setDeleting(false)
    }
  }

  const priorityKeys = Object.keys(PRIORITY_OPTIONS) as Priority[]

  // Turn plain text into React nodes with clickable links
  const linkifyText = (text: string, keyPrefix: string): React.ReactNode[] => {
    const urlRegex = /(https?:\/\/[^\s)<>]+)/g
    const nodes: React.ReactNode[] = []
    let last = 0
    let match: RegExpExecArray | null

    while ((match = urlRegex.exec(text)) !== null) {
      if (match.index > last) {
        nodes.push(<span key={`${keyPrefix}-t-${last}`}>{text.slice(last, match.index)}</span>)
      }
      nodes.push(
        <a
          key={`${keyPrefix}-a-${match.index}`}
          href={match[1]}
          target="_blank"
          rel="noopener noreferrer"
          className="text-accent underline hover:text-accent-dark break-all"
        >
          {match[1]}
        </a>
      )
      last = match.index + match[0].length
    }

    if (last < text.length) {
      nodes.push(<span key={`${keyPrefix}-t-${last}`}>{text.slice(last)}</span>)
    }

    return nodes
  }

  // Render comment content with highlighted @mentions and clickable links
  const renderCommentContent = (comment: Comment) => {
    if (!comment.mentions || comment.mentions.length === 0) {
      return <>{linkifyText(comment.content, 'c')}</>
    }

    let content = comment.content
    const parts: React.ReactNode[] = []
    let lastIndex = 0

    // Find all @mentions in the text and highlight them
    const sortedMentions = [...comment.mentions].sort((a, b) => {
      const idxA = content.indexOf(`@${a.name}`)
      const idxB = content.indexOf(`@${b.name}`)
      return idxA - idxB
    })

    for (const mention of sortedMentions) {
      const mentionText = `@${mention.name}`
      const idx = content.indexOf(mentionText, lastIndex)
      if (idx === -1) continue

      // Text before mention (with linkified URLs)
      if (idx > lastIndex) {
        parts.push(...linkifyText(content.slice(lastIndex, idx), `t-${lastIndex}`))
      }

      // Mention badge
      parts.push(
        <span
          key={`m-${mention.id}-${idx}`}
          className={`inline-flex items-center gap-0.5 px-1 py-0.5 rounded text-xs font-medium ${
            mention.type === 'agent'
              ? 'bg-purple-light text-purple'
              : 'bg-accent-50 text-accent-dark'
          }`}
        >
          {mention.type === 'agent' ? (
            <Bot className="h-3 w-3" />
          ) : (
            <User className="h-3 w-3" />
          )}
          {mention.name}
        </span>
      )

      lastIndex = idx + mentionText.length
    }

    // Remaining text after last mention (with linkified URLs)
    if (lastIndex < content.length) {
      parts.push(...linkifyText(content.slice(lastIndex), `t-${lastIndex}`))
    }

    return <>{parts}</>
  }

  const formatTime = (dateStr: string) => {
    // DB stores UTC — ensure JS parses it as UTC by appending Z if missing
    const utcStr = dateStr.endsWith('Z') || dateStr.includes('+') ? dateStr : dateStr + 'Z'
    const d = new Date(utcStr)

    const tz = 'Asia/Kolkata'

    // Get IST date parts for today/yesterday comparison
    const istParts = new Intl.DateTimeFormat('en-IN', {
      timeZone: tz,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).formatToParts(d)
    const istDay = Number(istParts.find(p => p.type === 'day')?.value)
    const istMonth = Number(istParts.find(p => p.type === 'month')?.value)
    const istYear = Number(istParts.find(p => p.type === 'year')?.value)

    const nowParts = new Intl.DateTimeFormat('en-IN', {
      timeZone: tz,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).formatToParts(new Date())
    const nowDay = Number(nowParts.find(p => p.type === 'day')?.value)
    const nowMonth = Number(nowParts.find(p => p.type === 'month')?.value)
    const nowYear = Number(nowParts.find(p => p.type === 'year')?.value)

    const isToday = istDay === nowDay && istMonth === nowMonth && istYear === nowYear

    const yesterday = new Date()
    yesterday.setDate(yesterday.getDate() - 1)
    const yParts = new Intl.DateTimeFormat('en-IN', {
      timeZone: tz,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).formatToParts(yesterday)
    const yDay = Number(yParts.find(p => p.type === 'day')?.value)
    const yMonth = Number(yParts.find(p => p.type === 'month')?.value)
    const yYear = Number(yParts.find(p => p.type === 'year')?.value)
    const isYesterday = istDay === yDay && istMonth === yMonth && istYear === yYear

    const time = d.toLocaleTimeString('en-IN', {
      timeZone: tz,
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    })

    if (isToday) return `Today ${time}`
    if (isYesterday) return `Yesterday ${time}`

    const monthName = d.toLocaleString('en-IN', { timeZone: tz, month: 'short' })
    return `${istDay} ${monthName} ${istYear} ${time}`
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative bg-card rounded-2xl shadow-e3 w-full max-w-2xl mx-4 max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-6 pb-0 shrink-0">
          <h2 className="text-lg font-semibold text-warm-900">Task Details</h2>
          <button
            onClick={onClose}
            className="p-1 text-warm-400 hover:text-warm-600 rounded"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto">
          <form onSubmit={handleSave} className="p-6 space-y-4">
            {/* Title */}
            <div>
              <label htmlFor="taskTitle" className="block text-sm font-medium text-warm-700 mb-1">
                Title
              </label>
              <input
                id="taskTitle"
                type="text"
                required
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="w-full px-3 py-2 bg-surface-sunk border-0 rounded-lg text-sm text-warm-900 focus:outline-none focus:ring-2 focus:ring-accent/20"
              />
            </div>

            {/* Status + Priority row */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label htmlFor="taskStatus" className="block text-sm font-medium text-warm-700 mb-1">
                  Status
                </label>
                <select
                  id="taskStatus"
                  value={statusId}
                  onChange={(e) => setStatusId(e.target.value)}
                  className="w-full px-3 py-2 bg-surface-sunk border-0 rounded-lg text-sm text-warm-900 focus:outline-none focus:ring-2 focus:ring-accent/20"
                >
                  {statuses.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="taskPriority" className="block text-sm font-medium text-warm-700 mb-1">
                  Priority
                </label>
                <select
                  id="taskPriority"
                  value={priority}
                  onChange={(e) => setPriority(e.target.value as Priority)}
                  className="w-full px-3 py-2 bg-surface-sunk border-0 rounded-lg text-sm text-warm-900 focus:outline-none focus:ring-2 focus:ring-accent/20"
                >
                  {priorityKeys.map((p) => (
                    <option key={p} value={p}>
                      {PRIORITY_OPTIONS[p].label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Assignee + Due date row */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label htmlFor="taskAssignee" className="block text-sm font-medium text-warm-700 mb-1">
                  Assignee
                </label>
                <select
                  id="taskAssignee"
                  value={assigneeId}
                  onChange={(e) => {
                    const selectedId = e.target.value
                    setAssigneeId(selectedId)
                    if (!selectedId) {
                      setAssigneeType('')
                    } else {
                      const found = assignees.find((a) => a.id === selectedId)
                      setAssigneeType(found?.type || '')
                    }
                  }}
                  className="w-full px-3 py-2 bg-surface-sunk border-0 rounded-lg text-sm text-warm-900 focus:outline-none focus:ring-2 focus:ring-accent/20"
                >
                  <option value="">Unassigned</option>
                  {assignees.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.type === 'agent' ? '\u{1F916} ' : '\u{1F464} '}{a.name} ({a.type})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="taskDue" className="block text-sm font-medium text-warm-700 mb-1">
                  Due Date
                </label>
                <input
                  id="taskDue"
                  type="date"
                  value={dueDate}
                  onChange={(e) => setDueDate(e.target.value)}
                  className="w-full px-3 py-2 bg-surface-sunk border-0 rounded-lg text-sm text-warm-900 focus:outline-none focus:ring-2 focus:ring-accent/20"
                />
              </div>
            </div>

            {/* Tags */}
            <div>
              <label htmlFor="taskTags" className="block text-sm font-medium text-warm-700 mb-1">
                Tags
              </label>
              <input
                id="taskTags"
                type="text"
                value={tagsInput}
                onChange={(e) => setTagsInput(e.target.value)}
                placeholder="Comma-separated tags"
                className="w-full px-3 py-2 bg-surface-sunk border-0 rounded-lg text-sm text-warm-900 focus:outline-none focus:ring-2 focus:ring-accent/20"
              />
            </div>

            {/* Revision count */}
            {task && task.revision_count > 0 && (
              <div className="flex items-center gap-2 px-3 py-2 bg-amber-50 border border-amber-200 rounded-lg">
                <span className="text-sm text-amber-800">
                  Revisions: <span className="font-semibold">{task.revision_count}/5</span>
                </span>
                {task.revision_count >= 5 && (
                  <span className="text-xs bg-amber-200 text-amber-900 px-1.5 py-0.5 rounded font-medium">
                    Escalated
                  </span>
                )}
              </div>
            )}

            {/* Description */}
            <div>
              <label htmlFor="taskDesc" className="block text-sm font-medium text-warm-700 mb-1">
                Description
              </label>
              <textarea
                id="taskDesc"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
                className="w-full px-3 py-2 bg-surface-sunk border-0 rounded-lg text-sm text-warm-900 focus:outline-none focus:ring-2 focus:ring-accent/20 resize-none"
                placeholder="Add a description..."
              />
            </div>

            {/* Actions */}
            <div className="flex items-center justify-between pt-2">
              <div>
                {!confirmDelete ? (
                  <button
                    type="button"
                    onClick={() => setConfirmDelete(true)}
                    className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-danger hover:bg-danger-light rounded-lg transition-colors"
                  >
                    <Trash2 className="h-4 w-4" />
                    Delete
                  </button>
                ) : (
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={handleDelete}
                      disabled={deleting}
                      className="px-3 py-2 text-sm font-medium text-white bg-danger rounded-lg hover:bg-danger/90 disabled:opacity-50 transition-colors"
                    >
                      {deleting ? 'Deleting...' : 'Confirm Delete'}
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirmDelete(false)}
                      className="px-3 py-2 text-sm font-medium text-warm-500 hover:bg-warm-50 rounded-lg transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                )}
              </div>
              <div className="flex gap-3">
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
                  {saving ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </div>
          </form>

          {/* ─── Comments Section ────────────────────────────────── */}
          <div className="px-6 pb-6">
            <div className="border-t border-border pt-5">
              <div className="flex items-center gap-2 mb-4">
                <MessageSquare className="h-4 w-4 text-warm-500" />
                <h3 className="text-sm font-semibold text-warm-900">
                  Comments
                  {comments.length > 0 && (
                    <span className="ml-1.5 text-xs font-normal text-warm-400">
                      ({comments.length})
                    </span>
                  )}
                </h3>
              </div>

              {/* Comment list */}
              {commentsLoading ? (
                <div className="flex items-center justify-center py-6">
                  <div className="h-5 w-5 animate-spin rounded-full border-2 border-warm-200 border-t-accent" />
                </div>
              ) : comments.length > 0 ? (
                <div className="space-y-3 mb-4 max-h-64 overflow-y-auto">
                  {comments.map((comment) => (
                    <div
                      key={comment.id}
                      className="group bg-surface-sunk rounded-lg p-3"
                    >
                      <div className="flex items-center justify-between mb-1">
                        <div className="flex items-center gap-2">
                          <div className="h-6 w-6 rounded-full bg-accent-100 flex items-center justify-center">
                            <span className="text-[10px] font-bold text-accent-dark">
                              {comment.created_by_name
                                .split(' ')
                                .map((n) => n[0])
                                .join('')
                                .slice(0, 2)
                                .toUpperCase()}
                            </span>
                          </div>
                          <span className="text-xs font-semibold text-warm-800">
                            {comment.created_by_name}
                          </span>
                          <span className="text-[10px] text-warm-400">
                            {formatTime(comment.created_at)}
                          </span>
                        </div>

                        {/* Delete button — own comments or admin */}
                        {currentUser &&
                          (comment.created_by === currentUser.id ||
                            currentUser.role === 'admin') && (
                            <button
                              type="button"
                              onClick={() => handleDeleteComment(comment.id)}
                              disabled={deletingCommentId === comment.id}
                              className="p-1 text-warm-300 hover:text-danger rounded opacity-0 group-hover:opacity-100 transition-all disabled:opacity-50"
                              title="Delete comment"
                            >
                              <Trash2 className="h-3 w-3" />
                            </button>
                          )}
                      </div>

                      <p className="text-sm text-warm-700 whitespace-pre-wrap leading-relaxed">
                        {renderCommentContent(comment)}
                      </p>
                    </div>
                  ))}
                  <div ref={commentsEndRef} />
                </div>
              ) : (
                <p className="text-xs text-warm-400 mb-4">
                  No comments yet. Be the first to add one.
                </p>
              )}

              {/* New comment input */}
              <div className="relative">
                <textarea
                  ref={commentInputRef}
                  value={commentText}
                  onChange={handleCommentChange}
                  onKeyDown={handleCommentKeyDown}
                  rows={2}
                  placeholder="Add a comment... Type @ to mention someone"
                  className="w-full px-3 py-2 pr-10 bg-surface-sunk border-0 rounded-lg text-sm text-warm-900 focus:outline-none focus:ring-2 focus:ring-accent/20 resize-none"
                />

                {/* Send button */}
                <button
                  type="button"
                  onClick={handlePostComment}
                  disabled={posting || !commentText.trim()}
                  className="absolute right-2 bottom-2 p-1.5 text-accent hover:text-accent-dark disabled:text-warm-300 disabled:cursor-not-allowed transition-colors rounded-lg hover:bg-accent-50"
                  title="Post comment (Ctrl+Enter)"
                >
                  <Send className="h-4 w-4" />
                </button>

                {/* @mention dropdown */}
                {mentionOpen && mentionCandidates.length > 0 && (
                  <div
                    ref={mentionDropdownRef}
                    className="absolute bottom-full mb-1 left-0 w-full bg-card rounded-lg shadow-e2 border border-border max-h-40 overflow-auto z-20"
                  >
                    {mentionCandidates.map((a, i) => (
                      <button
                        key={a.id}
                        type="button"
                        onClick={() => insertMention(a)}
                        className={`w-full text-left px-3 py-2 text-sm flex items-center gap-2.5 transition-colors ${
                          i === mentionIndex
                            ? 'bg-accent-50 text-accent-dark'
                            : 'text-warm-700 hover:bg-warm-50'
                        }`}
                      >
                        {a.type === 'agent' ? (
                          <span className="h-6 w-6 rounded-full bg-purple-light flex items-center justify-center shrink-0">
                            <Bot className="h-3.5 w-3.5 text-purple" />
                          </span>
                        ) : (
                          <span className="h-6 w-6 rounded-full bg-accent-100 flex items-center justify-center shrink-0">
                            <User className="h-3.5 w-3.5 text-accent-dark" />
                          </span>
                        )}
                        <span className="font-medium truncate">{a.name}</span>
                        <span className="text-[10px] text-warm-400 ml-auto shrink-0">
                          {a.type}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Mention hint */}
              {mentions.length > 0 && (
                <div className="flex items-center gap-1.5 mt-2 flex-wrap">
                  <span className="text-[10px] text-warm-400">Mentioning:</span>
                  {mentions
                    .filter((m) => commentText.includes(`@${m.name}`))
                    .map((m) => (
                      <span
                        key={m.id}
                        className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium ${
                          m.type === 'agent'
                            ? 'bg-purple-light text-purple'
                            : 'bg-accent-50 text-accent-dark'
                        }`}
                      >
                        {m.type === 'agent' ? '🤖' : '👤'} {m.name}
                      </span>
                    ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
