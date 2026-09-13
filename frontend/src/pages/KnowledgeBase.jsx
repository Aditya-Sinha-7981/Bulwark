import { useEffect, useMemo, useRef, useState } from 'react'
import { PageHeader } from '../components/ui/PageHeader.jsx'
import { EmptyState } from '../components/ui/EmptyState.jsx'
import { Badge } from '../components/ui/Badge.jsx'
import { Icon } from '../components/ui/Icon.jsx'
import { getKnowledgeBase, ingestKnowledgeDocument } from '../services/api.js'

const POLL_INTERVAL_MS = 10000

// docs/rag.md / backend/api/knowledge_base.py ALLOWED_EXTENSIONS — PDF is
// text-layer extraction only at ingestion time; scanned-input OCR is a
// query-time (extract_document) concern, not this endpoint's.
const ACCEPTED_EXTENSIONS = '.txt,.md,.markdown,.pdf'

const STATUS_FILTERS = [
  { id: 'all', label: 'All', match: () => true },
  { id: 'ready', label: 'Ready', match: (s) => s === 'ready' },
  { id: 'ingesting', label: 'Ingesting', match: (s) => s === 'ingesting' },
  { id: 'failed', label: 'Failed', match: (s) => s === 'failed' },
]

const STATUS_BADGE = {
  ready: { tone: 'green', icon: 'check' },
  ingesting: { tone: 'blue', icon: 'refresh' },
  failed: { tone: 'red', icon: 'alert' },
}

// Documents ingested into the local knowledge base (search_knowledge_base /
// RAG retrieval) — GET /api/v1/knowledge-base. A completely separate store
// from the Documents page: those are uploaded for extract_document, these
// are ingested for retrieval. Different table, different purpose.
export default function KnowledgeBase() {
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [ingesting, setIngesting] = useState(false)
  const [ingestError, setIngestError] = useState(null)
  const fileInputRef = useRef(null)

  const mountedRef = useRef(true)
  const fetchKb = () => {
    return getKnowledgeBase()
      .then((res) => {
        if (!mountedRef.current) return
        setDocuments(res.documents ?? [])
        setError(null)
      })
      .catch((err) => {
        if (mountedRef.current) setError(err?.message ?? 'Failed to load knowledge base')
      })
      .finally(() => {
        if (mountedRef.current) setLoading(false)
      })
  }

  useEffect(() => {
    mountedRef.current = true
    fetchKb()
    const interval = setInterval(fetchKb, POLL_INTERVAL_MS)
    return () => {
      mountedRef.current = false
      clearInterval(interval)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleIngestFile = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return

    setIngesting(true)
    setIngestError(null)
    try {
      // Backend defaults title to the filename stem when no metadata is
      // given (backend/api/knowledge_base.py) — no title/category prompt
      // needed for a straightforward upload-and-go flow.
      await ingestKnowledgeDocument(file)
      await fetchKb()
    } catch (err) {
      setIngestError(err?.message ?? 'Ingestion failed')
    } finally {
      setIngesting(false)
      e.target.value = ''
    }
  }

  const activeStatusFilter = STATUS_FILTERS.find((f) => f.id === statusFilter) ?? STATUS_FILTERS[0]
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return documents.filter(
      (doc) =>
        activeStatusFilter.match(doc.status) &&
        (!q || doc.title.toLowerCase().includes(q))
    )
  }, [documents, search, activeStatusFilter])

  return (
    <div className="mx-auto max-w-[1400px]">
      <PageHeader
        title="Knowledge Base"
        description="Documents ingested for search_knowledge_base retrieval — separate from uploaded documents."
      >
        <div className="flex items-center gap-3">
          <Badge tone="blue" dot={false} icon="knowledge">
            {filtered.length} of {documents.length} document{documents.length !== 1 ? 's' : ''}
          </Badge>
          <div className="relative">
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPTED_EXTENSIONS}
              className="hidden"
              onChange={handleIngestFile}
              disabled={ingesting}
              aria-label="Ingest a document into the knowledge base"
            />
            <button
              type="button"
              className="btn-primary btn text-sm disabled:opacity-50"
              onClick={() => fileInputRef.current?.click()}
              disabled={ingesting}
            >
              <Icon name="plus" size={14} />
              {ingesting ? 'Ingesting…' : 'Ingest document'}
            </button>
            {ingestError && (
              <div className="absolute right-0 top-full mt-2 w-64 rounded-lg border border-danger/30 bg-danger-soft px-3 py-2 text-xs text-danger z-10">
                {ingestError}
              </div>
            )}
          </div>
        </div>
      </PageHeader>
      <p className="mb-4 -mt-3 text-[11px] text-txt-dim">
        Accepts .txt, .md, and .pdf (text-layer only — scanned PDFs go through the Workbench's document extraction instead).
      </p>

      {documents.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <div className="relative min-w-[220px] flex-1 max-w-sm">
            <Icon name="search" size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-txt-dim" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search title…"
              className="input w-full pl-9 text-sm"
              aria-label="Search knowledge base by title"
            />
          </div>
          <div className="flex items-center gap-1">
            {STATUS_FILTERS.map((f) => (
              <button
                key={f.id}
                type="button"
                onClick={() => setStatusFilter(f.id)}
                className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                  statusFilter === f.id
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
          icon="knowledge"
          title="No documents in the knowledge base yet"
          description="Ingest an SOP or reference document via POST /api/v1/knowledge-base/documents and it will appear here once ready."
        />
      )}

      {!loading && !error && documents.length > 0 && filtered.length === 0 && (
        <EmptyState
          icon="search"
          title="No documents match your filters"
          description="Try a different search term or status filter."
        />
      )}

      {filtered.length > 0 && (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left text-[11px] uppercase tracking-wide text-txt-dim">
                <th className="px-4 py-3 font-medium">Title</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Chunks</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((doc) => {
                const statusMeta = STATUS_BADGE[doc.status] ?? { tone: 'gray', icon: 'dot' }
                return (
                  <tr key={doc.kb_document_id} className="border-b border-line last:border-0 hover:bg-elevated transition-colors">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <Icon name="knowledge" size={15} className="shrink-0 text-txt-low" />
                        <span className="truncate text-txt-hi">{doc.title}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <Badge tone={statusMeta.tone} dot={false} icon={statusMeta.icon}>
                        {doc.status}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 mono text-[11px] text-txt-dim">{doc.chunk_count}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
