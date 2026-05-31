import { Search, Bell } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

function getInitials(name: string): string {
  return name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2)
}

export default function TopBar() {
  const { user } = useAuth()

  return (
    <div className="h-16 border-b border-border bg-card flex items-center justify-between px-6">
      {/* Search */}
      <div className="relative w-80">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-warm-400" />
        <input
          type="text"
          placeholder="Search tasks, docs..."
          className="w-full pl-10 pr-4 py-2 bg-warm-50 border border-border rounded-lg text-sm text-warm-900 placeholder:text-warm-400 focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent"
        />
      </div>

      {/* Right side */}
      <div className="flex items-center gap-4">
        {/* Notifications */}
        <button className="relative p-2 text-warm-500 hover:bg-warm-50 rounded-lg transition-colors">
          <Bell className="h-5 w-5" />
          <span className="absolute top-1.5 right-1.5 h-2 w-2 bg-danger rounded-full" />
        </button>

        {/* User avatar */}
        {user && (
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-full bg-accent-100 flex items-center justify-center">
              <span className="text-xs font-semibold text-accent-dark">
                {getInitials(user.full_name)}
              </span>
            </div>
            <span className="text-sm font-medium text-warm-900">{user.full_name}</span>
          </div>
        )}
      </div>
    </div>
  )
}
