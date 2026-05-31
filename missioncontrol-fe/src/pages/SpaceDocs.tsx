import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Plus, FolderIcon, FileText, ChevronRight, FolderPlus } from 'lucide-react'
import api from '../lib/api'
import type { Space, Folder, Doc } from '../types'

export default function SpaceDocs() {
  const { spaceId } = useParams<{ spaceId: string }>()
  const navigate = useNavigate()
  const [space, setSpace] = useState<Space | null>(null)
  const [folders, setFolders] = useState<Folder[]>([])
  const [docs, setDocs] = useState<Doc[]>([])
  const [selectedFolder, setSelectedFolder] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [creatingFolder, setCreatingFolder] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')
  const [creatingDoc, setCreatingDoc] = useState(false)

  const fetchData = useCallback(async () => {
    if (!spaceId) return
    try {
      const [foldersRes, docsRes] = await Promise.all([
        api.get(`/api/spaces/${spaceId}/docs/folders`),
        api.get(`/api/spaces/${spaceId}/docs`, {
          params: selectedFolder ? { folder_id: selectedFolder } : {},
        }),
      ])
      setFolders(foldersRes.data)
      setDocs(docsRes.data)
    } catch {
      // silently handle
    } finally {
      setLoading(false)
    }
  }, [spaceId, selectedFolder])

  useEffect(() => {
    const fetchSpace = async () => {
      if (!spaceId) return
      try {
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
    fetchData()
  }, [spaceId, fetchData])

  const handleCreateFolder = async () => {
    if (!newFolderName.trim() || !spaceId) return
    try {
      await api.post(`/api/spaces/${spaceId}/docs/folders`, {
        name: newFolderName.trim(),
      })
      setNewFolderName('')
      setCreatingFolder(false)
      await fetchData()
    } catch {
      // silently handle
    }
  }

  const handleCreateDoc = async () => {
    if (!spaceId) return
    setCreatingDoc(true)
    try {
      const response = await api.post(`/api/spaces/${spaceId}/docs`, {
        title: 'Untitled Document',
        content: '',
        folder_id: selectedFolder,
      })
      navigate(`/spaces/${spaceId}/docs/${response.data.id}`)
    } catch {
      // silently handle
    } finally {
      setCreatingDoc(false)
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
    <div className="h-full flex flex-col">
      {/* Page header */}
      <div className="mb-6">
        <p className="text-xs font-medium text-warm-400 uppercase tracking-wider mb-1">
          {space?.name || 'Space'}
        </p>
        <h1 className="text-xl font-semibold text-warm-900">Documents</h1>
      </div>

      {/* Content */}
      <div className="flex-1 flex gap-6">
        {/* Folder sidebar */}
        <div className="w-60 shrink-0">
          <div className="flex items-center justify-between mb-3">
            <p className="text-[11px] font-semibold uppercase text-warm-500 tracking-wider">
              Folders
            </p>
            <button
              onClick={() => setCreatingFolder(true)}
              className="p-1 text-warm-400 hover:text-accent hover:bg-accent-50 rounded transition-colors"
              title="New folder"
            >
              <FolderPlus className="h-4 w-4" />
            </button>
          </div>

          <div className="space-y-0.5">
            {/* All documents */}
            <button
              onClick={() => setSelectedFolder(null)}
              className={`flex items-center gap-2.5 w-full px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                selectedFolder === null
                  ? 'bg-accent-50 text-accent-dark'
                  : 'text-warm-600 hover:bg-warm-50'
              }`}
            >
              <FileText className="h-4 w-4" />
              All Documents
            </button>

            {/* Folders */}
            {folders.map((folder) => (
              <button
                key={folder.id}
                onClick={() => setSelectedFolder(folder.id)}
                className={`flex items-center gap-2.5 w-full px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  selectedFolder === folder.id
                    ? 'bg-accent-50 text-accent-dark'
                    : 'text-warm-600 hover:bg-warm-50'
                }`}
              >
                <FolderIcon className="h-4 w-4" />
                <span className="truncate">{folder.name}</span>
              </button>
            ))}

            {/* Inline folder creation */}
            {creatingFolder && (
              <div className="px-2 py-1">
                <input
                  type="text"
                  value={newFolderName}
                  onChange={(e) => setNewFolderName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleCreateFolder()
                    if (e.key === 'Escape') setCreatingFolder(false)
                  }}
                  placeholder="Folder name..."
                  className="w-full px-2 py-1.5 text-sm bg-surface-sunk border-0 rounded-lg text-warm-900 focus:outline-none focus:ring-2 focus:ring-accent/20"
                  autoFocus
                />
              </div>
            )}
          </div>
        </div>

        {/* Document list */}
        <div className="flex-1">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-warm-900">
              {selectedFolder
                ? folders.find((f) => f.id === selectedFolder)?.name || 'Documents'
                : 'All Documents'}
            </h2>
            <button
              onClick={handleCreateDoc}
              disabled={creatingDoc}
              className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-white bg-lumen rounded-lg disabled:opacity-50"
            >
              <Plus className="h-4 w-4" />
              New Document
            </button>
          </div>

          {docs.length === 0 ? (
            <div className="bg-card rounded-xl shadow-e1 p-12 text-center">
              <FileText className="h-10 w-10 text-warm-300 mx-auto mb-3" />
              <p className="text-warm-500 text-sm">No documents yet.</p>
              <p className="text-warm-400 text-xs mt-1">Create your first document to get started.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {docs.map((doc) => (
                <button
                  key={doc.id}
                  onClick={() => navigate(`/spaces/${spaceId}/docs/${doc.id}`)}
                  className="w-full bg-card rounded-xl shadow-e1 card-hover p-4 text-left group flex items-center justify-between"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <FileText className="h-5 w-5 text-warm-400 shrink-0" />
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-warm-900 truncate">
                        {doc.title || 'Untitled'}
                      </p>
                      <div className="flex items-center gap-2 mt-0.5">
                        {doc.created_by_name && (
                          <span className="text-xs text-warm-400">{doc.created_by_name}</span>
                        )}
                        <span className="text-xs text-warm-400">
                          {new Date(doc.updated_at).toLocaleDateString('en-US', {
                            month: 'short',
                            day: 'numeric',
                            year: 'numeric',
                          })}
                        </span>
                      </div>
                    </div>
                  </div>
                  <ChevronRight className="h-4 w-4 text-warm-300 group-hover:text-accent transition-colors shrink-0" />
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
