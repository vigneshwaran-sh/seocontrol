import { useState, useEffect } from 'react'
import type { FormEvent } from 'react'
import { X } from 'lucide-react'
import type { User } from '../contexts/AuthContext'

interface UserModalProps {
  isOpen: boolean
  onClose: () => void
  user?: User | null
  onSave: (data: {
    full_name: string
    email: string
    password?: string
    role: 'admin' | 'editor' | 'viewer'
  }) => Promise<void>
}

export default function UserModal({ isOpen, onClose, user, onSave }: UserModalProps) {
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<'admin' | 'editor' | 'viewer'>('viewer')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const isEdit = !!user

  useEffect(() => {
    if (user) {
      setFullName(user.full_name)
      setEmail(user.email)
      setRole(user.role)
      setPassword('')
    } else {
      setFullName('')
      setEmail('')
      setPassword('')
      setRole('viewer')
    }
    setError('')
  }, [user, isOpen])

  if (!isOpen) return null

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)

    try {
      const data: { full_name: string; email: string; password?: string; role: 'admin' | 'editor' | 'viewer' } = {
        full_name: fullName,
        email,
        role,
      }
      if (!isEdit) {
        data.password = password
      }
      await onSave(data)
      onClose()
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { detail?: string } } }
        setError(axiosErr.response?.data?.detail || 'An error occurred')
      } else {
        setError('An error occurred')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />

      {/* Modal */}
      <div className="relative bg-card rounded-2xl shadow-e3 w-full max-w-md mx-4 p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-semibold text-warm-900">
            {isEdit ? 'Edit User' : 'Add User'}
          </h2>
          <button
            onClick={onClose}
            className="p-1 text-warm-400 hover:text-warm-600 rounded"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Error */}
        {error && (
          <div className="mb-4 p-3 bg-danger-light border border-danger/20 text-danger text-sm rounded-lg">
            {error}
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="fullName" className="block text-sm font-medium text-warm-700 mb-1">
              Full Name
            </label>
            <input
              id="fullName"
              type="text"
              required
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="w-full px-3 py-2 bg-surface-sunk border-0 rounded-lg text-sm text-warm-900 focus:outline-none focus:ring-2 focus:ring-accent/20"
              placeholder="John Doe"
            />
          </div>

          <div>
            <label htmlFor="email" className="block text-sm font-medium text-warm-700 mb-1">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-3 py-2 bg-surface-sunk border-0 rounded-lg text-sm text-warm-900 focus:outline-none focus:ring-2 focus:ring-accent/20"
              placeholder="john@example.com"
            />
          </div>

          {!isEdit && (
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-warm-700 mb-1">
                Password
              </label>
              <input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-3 py-2 bg-surface-sunk border-0 rounded-lg text-sm text-warm-900 focus:outline-none focus:ring-2 focus:ring-accent/20"
                placeholder="Enter password"
              />
            </div>
          )}

          <div>
            <label htmlFor="role" className="block text-sm font-medium text-warm-700 mb-1">
              Role
            </label>
            <select
              id="role"
              value={role}
              onChange={(e) => setRole(e.target.value as 'admin' | 'editor' | 'viewer')}
              className="w-full px-3 py-2 bg-surface-sunk border-0 rounded-lg text-sm text-warm-900 focus:outline-none focus:ring-2 focus:ring-accent/20"
            >
              <option value="viewer">Viewer</option>
              <option value="editor">Editor</option>
              <option value="admin">Admin</option>
            </select>
          </div>

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
              disabled={submitting}
              className="px-4 py-2 text-sm font-medium text-white bg-lumen rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {submitting
                ? 'Saving...'
                : isEdit
                  ? 'Update User'
                  : 'Create User'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
