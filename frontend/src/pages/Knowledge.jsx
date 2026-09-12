import { PageHeader } from '../components/ui/PageHeader.jsx'
import { EmptyState } from '../components/ui/EmptyState.jsx'
import { Badge } from '../components/ui/Badge.jsx'
import { Button } from '../components/ui/Button.jsx'

export default function Knowledge() {
  return (
    <div className="mx-auto max-w-[1400px]">
      <PageHeader
        title="Knowledge"
        description="Curate the local knowledge base your models retrieve from."
      />

      <div className="mb-5 flex flex-wrap items-center gap-2">
        <Badge tone="gray">0 documents indexed</Badge>
        <Badge tone="blue" icon="knowledge">
          Embedding: qwen3-embedding:0.6b
        </Badge>
      </div>

      <EmptyState
        icon="knowledge"
        title="No documents in the knowledge base yet"
        description="Ingest SOP-style documents, reports, or notes and Bulwark will chunk, embed, and index them locally with Chroma. Retrieval only ever happens when the orchestrator explicitly proposes a knowledge search."
        action={
          <Button variant="primary" icon="plus" disabled>
            Upload document
          </Button>
        }
      />

      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <div className="card p-4">
          <h3 className="text-sm font-semibold text-txt-hi">Ingestion pipeline</h3>
          <ul className="mt-3 space-y-2 text-[13px] text-txt-mid">
            <li>1. Parse plain text, markdown, or PDF text layer</li>
            <li>2. Chunk at ~500 tokens with overlap</li>
            <li>3. Embed locally via the embedding resource</li>
            <li>4. Index into the Chroma collection</li>
            <li>5. Status: ingesting → ready (or failed)</li>
          </ul>
        </div>
        <div className="card p-4">
          <h3 className="text-sm font-semibold text-txt-hi">Retrieval</h3>
          <p className="mt-3 text-sm leading-relaxed text-txt-low">
            The orchestrator must explicitly propose{' '}
            <code className="mono rounded bg-elevated px-1.5 py-0.5 text-[12px] text-accent">
              search_knowledge_base
            </code>{' '}
            — retrieval is never automatic. Results are returned as evidence for a grounded answer.
          </p>
          <div className="mono mt-3 text-[11px] text-txt-dim">
            backend: POST /api/v1/knowledge-base/documents (deferred)
          </div>
        </div>
      </div>
    </div>
  )
}