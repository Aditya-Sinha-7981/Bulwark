import { Badge } from '../ui/Badge.jsx'
import { ArtifactCard } from './ArtifactCard.jsx'
import { ExecutionSteps } from './ExecutionSteps.jsx'
import { SecurityPanel } from './SecurityPanel.jsx'

function Detail({ label, value, mono = false }) {
  return (
    <div className="flex items-start justify-between gap-3 py-1.5">
      <dt className="text-xs text-txt-low">{label}</dt>
      <dd className={`text-right text-xs font-medium text-txt-mid ${mono ? 'mono' : ''}`}>{value}</dd>
    </div>
  )
}

export function TaskDetailsPanel({ task, artifact, steps, running }) {
  return (
    <div className="space-y-4">
      {/* Task Details */}
      <div className="card p-4">
        <h3 className="mb-3 text-sm font-semibold text-txt-hi">Task Details</h3>
        <div className="mb-2 flex items-center gap-2">
          <Badge tone={running ? 'blue' : 'green'} icon={running ? undefined : 'check'}>
            {running ? 'Running' : 'Completed'}
          </Badge>
          <span className="mono text-[11px] text-txt-dim">{task.id}</span>
        </div>
        <dl className="divide-y divide-line/70">
          <Detail label="Task" value={task.name} />
          <Detail label="Description" value={task.description} />
          <Detail label="Started" value={task.started} mono />
          <Detail label="Completed" value={running ? '—' : task.completed} mono />
          <Detail label="Duration" value={running ? '…' : task.duration} mono />
          <Detail label="Model" value={task.model} mono />
        </dl>
      </div>

      {/* Artifact */}
      <div>
        <div className="label pb-2">Generated artifact</div>
        <ArtifactCard artifact={artifact} />
      </div>

      {/* Execution steps */}
      <div className="card p-4">
        <h3 className="mb-3 text-sm font-semibold text-txt-hi">Execution Steps</h3>
        <ExecutionSteps steps={steps} running={running} />
      </div>

      {/* Security & Privacy */}
      <SecurityPanel />
    </div>
  )
}