import { useState, useEffect, useRef } from 'react'
import { useJobEvents } from '../hooks/useJobEvents'
import { CapabilityActivity } from './CapabilityActivity'
import { Icon } from './ui/Icon'
import { Badge } from './ui/Badge'

// Live Job trace panel — driven by useJobEvents (SSE + late-join trace fetch).
// Renders each event through CapabilityActivity in order.
export function JobTracePanel({ jobId }) {
  const { events, status, error, reconnect } = useJobEvents(jobId)
  const [autoScroll, setAutoScroll] = useState(true)
  const traceContainerRef = useRef(null)
  const lastEventCountRef = useRef(0)

  // Auto-scroll to bottom when new events arrive (if user hasn't scrolled up)
  useEffect(() => {
    if (!autoScroll || !traceContainerRef.current) return
    if (events.length > lastEventCountRef.current) {
      traceContainerRef.current.scrollTop = traceContainerRef.current.scrollHeight
    }
    lastEventCountRef.current = events.length
  }, [events, autoScroll])

  const handleScroll = () => {
    if (!traceContainerRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = traceContainerRef.current
    // If user scrolls up more than 100px from bottom, disable auto-scroll
    setAutoScroll(scrollHeight - scrollTop - clientHeight < 100)
  }

  if (!jobId) {
    return (
      <div className="card flex items-center justify-center h-full min-h-[300px] text-txt-dim">
        No active job. Start a conversation to see the live trace.
      </div>
    )
  }

  const statusConfig = {
    connecting: { tone: 'blue', label: 'Connecting…', icon: 'refresh' },
    open: { tone: 'green', label: 'Live', icon: 'activity' },
    closed: { tone: 'gray', label: 'Disconnected', icon: 'alert' },
  }
  const statusInfo = statusConfig[status] ?? statusConfig.closed

  return (
    <div className="card flex flex-col h-full min-h-0">
      {/* Header */}
      <div className="px-4 py-3 border-b border-line flex items-center justify-between">
        <h3 className="text-sm font-semibold text-txt-hi">Live Trace</h3>
        <div className="flex items-center gap-3">
          <Badge tone={statusInfo.tone} icon={statusInfo.icon}>
            {statusInfo.label}
          </Badge>
          {status === 'closed' && (
            <button
              type="button"
              className="btn-quiet btn text-xs"
              onClick={reconnect}
              disabled={!jobId}
            >
              <Icon name="refresh" size={12} />
              Reconnect
            </button>
          )}
          {error && (
            <span className="text-xs text-danger mono">{error.message}</span>
          )}
        </div>
      </div>

      {/* Trace Events */}
      <div
        ref={traceContainerRef}
        className="flex-1 overflow-y-auto p-4 space-y-3"
        onScroll={handleScroll}
        aria-live="polite"
        aria-label="Job execution trace"
      >
        {events.length === 0 && status === 'connecting' && (
          <div className="flex items-center justify-center h-full text-txt-dim">
            <Icon name="refresh" size={24} className="animate-spin text-accent mr-2" />
            Connecting to trace stream…
          </div>
        )}

        {events.length === 0 && status !== 'connecting' && (
          <div className="flex items-center justify-center h-full text-txt-dim">
            No events yet. Waiting for job to start…
          </div>
        )}

        {events.map((event, idx) => (
          <div
            key={`${event.event_id}-${idx}`}
            className="trace-event border-l-2 border-line pl-3 transition-colors"
            style={{ borderLeftColor: getEventBorderColor(event.event_type) }}
          >
            <CapabilityActivity event={event} />
          </div>
        ))}

        {/* Auto-scroll indicator */}
        {!autoScroll && events.length > 0 && (
          <div className="fixed bottom-4 right-4 z-10" style={{ marginLeft: 'calc(50% - 150px)' }}>
            <button
              type="button"
              className="btn-primary btn text-xs shadow-lg"
              onClick={() => {
                setAutoScroll(true)
                traceContainerRef.current?.scrollTo({
                  top: traceContainerRef.current.scrollHeight,
                  behavior: 'smooth',
                })
              }}
            >
              <Icon name="chevronDown" size={12} />
              Scroll to latest
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

function getEventBorderColor(eventType) {
  const colors = {
    job_created: '#4c8dff',
    orchestrator_step: '#a78bfa',
    policy_decision: '#2ec98c',
    tool_invoked: '#a78bfa',
    model_invoked: '#4c8dff',
    resource_loaded: '#4c8dff',
    resource_unloaded: '#6d7f99',
    artifact_created: '#a78bfa',
    error: '#ef6f6f',
    job_completed: '#2ec98c',
  }
  return colors[eventType] ?? '#31466f'
}