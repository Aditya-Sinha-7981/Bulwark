import { useMemo } from 'react'
import { Icon } from './ui/Icon'
import { Badge } from './ui/Badge'

// RAG Evidence panel — scans trace events for search_knowledge_base results.
// Renders retrieval results (title, snippet, score) so grounding is visible.
export function RagEvidencePanel({ events = [] }) {
  const searchResults = useMemo(() => {
    const results = []
    for (const event of events) {
      // tool_result carries the capability's actual output (docs/audit.md);
      // tool_invoked only carries the call arguments, never the response.
      if (event.event_type === 'tool_result' && event.payload?.capability === 'search_knowledge_base') {
        const payloadResults = event.payload?.result?.results
        if (Array.isArray(payloadResults) && payloadResults.length > 0) {
          results.push(...payloadResults.map((r, idx) => ({
            ...r,
            _eventId: event.event_id,
            _index: idx,
          })))
        }
      }
    }
    return results
  }, [events])

  if (!searchResults.length) {
    return (
      <div className="card flex items-center justify-center h-full min-h-[200px] text-txt-dim">
        <div className="text-center">
          <Icon name="knowledge" size={32} className="mx-auto mb-2 text-txt-low" />
          <p>No retrieval evidence yet.</p>
          <p className="text-xs mt-1">Run a query that searches the knowledge base to see results here.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="card flex flex-col h-full min-h-0">
      <div className="px-4 py-3 border-b border-line flex items-center justify-between">
        <h3 className="text-sm font-semibold text-txt-hi">RAG Evidence</h3>
        <Badge tone="purple" dot={false}>
          {searchResults.length} result{searchResults.length !== 1 ? 's' : ''}
        </Badge>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {searchResults.map((result, idx) => (
          <div
            key={`${result._eventId}-${result._index}-${idx}`}
            className="border border-line rounded-lg p-3 hover:border-accent/40 transition-colors"
          >
            <div className="flex items-start justify-between gap-2 mb-2">
              <h4 className="text-sm font-medium text-txt-hi truncate">
                {result.title ?? result.document_title ?? `Result ${idx + 1}`}
              </h4>
              {result.score != null && (
                <Badge tone={result.score > 0.7 ? 'green' : result.score > 0.4 ? 'blue' : 'gray'} dot={false}>
                  {typeof result.score === 'number' ? (result.score * 100).toFixed(0) + '%' : result.score}
                </Badge>
              )}
            </div>
            {result.snippet && (
              <p className="text-sm text-txt-mid line-clamp-4 bg-elevated p-2 rounded mono text-[11px]">
                {result.snippet}
              </p>
            )}
            {result.chunk_text && !result.snippet && (
              <p className="text-sm text-txt-mid line-clamp-4 bg-elevated p-2 rounded mono text-[11px]">
                {result.chunk_text}
              </p>
            )}
            <div className="mt-2 flex flex-wrap gap-2 text-[10px] text-txt-dim mono">
              {result.kb_document_id && <span>doc: {result.kb_document_id.slice(0, 8)}…</span>}
              {result.chunk_index != null && <span>chunk: {result.chunk_index}</span>}
              {result.metadata && Object.entries(result.metadata).map(([k, v]) => (
                <span key={k}>{k}: {v}</span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}