import { useEffect, useState } from 'react'
import { PageHeader } from '../components/ui/PageHeader.jsx'
import { EmptyState } from '../components/ui/EmptyState.jsx'
import { Badge } from '../components/ui/Badge.jsx'
import { Icon } from '../components/ui/Icon.jsx'
import { listDocuments } from '../services/api.js'

const POLL_INTERVAL_MS = 10000

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

  return (
    <div className="mx-auto max-w-[1400px]">
      <PageHeader
        title="Documents"
        description="Files uploaded to the Workbench for extraction (scanned reports, inspection photos, etc.)."
      >
        <Badge tone="gray">{documents.length} file{documents.length !== 1 ? 's' : ''}</Badge>
      </PageHeader>

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

      {documents.length > 0 && (
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
              {documents.map((doc) => (
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
