import { NavLink, useParams, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard,
  Users,
  Settings,
  Plus,
  LogOut,
  Rocket,
  Columns3,
  FileText,
  Bot,
  ScrollText,
  Search,
  MoreHorizontal,
  Pencil,
  Trash2,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { useWorkspace } from '../contexts/WorkspaceContext'
import { useState, useRef, useEffect } from 'react'
import CreateSpaceModal from './CreateSpaceModal'
import api from '../lib/api'

function getInitials(name: string): string {
  return name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2)
}

function navLinkClasses({ isActive }: { isActive: boolean }): string {
  return `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
    isActive
      ? 'bg-accent-50 text-accent-dark'
      : 'text-warm-600 hover:bg-warm-50 hover:text-warm-900'
  }`
}

export default function Sidebar() {
  const { user, logout } = useAuth()
  const { currentOrg, spaces, refreshSpaces } = useWorkspace()
  const { spaceId } = useParams()
  const navigate = useNavigate()
  const [showCreateSpace, setShowCreateSpace] = useState(false)

  // Space context menu
  const [menuSpaceId, setMenuSpaceId] = useState<string | null>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  // Rename
  const [renamingSpaceId, setRenamingSpaceId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const renameInputRef = useRef<HTMLInputElement>(null)

  // Delete
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)

  // Close menu on outside click
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuSpaceId(null)
      }
    }
    if (menuSpaceId) {
      document.addEventListener('mousedown', handleClick)
    }
    return () => document.removeEventListener('mousedown', handleClick)
  }, [menuSpaceId])

  // Focus rename input
  useEffect(() => {
    if (renamingSpaceId && renameInputRef.current) {
      renameInputRef.current.focus()
      renameInputRef.current.select()
    }
  }, [renamingSpaceId])

  const handleRename = async (id: string) => {
    if (!renameValue.trim() || !currentOrg) return
    try {
      await api.put(`/api/orgs/${currentOrg.id}/spaces/${id}`, {
        name: renameValue.trim(),
      })
      await refreshSpaces()
    } catch {
      // silently handle
    } finally {
      setRenamingSpaceId(null)
    }
  }

  const handleDelete = async (id: string) => {
    if (!currentOrg) return
    setDeleting(true)
    try {
      await api.delete(`/api/orgs/${currentOrg.id}/spaces/${id}`)
      await refreshSpaces()
      // Navigate away if we deleted the active space
      if (spaceId === id) {
        navigate('/')
      }
    } catch {
      // silently handle
    } finally {
      setDeleting(false)
      setConfirmDeleteId(null)
    }
  }

  return (
    <>
      <aside className="w-[260px] min-h-screen bg-card shadow-e1 flex flex-col">
        {/* Logo + Search */}
        <div className="px-4 pt-5 pb-4">
          <div className="flex items-center gap-2.5 mb-4">
            <div className="h-8 w-8 bg-lumen rounded-lg flex items-center justify-center">
              <Rocket className="h-4 w-4 text-white" />
            </div>
            <h1 className="text-lg font-bold text-warm-900 tracking-tight">MissionControl</h1>
          </div>
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-warm-400" />
            <input
              type="text"
              placeholder="Search..."
              className="w-full pl-8 pr-3 py-1.5 bg-surface-sunk border-0 rounded-lg text-xs text-warm-700 placeholder:text-warm-400 focus:outline-none focus:ring-2 focus:ring-accent/20"
            />
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-2 space-y-6 overflow-y-auto">
          {/* Main */}
          <div>
            <NavLink to="/" end className={navLinkClasses}>
              <LayoutDashboard className="h-4.5 w-4.5" />
              Dashboard
            </NavLink>
          </div>

          {/* Workspace section */}
          <div>
            <p className="px-3 mb-2 text-[11px] font-semibold uppercase text-warm-500 tracking-wider">
              Workspace
            </p>
            <div className="space-y-0.5">
              {spaces.map((space) => {
                const isSpaceActive = spaceId === space.id
                return (
                  <div key={space.id} className="relative group/space">
                    {renamingSpaceId === space.id ? (
                      /* Inline rename input */
                      <div className="flex items-center gap-3 px-3 py-2">
                        <span className="text-base leading-none">{space.icon || '\u{1F4C1}'}</span>
                        <input
                          ref={renameInputRef}
                          type="text"
                          value={renameValue}
                          onChange={(e) => setRenameValue(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') handleRename(space.id)
                            if (e.key === 'Escape') setRenamingSpaceId(null)
                          }}
                          onBlur={() => handleRename(space.id)}
                          className="flex-1 min-w-0 px-2 py-0.5 bg-surface-sunk border-0 rounded text-sm text-warm-900 focus:outline-none focus:ring-2 focus:ring-accent/20"
                        />
                      </div>
                    ) : (
                      /* Space nav link + menu trigger */
                      <div className="flex items-center">
                        <NavLink
                          to={`/spaces/${space.id}/tasks`}
                          className={() =>
                            `flex-1 flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                              isSpaceActive
                                ? 'bg-accent-50 text-accent-dark'
                                : 'text-warm-600 hover:bg-warm-50 hover:text-warm-900'
                            }`
                          }
                        >
                          <span className="text-base leading-none">{space.icon || '\u{1F4C1}'}</span>
                          <span className="truncate">{space.name}</span>
                        </NavLink>

                        {/* More menu trigger */}
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            setMenuSpaceId(menuSpaceId === space.id ? null : space.id)
                          }}
                          className="p-1 mr-1 text-warm-400 hover:text-warm-700 hover:bg-warm-100 rounded opacity-0 group-hover/space:opacity-100 transition-all"
                        >
                          <MoreHorizontal className="h-4 w-4" />
                        </button>
                      </div>
                    )}

                    {/* Dropdown menu */}
                    {menuSpaceId === space.id && (
                      <div
                        ref={menuRef}
                        className="absolute left-4 top-full z-50 mt-1 w-40 bg-card rounded-xl shadow-e3 py-1.5"
                      >
                        <button
                          onClick={() => {
                            setMenuSpaceId(null)
                            setRenameValue(space.name)
                            setRenamingSpaceId(space.id)
                          }}
                          className="flex items-center gap-2.5 w-full px-3 py-2 text-sm text-warm-700 hover:bg-warm-50 transition-colors"
                        >
                          <Pencil className="h-3.5 w-3.5" />
                          Rename
                        </button>
                        <button
                          onClick={() => {
                            setMenuSpaceId(null)
                            setConfirmDeleteId(space.id)
                          }}
                          className="flex items-center gap-2.5 w-full px-3 py-2 text-sm text-danger hover:bg-danger-light transition-colors"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                          Delete
                        </button>
                      </div>
                    )}

                    {/* Sub-navigation for active space */}
                    {isSpaceActive && (
                      <div className="ml-7 mt-0.5 space-y-0.5">
                        <NavLink
                          to={`/spaces/${space.id}/tasks`}
                          end
                          className={({ isActive }) =>
                            `flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                              isActive
                                ? 'text-accent-dark bg-accent-50/60'
                                : 'text-warm-500 hover:text-warm-700 hover:bg-warm-50'
                            }`
                          }
                        >
                          <Columns3 className="h-3.5 w-3.5" />
                          Board
                        </NavLink>
                        <NavLink
                          to={`/spaces/${space.id}/docs`}
                          className={({ isActive }) =>
                            `flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                              isActive
                                ? 'text-accent-dark bg-accent-50/60'
                                : 'text-warm-500 hover:text-warm-700 hover:bg-warm-50'
                            }`
                          }
                        >
                          <FileText className="h-3.5 w-3.5" />
                          Docs
                        </NavLink>
                        <NavLink
                          to={`/spaces/${space.id}/agents`}
                          className={({ isActive }) =>
                            `flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                              isActive
                                ? 'text-accent-dark bg-accent-50/60'
                                : 'text-warm-500 hover:text-warm-700 hover:bg-warm-50'
                            }`
                          }
                        >
                          <Bot className="h-3.5 w-3.5" />
                          Agents
                        </NavLink>
                        <NavLink
                          to={`/spaces/${space.id}/logs`}
                          className={({ isActive }) =>
                            `flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                              isActive
                                ? 'text-accent-dark bg-accent-50/60'
                                : 'text-warm-500 hover:text-warm-700 hover:bg-warm-50'
                            }`
                          }
                        >
                          <ScrollText className="h-3.5 w-3.5" />
                          Logs
                        </NavLink>
                      </div>
                    )}
                  </div>
                )
              })}

              <button
                onClick={() => setShowCreateSpace(true)}
                className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium text-warm-400 hover:text-accent hover:bg-warm-50 transition-colors w-full"
              >
                <Plus className="h-4 w-4" />
                New Space
              </button>
            </div>
          </div>

          {/* Admin section */}
          {user?.role === 'admin' && (
            <div>
              <p className="px-3 mb-2 text-[11px] font-semibold uppercase text-warm-500 tracking-wider">
                Admin
              </p>
              <div className="space-y-0.5">
                <NavLink to="/users" className={navLinkClasses}>
                  <Users className="h-4.5 w-4.5" />
                  Users
                </NavLink>
                <NavLink to="/settings" className={navLinkClasses}>
                  <Settings className="h-4.5 w-4.5" />
                  Settings
                </NavLink>
              </div>
            </div>
          )}
        </nav>

        {/* User info at bottom */}
        {user && (
          <div className="px-3 py-4 border-t border-border">
            <div className="flex items-center gap-3">
              <div className="h-9 w-9 rounded-full bg-accent-100 flex items-center justify-center shrink-0">
                <span className="text-xs font-semibold text-accent-dark">
                  {getInitials(user.full_name)}
                </span>
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-warm-900 truncate">{user.full_name}</p>
                <p className="text-xs text-warm-500 capitalize">{user.role}</p>
              </div>
              <button
                onClick={logout}
                className="p-2 text-warm-400 hover:text-danger hover:bg-danger-light rounded-lg transition-colors"
                title="Sign out"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}
      </aside>

      <CreateSpaceModal
        isOpen={showCreateSpace}
        onClose={() => setShowCreateSpace(false)}
      />

      {/* Delete space confirmation */}
      {confirmDeleteId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black/40"
            onClick={() => setConfirmDeleteId(null)}
          />
          <div className="relative bg-card rounded-2xl shadow-e3 w-full max-w-sm mx-4 p-6">
            <h3 className="text-lg font-semibold text-warm-900 mb-2">Delete Space</h3>
            <p className="text-sm text-warm-600 mb-1">
              Are you sure you want to delete{' '}
              <span className="font-medium">
                {spaces.find((s) => s.id === confirmDeleteId)?.name}
              </span>
              ?
            </p>
            <p className="text-xs text-warm-400 mb-6">
              All tasks, documents, and agents in this space will be permanently removed.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setConfirmDeleteId(null)}
                className="px-4 py-2 text-sm font-medium text-warm-600 bg-warm-50 rounded-lg hover:bg-warm-100 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDelete(confirmDeleteId)}
                disabled={deleting}
                className="px-4 py-2 text-sm font-medium text-white bg-danger rounded-lg hover:bg-danger/90 disabled:opacity-50 transition-colors"
              >
                {deleting ? 'Deleting...' : 'Delete Space'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
