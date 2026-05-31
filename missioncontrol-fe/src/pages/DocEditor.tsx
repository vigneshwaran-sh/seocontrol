import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Check, Loader2 } from 'lucide-react'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Underline from '@tiptap/extension-underline'
import Placeholder from '@tiptap/extension-placeholder'
import api from '../lib/api'
import type { Doc } from '../types'

type SaveState = 'idle' | 'saving' | 'saved'

export default function DocEditor() {
  const { spaceId, docId } = useParams<{ spaceId: string; docId: string }>()
  const navigate = useNavigate()
  const [doc, setDoc] = useState<Doc | null>(null)
  const [title, setTitle] = useState('')
  const [loading, setLoading] = useState(true)
  const [saveState, setSaveState] = useState<SaveState>('idle')
  const saveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const initialLoadRef = useRef(true)

  const saveDoc = useCallback(
    async (newTitle: string, newContent: string) => {
      if (!spaceId || !docId) return
      setSaveState('saving')
      try {
        await api.put(`/api/spaces/${spaceId}/docs/${docId}`, {
          title: newTitle,
          content: newContent,
        })
        setSaveState('saved')
        setTimeout(() => setSaveState('idle'), 2000)
      } catch {
        setSaveState('idle')
      }
    },
    [spaceId, docId]
  )

  const debouncedSave = useCallback(
    (newTitle: string, newContent: string) => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current)
      }
      saveTimeoutRef.current = setTimeout(() => {
        saveDoc(newTitle, newContent)
      }, 1000)
    },
    [saveDoc]
  )

  const editor = useEditor({
    extensions: [
      StarterKit,
      Underline,
      Placeholder.configure({
        placeholder: 'Start writing...',
      }),
    ],
    content: '',
    onUpdate: ({ editor: ed }) => {
      if (!initialLoadRef.current) {
        debouncedSave(title, ed.getHTML())
      }
    },
    editorProps: {
      attributes: {
        class: 'prose prose-warm max-w-none focus:outline-none',
      },
    },
  })

  useEffect(() => {
    const fetchDoc = async () => {
      if (!spaceId || !docId) return
      try {
        const response = await api.get(`/api/spaces/${spaceId}/docs/${docId}`)
        const fetchedDoc: Doc = response.data
        setDoc(fetchedDoc)
        setTitle(fetchedDoc.title)
        if (editor) {
          editor.commands.setContent(fetchedDoc.content || '')
        }
        initialLoadRef.current = false
      } catch {
        // silently handle
      } finally {
        setLoading(false)
      }
    }

    fetchDoc()
  }, [spaceId, docId, editor])

  // Save on title change (after initial load)
  useEffect(() => {
    if (!initialLoadRef.current && doc && editor) {
      debouncedSave(title, editor.getHTML())
    }
  }, [title, doc, editor, debouncedSave])

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current)
      }
    }
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-warm-200 border-t-accent" />
      </div>
    )
  }

  if (!doc) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-warm-500 text-sm">Document not found.</p>
      </div>
    )
  }

  return (
    <div className="max-w-3xl mx-auto">
      {/* Top bar */}
      <div className="flex items-center justify-between mb-6">
        <button
          onClick={() => navigate(`/spaces/${spaceId}/docs`)}
          className="flex items-center gap-2 text-sm text-warm-500 hover:text-warm-700 transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to docs
        </button>

        {/* Save status */}
        <div className="flex items-center gap-1.5 text-xs text-warm-400">
          {saveState === 'saving' && (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Saving...
            </>
          )}
          {saveState === 'saved' && (
            <>
              <Check className="h-3.5 w-3.5 text-success" />
              <span className="text-success">Saved</span>
            </>
          )}
        </div>
      </div>

      {/* Document card */}
      <div className="bg-card rounded-2xl shadow-e1 p-8">
        {/* Title */}
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="w-full text-3xl font-serif font-bold text-warm-900 placeholder:text-warm-300 bg-transparent border-none focus:outline-none mb-6"
          placeholder="Untitled"
        />

        {/* Toolbar */}
        {editor && (
          <div className="flex items-center gap-1 pb-4 mb-4 border-b border-border flex-wrap">
          <ToolbarButton
            active={editor.isActive('bold')}
            onClick={() => editor.chain().focus().toggleBold().run()}
            label="B"
            fontWeight="font-bold"
          />
          <ToolbarButton
            active={editor.isActive('italic')}
            onClick={() => editor.chain().focus().toggleItalic().run()}
            label="I"
            fontStyle="italic"
          />
          <ToolbarButton
            active={editor.isActive('underline')}
            onClick={() => editor.chain().focus().toggleUnderline().run()}
            label="U"
            underline
          />

          <div className="w-px h-5 bg-border mx-1" />

          <ToolbarButton
            active={editor.isActive('heading', { level: 1 })}
            onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
            label="H1"
          />
          <ToolbarButton
            active={editor.isActive('heading', { level: 2 })}
            onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
            label="H2"
          />
          <ToolbarButton
            active={editor.isActive('heading', { level: 3 })}
            onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
            label="H3"
          />

          <div className="w-px h-5 bg-border mx-1" />

          <ToolbarButton
            active={editor.isActive('bulletList')}
            onClick={() => editor.chain().focus().toggleBulletList().run()}
            label="UL"
          />
          <ToolbarButton
            active={editor.isActive('orderedList')}
            onClick={() => editor.chain().focus().toggleOrderedList().run()}
            label="OL"
          />
          </div>
        )}

        {/* Editor */}
        <div className="tiptap-editor">
          <EditorContent editor={editor} />
        </div>
      </div>
    </div>
  )
}

function ToolbarButton({
  active,
  onClick,
  label,
  fontWeight,
  fontStyle,
  underline,
}: {
  active: boolean
  onClick: () => void
  label: string
  fontWeight?: string
  fontStyle?: string
  underline?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-2.5 py-1.5 text-xs rounded-lg transition-colors ${
        active
          ? 'bg-accent-100 text-accent-dark'
          : 'text-warm-600 hover:bg-warm-50'
      } ${fontWeight || ''} ${fontStyle || ''} ${underline ? 'underline' : ''}`}
    >
      {label}
    </button>
  )
}
