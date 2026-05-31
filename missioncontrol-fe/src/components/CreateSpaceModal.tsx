import { useState } from 'react'
import type { FormEvent } from 'react'
import { X } from 'lucide-react'
import api from '../lib/api'
import { useWorkspace } from '../contexts/WorkspaceContext'

interface CreateSpaceModalProps {
  isOpen: boolean
  onClose: () => void
}

const EMOJI_OPTIONS = ['📁', '🚀', '💼', '🎯', '📊', '🔧', '💡', '🎨', '📝', '🏠', '⭐', '🔥', '🌟', '📌', '🎪', '🏗️', '📐', '🧩']

const COLOR_OPTIONS = [
  '#C4956A', '#5A9A6E', '#D4903C', '#C75B4A', '#8B7EC8',
  '#4A90C7', '#C74A8B', '#6EC79A', '#C7A84A', '#4AC7C7',
]

export default function CreateSpaceModal({ isOpen, onClose }: CreateSpaceModalProps) {
  const { currentOrg, refreshSpaces } = useWorkspace()
  const [name, setName] = useState('')
  const [icon, setIcon] = useState('📁')
  const [color, setColor] = useState('#C4956A')
  const [description, setDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  if (!isOpen) return null

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!currentOrg) return

    setError('')
    setSubmitting(true)

    try {
      await api.post(`/api/orgs/${currentOrg.id}/spaces`, {
        name,
        icon,
        color,
        description,
      })
      await refreshSpaces()
      setName('')
      setIcon('📁')
      setColor('#C4956A')
      setDescription('')
      onClose()
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { detail?: string } } }
        setError(axiosErr.response?.data?.detail || 'Failed to create space')
      } else {
        setError('Failed to create space')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative bg-card rounded-2xl shadow-e3 w-full max-w-md mx-4 p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-semibold text-warm-900">Create Space</h2>
          <button
            onClick={onClose}
            className="p-1 text-warm-400 hover:text-warm-600 rounded"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-danger-light border border-danger/20 text-danger text-sm rounded-lg">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Name */}
          <div>
            <label htmlFor="spaceName" className="block text-sm font-medium text-warm-700 mb-1">
              Name
            </label>
            <input
              id="spaceName"
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 bg-surface-sunk border-0 rounded-lg text-sm text-warm-900 focus:outline-none focus:ring-2 focus:ring-accent/20"
              placeholder="e.g. Marketing, Engineering"
            />
          </div>

          {/* Icon */}
          <div>
            <label className="block text-sm font-medium text-warm-700 mb-2">Icon</label>
            <div className="flex flex-wrap gap-2">
              {EMOJI_OPTIONS.map((emoji) => (
                <button
                  key={emoji}
                  type="button"
                  onClick={() => setIcon(emoji)}
                  className={`h-9 w-9 rounded-lg flex items-center justify-center text-lg transition-colors ${
                    icon === emoji
                      ? 'bg-accent-100 ring-2 ring-accent'
                      : 'bg-warm-50 hover:bg-warm-100'
                  }`}
                >
                  {emoji}
                </button>
              ))}
            </div>
          </div>

          {/* Color */}
          <div>
            <label className="block text-sm font-medium text-warm-700 mb-2">Color</label>
            <div className="flex flex-wrap gap-2">
              {COLOR_OPTIONS.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setColor(c)}
                  className={`h-8 w-8 rounded-full transition-all ${
                    color === c ? 'ring-2 ring-offset-2 ring-accent scale-110' : 'hover:scale-110'
                  }`}
                  style={{ backgroundColor: c }}
                />
              ))}
            </div>
          </div>

          {/* Description */}
          <div>
            <label htmlFor="spaceDesc" className="block text-sm font-medium text-warm-700 mb-1">
              Description
            </label>
            <textarea
              id="spaceDesc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full px-3 py-2 bg-surface-sunk border-0 rounded-lg text-sm text-warm-900 focus:outline-none focus:ring-2 focus:ring-accent/20 resize-none"
              placeholder="What is this space for?"
            />
          </div>

          {/* Actions */}
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
              {submitting ? 'Creating...' : 'Create Space'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
