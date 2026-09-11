import { PageHeader } from '../components/ui/PageHeader.jsx'
import { EmptyState } from '../components/ui/EmptyState.jsx'
import { Badge } from '../components/ui/Badge.jsx'

export default function Artifacts() {
  return (
    <div className="mx-auto max-w-[1400px]">
      <PageHeader
        title="Artifacts"
        description="Generated deliverables from completed tasks."
      />

      <div className="mb-5 flex flex-wrap items-center gap-2">
        <Badge tone="purple" icon="artifacts">
          DOCX / XLSX / Markdown
        </Badge>
        <Badge tone="gray">0 files</Badge>
      </div>

      <EmptyState
        icon="artifacts"
        title="No artifacts yet"
        description="Artifacts are rendered deterministically from structured data — the model never controls formatting. Run a task in the Workbench that generates a report and it will appear here for download."
      />

      <div className="mt-5 grid gap-4 lg:grid-cols-3">
        {[
          { type: 'DOCX', note: 'Approval notes, structured findings', icon: 'file' },
          { type: 'XLSX', note: 'Tabular extracts, inspection data', icon: 'file' },
          { type: 'Markdown', note: 'Summaries, quick deliverables', icon: 'file' },
        ].map((kind) => (
          <div key={kind.type} className="card p-4">
            <Badge tone="purple" dot={false} className="mb-2">
              {kind.type}
            </Badge>
            <p className="text-sm text-txt-low">{kind.note}</p>
            <div className="mono mt-2 text-[11px] text-txt-dim">
              backend: GET /api/v1/artifacts/{"{id}"}/download
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}