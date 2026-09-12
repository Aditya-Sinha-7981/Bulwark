import { Icon } from './ui/Icon'
import { Badge } from './ui/Badge'

// Renders a single audit event by event_type (per docs/audit.md).
// Unknown event types render generically — never crash.
export function CapabilityActivity({ event }) {
  if (!event) return null

  const { event_type, payload, timestamp, component } = event
  const time = timestamp ? new Date(timestamp).toLocaleTimeString() : ''

  const renderPayload = (obj) => {
    if (!obj || typeof obj !== 'object') return String(obj ?? '')
    return Object.entries(obj)
      .map(([k, v]) => (
        <span key={k} className="flex gap-1">
          <span className="text-txt-dim mono text-[11px]">{k}:</span>
          <span className="mono text-[11px] text-txt-mid">{String(v)}</span>
        </span>
      ))
  }

  switch (event_type) {
    case 'job_created': {
      return (
        <div className="flex items-center gap-2 text-txt-mid">
          <Icon name="activity" size={14} className="text-accent" />
          <span>Job created</span>
          {payload?.conversation_id && (
            <span className="mono text-[11px] text-txt-dim">({payload.conversation_id.slice(0, 8)}…)</span>
          )}
          <span className="mono text-[10px] text-txt-dim ml-auto">{time}</span>
        </div>
      )
    }

    case 'orchestrator_step': {
      const action = payload?.action ?? 'unknown'
      return (
        <div className="flex items-center gap-2 text-txt-mid">
          <Icon name="activity" size={14} className="text-accent" />
          <span>Orchestrator: <strong className="text-txt-hi">{action}</strong></span>
          {payload?.proposal && (
            <details className="ml-4 mt-1">
              <summary className="text-xs text-txt-low cursor-pointer mono">Proposal</summary>
              <pre className="mt-1 text-[10px] mono text-txt-mid bg-elevated p-2 rounded overflow-auto max-h-24">
                {JSON.stringify(payload.proposal, null, 2)}
              </pre>
            </details>
          )}
          <span className="mono text-[10px] text-txt-dim ml-auto">{time}</span>
        </div>
      )
    }

    case 'policy_decision': {
      const decision = payload?.decision ?? 'unknown'
      const reason = payload?.reason ?? ''
      const capability = payload?.capability ?? ''
      const isAllow = decision === 'allow'
      return (
        <div className="flex items-center gap-2">
          <Icon name={isAllow ? 'shieldCheck' : 'alert'} size={14} className={isAllow ? 'text-ok' : 'text-danger'} />
          <span className="font-medium">{isAllow ? 'Allowed' : 'Denied'}</span>
          {capability && <span className="mono text-[11px] text-txt-dim">{capability}</span>}
          <Badge tone={isAllow ? 'green' : 'red'} dot={false} icon={isAllow ? 'check' : 'x'}>
            {decision}
          </Badge>
          {reason && (
            <span className="ml-2 text-xs text-txt-low italic max-w-[300px] truncate">{reason}</span>
          )}
          <span className="mono text-[10px] text-txt-dim ml-auto">{time}</span>
        </div>
      )
    }

    case 'tool_invoked': {
      const capability = payload?.capability ?? 'unknown'
      const args = payload?.arguments ?? {}
      return (
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2 text-txt-mid">
            <Icon name="activity" size={14} className="text-band" />
            <span>Calling <strong className="text-txt-hi mono">{capability}</strong>…</span>
            <span className="mono text-[10px] text-txt-dim ml-auto">{time}</span>
          </div>
          {Object.keys(args).length > 0 && (
            <div className="ml-6 flex flex-wrap gap-1 text-[11px]">
              {renderPayload(args)}
            </div>
          )}
        </div>
      )
    }

    case 'model_invoked': {
      const resourceType = payload?.resource_type ?? ''
      const modelIdentifier = payload?.model_identifier ?? ''
      const promptTokens = payload?.prompt_tokens
      const completionTokens = payload?.completion_tokens
      const durationMs = payload?.duration_ms
      return (
        <div className="flex items-center gap-2 text-txt-mid">
          <Icon name="node" size={14} className="text-accent" />
          <span>
            Model: <strong className="text-txt-hi mono">{modelIdentifier}</strong>
            {resourceType && <span className="text-txt-dim"> ({resourceType})</span>}
          </span>
          {(promptTokens || completionTokens) && (
            <span className="text-[10px] text-txt-dim mono ml-2">
              {promptTokens ?? 0}→{completionTokens ?? 0} tok
            </span>
          )}
          {durationMs && (
            <span className="text-[10px] text-txt-dim mono ml-2">{durationMs}ms</span>
          )}
          <span className="mono text-[10px] text-txt-dim ml-auto">{time}</span>
        </div>
      )
    }

    case 'resource_loaded': {
      const resourceType = payload?.resource_type ?? ''
      const modelIdentifier = payload?.model_identifier ?? ''
      const durationMs = payload?.duration_ms
      return (
        <div className="flex items-center gap-2 text-txt-mid">
          <Icon name="download" size={14} className="text-accent animate-pulse" />
          <span className="font-medium text-accent">
            Loading <strong className="text-txt-hi mono">{modelIdentifier}</strong>
            {resourceType && <span className="text-txt-dim"> ({resourceType})</span>}
          </span>
          {durationMs && (
            <span className="text-[10px] text-txt-dim mono ml-2">{durationMs}ms</span>
          )}
          <span className="mono text-[10px] text-txt-dim ml-auto">{time}</span>
        </div>
      )
    }

    case 'resource_unloaded': {
      const resourceType = payload?.resource_type ?? ''
      const modelIdentifier = payload?.model_identifier ?? ''
      const reason = payload?.reason ?? ''
      return (
        <div className="flex items-center gap-2 text-txt-mid">
          <Icon name="upload" size={14} className="text-txt-low" />
          <span>Unloaded <strong className="text-txt-hi mono">{modelIdentifier}</strong></span>
          {resourceType && <span className="text-txt-dim"> ({resourceType})</span>}
          {reason && <span className="text-xs text-txt-low">({reason})</span>}
          <span className="mono text-[10px] text-txt-dim ml-auto">{time}</span>
        </div>
      )
    }

    case 'artifact_created': {
      const artifactId = payload?.artifact_id ?? ''
      const type = payload?.type ?? ''
      const filename = payload?.filename ?? ''
      return (
        <div className="flex items-center gap-2 text-txt-mid">
          <Icon name="artifacts" size={14} className="text-band" />
          <span>Artifact created:</span>
          <strong className="text-txt-hi">{filename}</strong>
          {type && <span className="text-txt-dim">({type})</span>}
          {artifactId && <span className="mono text-[10px] text-txt-dim">({artifactId.slice(0, 8)}…)</span>}
          <span className="mono text-[10px] text-txt-dim ml-auto">{time}</span>
        </div>
      )
    }

    case 'error': {
      const message = payload?.message ?? payload?.error ?? 'Unknown error'
      const comp = payload?.component ?? component
      return (
        <div className="flex items-start gap-2 text-danger">
          <Icon name="alert" size={14} className="shrink-0 mt-0.5" />
          <div className="flex-1">
            <span className="font-medium">Error</span>
            {comp && <span className="text-txt-dim ml-2 mono text-[11px]">[{comp}]</span>}
            <p className="mt-0.5 text-sm">{message}</p>
          </div>
          <span className="mono text-[10px] text-txt-dim ml-auto">{time}</span>
        </div>
      )
    }

    case 'job_completed': {
      const status = payload?.status ?? 'completed'
      const durationMs = payload?.duration_ms
      const isSuccess = status === 'completed'
      return (
        <div className="flex items-center gap-2">
          <Icon name={isSuccess ? 'check' : 'alert'} size={14} className={isSuccess ? 'text-ok' : 'text-danger'} />
          <span className="font-medium">{isSuccess ? 'Job completed' : 'Job failed'}</span>
          <Badge tone={isSuccess ? 'green' : 'red'} dot={false}>{status}</Badge>
          {durationMs && <span className="mono text-[10px] text-txt-dim ml-2">{durationMs}ms</span>}
          <span className="mono text-[10px] text-txt-dim ml-auto">{time}</span>
        </div>
      )
    }

    default: {
      // Unknown event type — render generically, never crash
      return (
        <details className="w-full">
          <summary className="flex items-center gap-2 text-txt-low cursor-pointer">
            <Icon name="activity" size={14} className="text-txt-dim" />
            <span className="mono text-[11px] font-medium">{event_type}</span>
          </summary>
          <div className="mt-2 ml-6 text-[11px] mono text-txt-mid bg-elevated p-2 rounded overflow-auto max-h-40">
            <pre>{JSON.stringify(payload, null, 2)}</pre>
          </div>
          <span className="mono text-[10px] text-txt-dim ml-6">{time}</span>
        </details>
      )
    }
  }
}