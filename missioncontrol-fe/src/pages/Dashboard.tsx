import { useState, useEffect } from 'react'
import { useAuth } from '../contexts/AuthContext'
import { useWorkspace } from '../contexts/WorkspaceContext'
import {
  CheckSquare,
  Clock,
  CheckCircle2,
  Layers,
  ArrowRight,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import api from '../lib/api'

function getGreeting(): string {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 17) return 'Good afternoon'
  return 'Good evening'
}

function getFirstName(fullName: string): string {
  return fullName.split(' ')[0]
}

function formatDate(): string {
  return new Date().toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}

interface DashboardStats {
  totalTasks: number
  inProgress: number
  completed: number
}

export default function Dashboard() {
  const { user } = useAuth()
  const { spaces } = useWorkspace()
  const navigate = useNavigate()
  const [stats, setStats] = useState<DashboardStats>({
    totalTasks: 0,
    inProgress: 0,
    completed: 0,
  })

  useEffect(() => {
    const fetchStats = async () => {
      let total = 0
      let inProgress = 0
      let completed = 0

      for (const space of spaces) {
        try {
          const tasksRes = await api.get(`/api/spaces/${space.id}/tasks`)
          const tasks = tasksRes.data as Array<{ status_name?: string }>
          total += tasks.length
          for (const task of tasks) {
            const statusName = (task.status_name || '').toLowerCase()
            if (statusName === 'done' || statusName === 'completed' || statusName === 'complete') {
              completed++
            } else if (statusName === 'in progress' || statusName === 'in_progress') {
              inProgress++
            }
          }
        } catch {
          // skip
        }
      }

      setStats({ totalTasks: total, inProgress, completed })
    }

    if (spaces.length > 0) {
      fetchStats()
    }
  }, [spaces])

  const statCards = [
    {
      label: 'Total Tasks',
      value: stats.totalTasks,
      icon: CheckSquare,
      iconBg: 'bg-accent-100',
      iconColor: 'text-accent',
    },
    {
      label: 'In Progress',
      value: stats.inProgress,
      icon: Clock,
      iconBg: 'bg-warning-light',
      iconColor: 'text-warning',
    },
    {
      label: 'Completed',
      value: stats.completed,
      icon: CheckCircle2,
      iconBg: 'bg-success-light',
      iconColor: 'text-success',
    },
    {
      label: 'Spaces',
      value: spaces.length,
      icon: Layers,
      iconBg: 'bg-purple-light',
      iconColor: 'text-purple',
    },
  ]

  return (
    <div className="max-w-5xl">
      {/* Hero greeting */}
      <div className="bg-aurora-wash rounded-2xl p-8 mb-8">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-3xl font-serif font-bold text-warm-900 mb-1">
              {getGreeting()}, {user ? getFirstName(user.full_name) : 'there'}.
            </h1>
            <p className="text-warm-500 text-sm">{formatDate()}</p>
            {stats.totalTasks > 0 && (
              <p className="text-warm-600 text-sm mt-3">
                {stats.totalTasks} total tasks across {spaces.length} space{spaces.length !== 1 ? 's' : ''}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2 text-xs text-warm-500">
            <span className="h-2 w-2 rounded-full bg-aurora animate-pulse" />
            Live
          </div>
        </div>
        <div className="h-0.5 w-16 bg-aurora/60 rounded-full mt-5" />
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {statCards.map((card) => (
          <div
            key={card.label}
            className="bg-card rounded-xl shadow-e1 p-5"
          >
            <div className="flex items-center justify-between mb-3">
              <div className={`h-10 w-10 rounded-lg ${card.iconBg} flex items-center justify-center`}>
                <card.icon className={`h-5 w-5 ${card.iconColor}`} />
              </div>
            </div>
            <p className="text-2xl font-bold text-warm-900">{card.value}</p>
            <p className="text-sm text-warm-500 mt-0.5">{card.label}</p>
          </div>
        ))}
      </div>

      {/* Your Spaces */}
      <div>
        <h2 className="text-sm font-semibold text-warm-900 mb-4">Your Spaces</h2>
        {spaces.length === 0 ? (
          <div className="bg-card rounded-xl shadow-e1 p-8 text-center">
            <Layers className="h-10 w-10 text-warm-300 mx-auto mb-3" />
            <p className="text-warm-500 text-sm">
              No spaces yet. Create your first space from the sidebar.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {spaces.map((space) => (
              <button
                key={space.id}
                onClick={() => navigate(`/spaces/${space.id}/tasks`)}
                className="bg-card rounded-xl shadow-e1 card-hover p-5 text-left group"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-2xl">{space.icon || '📁'}</span>
                  <ArrowRight className="h-4 w-4 text-warm-300 group-hover:text-accent transition-colors" />
                </div>
                <h3 className="font-semibold text-warm-900 text-sm">{space.name}</h3>
                {space.description && (
                  <p className="text-xs text-warm-500 mt-1 line-clamp-2">{space.description}</p>
                )}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
