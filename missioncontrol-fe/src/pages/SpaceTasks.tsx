import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { Plus, GripVertical } from 'lucide-react'
import api from '../lib/api'
import type { Task, TaskStatus, Space, Assignee } from '../types'
import { PRIORITY_OPTIONS } from '../types'
import type { Priority } from '../types'
import TaskDetailModal from '../components/TaskDetailModal'

function getInitials(name: string): string {
  return name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2)
}

export default function SpaceTasks() {
  const { spaceId } = useParams<{ spaceId: string }>()
  const [space, setSpace] = useState<Space | null>(null)
  const [statuses, setStatuses] = useState<TaskStatus[]>([])
  const [tasksByStatus, setTasksByStatus] = useState<Record<string, Task[]>>({})
  const [loading, setLoading] = useState(true)
  const [addingToStatus, setAddingToStatus] = useState<string | null>(null)
  const [newTaskTitle, setNewTaskTitle] = useState('')
  const [selectedTask, setSelectedTask] = useState<Task | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [draggedTask, setDraggedTask] = useState<Task | null>(null)
  const [dragOverStatus, setDragOverStatus] = useState<string | null>(null)
  const [assignees, setAssignees] = useState<Assignee[]>([])

  const fetchTasks = useCallback(async () => {
    if (!spaceId) return

    try {
      const [statusesRes, tasksRes, assigneesRes] = await Promise.all([
        api.get(`/api/spaces/${spaceId}/tasks/statuses`),
        api.get(`/api/spaces/${spaceId}/tasks`),
        api.get(`/api/spaces/${spaceId}/tasks/assignees`).catch(() => ({ data: [] })),
      ])

      const fetchedStatuses: TaskStatus[] = statusesRes.data
      const fetchedTasks: Task[] = tasksRes.data

      setStatuses(fetchedStatuses)
      setAssignees(assigneesRes.data as Assignee[])

      const grouped: Record<string, Task[]> = {}
      for (const s of fetchedStatuses) {
        grouped[s.id] = []
      }
      for (const t of fetchedTasks) {
        if (grouped[t.status_id]) {
          grouped[t.status_id].push(t)
        }
      }
      setTasksByStatus(grouped)
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
        // We need to find the space from the spaces list or fetch individually
        // For now, we'll get it from the orgs endpoint
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
    fetchTasks()
  }, [spaceId, fetchTasks])

  const handleAddTask = async (statusId: string) => {
    if (!newTaskTitle.trim() || !spaceId) return

    try {
      await api.post(`/api/spaces/${spaceId}/tasks`, {
        title: newTaskTitle.trim(),
        status_id: statusId,
        priority: 'none',
      })
      setNewTaskTitle('')
      setAddingToStatus(null)
      await fetchTasks()
    } catch {
      // silently handle
    }
  }

  const handleDragStart = (task: Task) => {
    setDraggedTask(task)
  }

  const handleDragOver = (e: React.DragEvent, statusId: string) => {
    e.preventDefault()
    setDragOverStatus(statusId)
  }

  const handleDragLeave = () => {
    setDragOverStatus(null)
  }

  const handleDrop = async (statusId: string) => {
    setDragOverStatus(null)
    if (!draggedTask || !spaceId || draggedTask.status_id === statusId) {
      setDraggedTask(null)
      return
    }

    try {
      await api.put(`/api/spaces/${spaceId}/tasks/${draggedTask.id}/move`, {
        status_id: statusId,
      })
      await fetchTasks()
    } catch {
      // silently handle
    } finally {
      setDraggedTask(null)
    }
  }

  const openTaskDetail = (task: Task) => {
    setSelectedTask(task)
    setDetailOpen(true)
  }

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
        <h1 className="text-xl font-semibold text-warm-900">Board</h1>
      </div>

      {/* Board */}
      <div className="flex-1 flex gap-4 overflow-x-auto pb-4">
        {statuses.map((status) => {
          const tasks = tasksByStatus[status.id] || []

          return (
            <div
              key={status.id}
              className={`flex-shrink-0 w-72 flex flex-col rounded-xl transition-colors ${
                dragOverStatus === status.id ? 'bg-accent-50' : 'bg-surface-sunk'
              }`}
              onDragOver={(e) => handleDragOver(e, status.id)}
              onDragLeave={handleDragLeave}
              onDrop={() => handleDrop(status.id)}
            >
              {/* Column header */}
              <div className="flex items-center justify-between px-3 py-3">
                <div className="flex items-center gap-2">
                  <span
                    className="h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: status.color || '#8A8580' }}
                  />
                  <span className="text-sm font-semibold text-warm-900">{status.name}</span>
                  <span className="text-xs text-warm-400 bg-warm-100 rounded-full px-1.5 py-0.5">
                    {tasks.length}
                  </span>
                </div>
                <button
                  onClick={() => {
                    setAddingToStatus(status.id)
                    setNewTaskTitle('')
                  }}
                  className="p-1 text-warm-400 hover:text-accent hover:bg-accent-50 rounded transition-colors"
                >
                  <Plus className="h-4 w-4" />
                </button>
              </div>

              {/* Inline add form */}
              {addingToStatus === status.id && (
                <div className="px-3 pb-2">
                  <div className="bg-card rounded-xl shadow-e1 p-3">
                    <input
                      type="text"
                      value={newTaskTitle}
                      onChange={(e) => setNewTaskTitle(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleAddTask(status.id)
                        if (e.key === 'Escape') setAddingToStatus(null)
                      }}
                      placeholder="Task name..."
                      className="w-full text-sm text-warm-900 placeholder:text-warm-400 focus:outline-none bg-transparent"
                      autoFocus
                    />
                    <div className="flex justify-end gap-2 mt-2">
                      <button
                        onClick={() => setAddingToStatus(null)}
                        className="px-2 py-1 text-xs text-warm-500 hover:bg-warm-50 rounded transition-colors"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={() => handleAddTask(status.id)}
                        className="px-2 py-1 text-xs text-white bg-lumen rounded"
                      >
                        Add
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* Task cards */}
              <div className="flex-1 px-3 pb-3 space-y-2 overflow-y-auto">
                {tasks.map((task) => {
                  const priorityInfo = PRIORITY_OPTIONS[(task.priority as Priority) || 'none'] || PRIORITY_OPTIONS.none

                  return (
                    <div
                      key={task.id}
                      draggable
                      onDragStart={() => handleDragStart(task)}
                      onClick={() => openTaskDetail(task)}
                      className="bg-card rounded-xl shadow-e1 p-3 cursor-pointer card-hover group"
                    >
                      <div className="flex items-start gap-2">
                        <GripVertical className="h-4 w-4 text-warm-300 opacity-0 group-hover:opacity-100 transition-opacity mt-0.5 shrink-0 cursor-grab" />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-warm-900 truncate">
                            {task.title}
                          </p>

                          <div className="flex items-center gap-2 mt-2">
                            {/* Priority dot */}
                            <span
                              className={`h-2 w-2 rounded-full ${priorityInfo.dot}`}
                              title={priorityInfo.label}
                            />

                            {/* Tags */}
                            {task.tags && task.tags.length > 0 && (
                              <span className="text-[10px] px-1.5 py-0.5 bg-warm-100 text-warm-600 rounded-full truncate max-w-[80px]">
                                {task.tags[0]}
                              </span>
                            )}

                            <div className="flex-1" />

                            {/* Due date */}
                            {task.due_date && (
                              <span className="text-[10px] text-warm-400">
                                {new Date(task.due_date).toLocaleDateString('en-US', {
                                  month: 'short',
                                  day: 'numeric',
                                })}
                              </span>
                            )}

                            {/* Assignee avatar */}
                            {task.assignee_id && (() => {
                              const assignee = assignees.find((a) => a.id === task.assignee_id)
                              const displayName = assignee?.name || task.assignee_name || ''
                              if (!displayName) return null
                              return (
                                <div className="h-5 w-5 rounded-full bg-accent-100 flex items-center justify-center shrink-0" title={displayName}>
                                  {task.assignee_type === 'agent' ? (
                                    <span className="text-[10px]">{assignee?.avatar || '\u{1F916}'}</span>
                                  ) : (
                                    <span className="text-[8px] font-semibold text-accent-dark">
                                      {getInitials(displayName)}
                                    </span>
                                  )}
                                </div>
                              )
                            })()}
                          </div>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )
        })}

        {statuses.length === 0 && (
          <div className="flex-1 flex items-center justify-center py-20">
            <div className="text-center">
              <p className="text-warm-500 text-sm">No task statuses configured for this space.</p>
              <p className="text-warm-400 text-xs mt-1">Statuses will be created when the backend is ready.</p>
            </div>
          </div>
        )}
      </div>

      {/* Task detail modal */}
      <TaskDetailModal
        isOpen={detailOpen}
        onClose={() => setDetailOpen(false)}
        task={selectedTask}
        spaceId={spaceId || ''}
        statuses={statuses}
        onUpdated={fetchTasks}
      />
    </div>
  )
}
