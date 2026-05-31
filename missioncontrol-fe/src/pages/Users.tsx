import { useState, useEffect, useCallback } from 'react'
import { Search } from 'lucide-react'
import type { User } from '../contexts/AuthContext'
import api from '../lib/api'
import UserModal from '../components/UserModal'

export default function Users() {
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [modalOpen, setModalOpen] = useState(false)
  const [editingUser, setEditingUser] = useState<User | null>(null)
  const [confirmDeactivate, setConfirmDeactivate] = useState<User | null>(null)
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  const fetchUsers = useCallback(async () => {
    try {
      const params = search ? { search } : {}
      const response = await api.get('/api/users', { params })
      setUsers(response.data)
    } catch {
      // handled silently
    } finally {
      setLoading(false)
    }
  }, [search])

  useEffect(() => {
    setLoading(true)
    const timeout = setTimeout(() => {
      fetchUsers()
    }, 300)
    return () => clearTimeout(timeout)
  }, [fetchUsers])

  const handleCreate = () => {
    setEditingUser(null)
    setModalOpen(true)
  }

  const handleEdit = (user: User) => {
    setEditingUser(user)
    setModalOpen(true)
  }

  const handleSave = async (data: {
    full_name: string
    email: string
    password?: string
    role: 'admin' | 'editor' | 'viewer'
  }) => {
    if (editingUser) {
      await api.put(`/api/users/${editingUser.id}`, data)
    } else {
      await api.post('/api/users', data)
    }
    await fetchUsers()
  }

  const handleToggleActive = async (user: User) => {
    setActionLoading(user.id)
    try {
      if (user.is_active) {
        await api.delete(`/api/users/${user.id}`)
      } else {
        await api.put(`/api/users/${user.id}`, { is_active: true })
      }
      await fetchUsers()
    } catch {
      // handled silently
    } finally {
      setActionLoading(null)
      setConfirmDeactivate(null)
    }
  }

  const roleBadgeColor = (role: string) => {
    switch (role) {
      case 'admin':
        return 'bg-purple-light text-purple'
      case 'editor':
        return 'bg-accent-100 text-accent-dark'
      default:
        return 'bg-warm-100 text-warm-600'
    }
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <p className="text-xs font-medium text-warm-400 uppercase tracking-wider mb-1">Admin</p>
          <h1 className="text-xl font-semibold text-warm-900">Users</h1>
        </div>
        <button
          onClick={handleCreate}
          className="px-4 py-2 text-sm font-medium text-white bg-lumen rounded-lg"
        >
          Add User
        </button>
      </div>

      {/* Search */}
      <div className="mb-4 relative w-full max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-warm-400" />
        <input
          type="text"
          placeholder="Search by name or email..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-10 pr-4 py-2 bg-surface-sunk border-0 rounded-lg text-sm text-warm-900 focus:outline-none focus:ring-2 focus:ring-accent/20"
        />
      </div>

      {/* Table */}
      <div className="bg-card rounded-xl shadow-e1 overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="h-6 w-6 animate-spin rounded-full border-4 border-warm-200 border-t-accent" />
          </div>
        ) : users.length === 0 ? (
          <div className="text-center py-12 text-warm-500 text-sm">
            No users found.
          </div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b border-border bg-warm-50">
                <th className="text-left px-6 py-3 text-xs font-medium text-warm-500 uppercase tracking-wider">
                  Name
                </th>
                <th className="text-left px-6 py-3 text-xs font-medium text-warm-500 uppercase tracking-wider">
                  Email
                </th>
                <th className="text-left px-6 py-3 text-xs font-medium text-warm-500 uppercase tracking-wider">
                  Role
                </th>
                <th className="text-left px-6 py-3 text-xs font-medium text-warm-500 uppercase tracking-wider">
                  Status
                </th>
                <th className="text-right px-6 py-3 text-xs font-medium text-warm-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {users.map((u) => (
                <tr key={u.id} className="hover:bg-warm-50/50">
                  <td className="px-6 py-4 text-sm font-medium text-warm-900">
                    {u.full_name}
                  </td>
                  <td className="px-6 py-4 text-sm text-warm-600">
                    {u.email}
                  </td>
                  <td className="px-6 py-4">
                    <span
                      className={`inline-flex px-2 py-0.5 text-xs font-medium rounded-full capitalize ${roleBadgeColor(u.role)}`}
                    >
                      {u.role}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <span
                      className={`inline-flex px-2 py-0.5 text-xs font-medium rounded-full ${
                        u.is_active
                          ? 'bg-success-light text-success'
                          : 'bg-danger-light text-danger'
                      }`}
                    >
                      {u.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => handleEdit(u)}
                        className="px-3 py-1.5 text-xs font-medium text-warm-700 bg-white border border-border rounded-lg hover:bg-warm-50 transition-colors"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() =>
                          u.is_active
                            ? setConfirmDeactivate(u)
                            : handleToggleActive(u)
                        }
                        disabled={actionLoading === u.id}
                        className={`px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors disabled:opacity-50 ${
                          u.is_active
                            ? 'text-danger border-danger/30 hover:bg-danger-light'
                            : 'text-success border-success/30 hover:bg-success-light'
                        }`}
                      >
                        {actionLoading === u.id
                          ? '...'
                          : u.is_active
                            ? 'Deactivate'
                            : 'Activate'}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* User Modal */}
      <UserModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        user={editingUser}
        onSave={handleSave}
      />

      {/* Deactivate Confirmation */}
      {confirmDeactivate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black/40"
            onClick={() => setConfirmDeactivate(null)}
          />
          <div className="relative bg-card rounded-2xl shadow-e3 w-full max-w-sm mx-4 p-6">
            <h3 className="text-lg font-semibold text-warm-900 mb-2">
              Deactivate User
            </h3>
            <p className="text-sm text-warm-600 mb-6">
              Are you sure you want to deactivate{' '}
              <span className="font-medium">{confirmDeactivate.full_name}</span>?
              They will no longer be able to sign in.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setConfirmDeactivate(null)}
                className="px-4 py-2 text-sm font-medium text-warm-600 bg-warm-50 rounded-lg hover:bg-warm-100 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => handleToggleActive(confirmDeactivate)}
                disabled={actionLoading === confirmDeactivate.id}
                className="px-4 py-2 text-sm font-medium text-white bg-danger rounded-lg hover:bg-danger/90 disabled:opacity-50 transition-colors"
              >
                {actionLoading === confirmDeactivate.id
                  ? 'Deactivating...'
                  : 'Deactivate'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
