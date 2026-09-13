import { useEffect, useRef, useState } from 'react'
import { listDocuments } from '../services/api'
import { Icon } from './ui/Icon'

// Documents picker — lets the user re-attach a previously uploaded document
// to a new Job without re-uploading the file. GET /api/v1/documents.
export function DocumentPicker({ onSelectDocument, disabled = false }) {
  const [open, setOpen] = useState(false)
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const containerRef = useRef(null)

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setLoading(true)
    setError(null)
    listDocuments({ limit: 20 })
      .then((res) => {
        if (!cancelled) setDocuments(res.documents ?? [])
      })
      .catch((err) => {
        if (!cancelled) setError(err?.message ?? 'Failed to load documents')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    const handleClickOutside = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [open])

  const handleSelect = (doc) => {
    onSelectDocument?.(doc)
    setOpen(false)
  }

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        className="btn-quiet btn text-txt-mid disabled:opacity-50"
        onClick={() => setOpen((v) => !v)}
        disabled={disabled}
        aria-label="Browse uploaded documents"
        aria-expanded={open}
      >
        <Icon name="folder" size={15} />
        Browse
      </button>

      {open && (
        <div className="absolute bottom-full left-0 mb-2 w-72 max-h-72 overflow-y-auto rounded-lg border border-line bg-surface shadow-lg z-20">
          <div className="px-3 py-2 border-b border-line text-xs font-medium text-txt-dim">
            Uploaded documents
          </div>
          {loading && (
            <div className="px-3 py-4 text-sm text-txt-dim text-center">Loading…</div>
          )}
          {error && (
            <div className="px-3 py-4 text-sm text-danger text-center">{error}</div>
          )}
          {!loading && !error && documents.length === 0 && (
            <div className="px-3 py-4 text-sm text-txt-dim text-center">No documents uploaded yet.</div>
          )}
          {!loading && !error && documents.map((doc) => (
            <button
              key={doc.document_id}
              type="button"
              className="w-full flex items-start gap-2 px-3 py-2 text-left text-sm hover:bg-elevated transition-colors"
              onClick={() => handleSelect(doc)}
            >
              <Icon name="file" size={14} className="mt-0.5 shrink-0 text-txt-low" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-txt-hi">{doc.filename}</p>
                <p className="text-[11px] text-txt-dim mono">
                  {new Date(doc.uploaded_at).toLocaleString()}
                </p>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
