import { PageHeader } from '../components/ui/PageHeader.jsx'
import { EmptyState } from '../components/ui/EmptyState.jsx'
import { Badge } from '../components/ui/Badge.jsx'

export default function Audit() {
  return (
    <div className="mx-auto max-w-[1400px]">
      <PageHeader
        title="Audit"
        description="Every significant action, model call, and capability invocation — as a single event stream."
      />

      <div className="mb-5 flex flex-wrap items-center gap-2">
        <Badge tone="green" icon="shieldCheck">
          Single source of truth
        </Badge>
        <Badge tone="gray">SSE event stream</Badge>
      </div>

      <EmptyState
        icon="audit"
        title="No events to display"
        description="The Job trace shown in the Workbench is a filtered view over this audit stream. Once tasks run, their events — job_created, policy_decision, tool_invoked, model_invoked, resource_loaded, artifact_created, job_completed — will stream here."
      />

      <div className="mt-5 grid gap-4 lg:grid-cols-3">
        {[
          { name: 'job_created', tone: 'blue' },
          { name: 'policy_decision', tone: 'blue' },
          { name: 'tool_invoked', tone: 'blue' },
          { name: 'model_invoked', tone: 'purple' },
          { name: 'resource_loaded', tone: 'purple' },
          { name: 'artifact_created', tone: 'green' },
          { name: 'network_check', tone: 'green' },
          { name: 'error', tone: 'red' },
          { name: 'job_completed', tone: 'green' },
        ].map((e) => (
          <div key={e.name} className="card flex items-center justify-between px-4 py-3">
            <code className="mono text-[13px] text-txt-mid">{e.name}</code>
            <Badge tone={e.tone} dot={false}>
              defined
            </Badge>
          </div>
        ))}
      </div>
    </div>
  )
}