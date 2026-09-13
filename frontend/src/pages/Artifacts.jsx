import { useEffect, useMemo, useState } from 'react'
import { PageHeader } from '../components/ui/PageHeader.jsx'
import { EmptyState } from '../components/ui/EmptyState.jsx'
import { Badge } from '../components/ui/Badge.jsx'
import { Icon } from '../components/ui/Icon.jsx'
import { listArtifacts, artifactDownloadUrl } from '../services/api.js'

const POLL_INTERVAL_MS = 10000

const TYPE_FILTERS = [
  { id: 'all', label: 'All', match: () => true },
  { id: 'docx', label: 'DOCX', match: (t) => t === 'docx' },
  { id: 'xlsx', label: 'XLSX', match: (t) => t === 'xlsx' },
  { id: 'pptx', label: 'PPTX', match: (t) => t === 'pptx' },
]

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / 1024 ** i).toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

// Artifacts the system has generated (create_docx / create_xlsx output) —
// GET /api/v1/artifacts. Deterministically rendered from structured data,
// per capability — the model never controls formatting (AGENTS.md §6 rule 6).
export default function Artifacts() {
  const [artifacts, setArtifacts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('all')

  useEffect(() => {
    let cancelled = false
    const fetchArtifacts = () => {
      listArtifacts({ limit: 100 })
        .then((res) => {
          if (!cancelled) {
            setArtifacts(res.artifacts ?? [])
            setError(null)
          }
        })
        .catch((err) => {
          if (!cancelled) setError(err?.message ?? 'Failed to load artifacts')
        })
        .finally(() => {
          if (!cancelled) setLoading(false)
        })
    }
    fetchArtifacts()
    const interval = setInterval(fetchArtifacts, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [])

  const activeTypeFilter = TYPE_FILTERS.find((f) => f.id === typeFilter) ?? TYPE_FILTERS[0]
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return artifacts.filter(
      (art) =>
        activeTypeFilter.match(art.type) &&
        (!q || art.filename.toLowerCase().includes(q))
    )
  }, [artifacts, search, activeTypeFilter])

  return (
    <div className="mx-auto max-w-[1400px]">
      <PageHeader
        title="Created"
        description="Generated deliverables from completed tasks — rendered deterministically, never model-formatted."
      >
        <Badge tone="purple" dot={false} icon="artifacts">
          {filtered.length} of {artifacts.length} file{artifacts.length !== 1 ? 's' : ''}
        </Badge>
      </PageHeader>

      {artifacts.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <div className="relative min-w-[220px] flex-1 max-w-sm">
            <Icon name="search" size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-txt-dim" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search filename…"
              className="input w-full pl-9 text-sm"
              aria-label="Search artifacts by filename"
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

      {loading && artifacts.length === 0 && !error && (
        <div className="card flex min-h-[200px] items-center justify-center text-txt-dim">
          Loading…
        </div>
      )}

      {!loading && !error && artifacts.length === 0 && (
        <EmptyState
          icon="artifacts"
          title="No artifacts yet"
          description="Run a task in the Workbench that generates a report (DOCX/XLSX) and it will appear here for download."
        />
      )}

      {!loading && !error && artifacts.length > 0 && filtered.length === 0 && (
        <EmptyState
          icon="search"
          title="No artifacts match your filters"
          description="Try a different search term or type filter."
        />
      )}

      {filtered.length > 0 && (
        <div className="grid gap-3 lg:grid-cols-2">
          {filtered.map((art) => (
            <a
              key={art.artifact_id}
              href={artifactDownloadUrl(art.artifact_id)}
              download={art.filename}
              target="_blank"
              rel="noopener noreferrer"
              className="card flex items-center gap-3 p-4 hover:border-accent/40 hover:bg-elevated transition-colors"
            >
              <div className="p-2 rounded-lg bg-band-soft text-band shrink-0">
                <Icon name="file" size={20} />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-txt-hi">{art.filename}</p>
                <div className="mt-1 flex items-center gap-2 text-[11px] text-txt-dim mono">
                  <span>{art.type?.toUpperCase()}</span>
                  <span>{formatBytes(art.size_bytes)}</span>
                  <span>{new Date(art.created_at).toLocaleString()}</span>
                </div>
              </div>
              <Icon name="download" size={16} className="text-txt-low shrink-0" />
            </a>
          ))}
        </div>
      )}
    </div>
  )
}
