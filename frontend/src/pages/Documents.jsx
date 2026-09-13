import { useEffect, useMemo, useState } from 'react'
import { PageHeader } from '../components/ui/PageHeader.jsx'
import { EmptyState } from '../components/ui/EmptyState.jsx'
import { Badge } from '../components/ui/Badge.jsx'
import { Icon } from '../components/ui/Icon.jsx'
import { listDocuments } from '../services/api.js'

const POLL_INTERVAL_MS = 10000

const TYPE_FILTERS = [
  { id: 'all', label: 'All', match: () => true },
  { id: 'image/png', label: 'PNG', match: (t) => t === 'image/png' },
  { id: 'image/jpeg', label: 'JPEG', match: (t) => t === 'image/jpeg' },
  { id: 'application/pdf', label: 'PDF', match: (t) => t === 'application/pdf' },
]

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / 1024 ** i).toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

// Documents uploaded via the Workbench composer for extract_document
// (scanned reports, etc.) — GET /api/v1/documents. These aren't scoped to
// any one conversation in the data model, so they get their own page rather
// than living inside a specific chat.
export default function Documents() {
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('all')

  useEffect(() => {
    let cancelled = false
    const fetchDocs = () => {
      listDocuments({ limit: 100 })
        .then((res) => {
          if (!cancelled) {
            setDocuments(res.documents ?? [])
            setError(null)
          }
        })
        .catch((err) => {
          if (!cancelled) setError(err?.message ?? 'Failed to load documents')
        })
        .finally(() => {
          if (!cancelled) setLoading(false)
        })
    }
    fetchDocs()
    const interval = setInterval(fetchDocs, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [])

  const activeTypeFilter = TYPE_FILTERS.find((f) => f.id === typeFilter) ?? TYPE_FILTERS[0]
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return documents.filter(
      (doc) =>
        activeTypeFilter.match(doc.content_type) &&
        (!q || doc.filename.toLowerCase().includes(q))
    )
  }, [documents, search, activeTypeFilter])

  return (
    <div className="mx-auto max-w-[1400px]">
      <PageHeader
        title="Documents"
        description="Files uploaded to the Workbench for extraction (scanned reports, inspection photos, etc.)."
      >
        <Badge tone="gray">
          {filtered.length} of {documents.length} file{documents.length !== 1 ? 's' : ''}
        </Badge>
      </PageHeader>

      {documents.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <div className="relative min-w-[220px] flex-1 max-w-sm">
            <Icon name="search" size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-txt-dim" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search filename…"
              className="input w-full pl-9 text-sm"
              aria-label="Search documents by filename"
            />
          </div>
          <div className="flex items-center gap-1">
            {TYPE_FILTERS.map((f) => (
              <button
                key={f.id}
                type="button"
                onClick={() => setTypeFilter(f.id)}
                className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                  typeFilter === f.id
                    ? 'bg-accent-soft text-accent'
                    : 'text-txt-mid hover:bg-elevated hover:text-txt-hi'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {error && (
        <div className="mb-4 rounded-lg border border-danger/30 bg-danger-soft px-4 py-2 text-sm text-danger">
          {error}
        </div>
      )}

      {loading && documents.length === 0 && !error && (
        <div className="card flex min-h-[200px] items-center justify-center text-txt-dim">
          Loading…
        </div>
      )}

      {!loading && !error && documents.length === 0 && (
        <EmptyState
          icon="file"
          title="No documents uploaded yet"
          description="Attach a file from the Workbench composer (scanned reports, inspection photos) and it will appear here."
        />
      )}

      {!loading && !error && documents.length > 0 && filtered.length === 0 && (
        <EmptyState
          icon="search"
          title="No documents match your filters"
          description="Try a different search term or type filter."
        />
      )}

      {filtered.length > 0 && (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left text-[11px] uppercase tracking-wide text-txt-dim">
                <th className="px-4 py-3 font-medium">Filename</th>
                <th className="px-4 py-3 font-medium">Type</th>
                <th className="px-4 py-3 font-medium">Size</th>
                <th className="px-4 py-3 font-medium">Uploaded</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((doc) => (
                <tr key={doc.document_id} className="border-b border-line last:border-0 hover:bg-elevated transition-colors">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <Icon name="file" size={15} className="shrink-0 text-txt-low" />
                      <span className="truncate text-txt-hi">{doc.filename}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 mono text-[11px] text-txt-dim">{doc.content_type}</td>
                  <td className="px-4 py-3 mono text-[11px] text-txt-dim">{formatBytes(doc.size_bytes)}</td>
                  <td className="px-4 py-3 mono text-[11px] text-txt-dim">
                    {new Date(doc.uploaded_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
