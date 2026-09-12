import { Badge } from '../ui/Badge.jsx'
import { Icon } from '../ui/Icon.jsx'

const STATUS_META = {
  completed: { tone: 'green' },
  running: { tone: 'blue' },
  waiting: { tone: 'gray' },
  failed: { tone: 'red' },
}

function StatusCell({ status }) {
  const meta = STATUS_META[status] ?? STATUS_META.waiting
  return <Badge tone={meta.tone}>{status}</Badge>
}

function ResultCell({ result }) {
  const isArtifact = /\.(docx|xlsx|md)$/i.test(result)
  return (
    <span className="inline-flex items-center gap-1.5 text-[13px] text-txt-mid">
      {isArtifact && <Icon name="artifacts" size={13} className="text-band" />}
      {result}
    </span>
  )
}

export function JobsTable({ jobs, onSelect, onRun }) {
  return (
    <div className="card overflow-x-auto">
      <table className="w-full min-w-[760px] text-left">
        <thead>
          <tr className="border-b border-line text-[11px] uppercase tracking-wider text-txt-dim">
            <th className="px-4 py-3 font-medium">Task</th>
            <th className="px-4 py-3 font-medium">Status</th>
            <th className="px-4 py-3 font-medium">Started</th>
            <th className="px-4 py-3 font-medium">Duration</th>
            <th className="px-4 py-3 font-medium">Result</th>
            <th className="px-4 py-3 font-medium">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line/60">
          {jobs.map((job) => (
            <tr
              key={job.id}
              className="cursor-pointer transition-colors hover:bg-elevated/50"
              onClick={() => onSelect(job)}
            >
              <td className="px-4 py-3">
                <div className="flex items-center gap-2.5">
                  {job.hasFile && <Icon name="paperclip" size={13} className="shrink-0 text-txt-dim" />}
                  <span className="text-sm font-medium text-txt-hi">{job.task}</span>
                </div>
              </td>
              <td className="px-4 py-3">
                <StatusCell status={job.status} />
              </td>
              <td className="px-4 py-3">
                <span className="mono text-xs text-txt-low">{formatStarted(job.started)}</span>
              </td>
              <td className="px-4 py-3">
                <span className="mono text-xs text-txt-low">{job.duration}</span>
              </td>
              <td className="px-4 py-3">
                <ResultCell result={job.result} />
              </td>
              <td className="px-4 py-3">
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    className="btn-quiet btn h-7 !px-2 text-xs"
                    aria-label={`Open ${job.task}`}
                    onClick={(e) => {
                      e.stopPropagation()
                      onSelect(job)
                    }}
                  >
                    Open
                  </button>
                  <button
                    type="button"
                    className="btn-quiet btn h-7 !px-2 text-xs"
                    aria-label={`Run ${job.task} again`}
                    onClick={(e) => {
                      e.stopPropagation()
                      onRun(job)
                    }}
                  >
                    <Icon name="refresh" size={13} />
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function formatStarted(iso) {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}