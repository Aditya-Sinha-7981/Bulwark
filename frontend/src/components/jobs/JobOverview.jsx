import { Icon } from '../ui/Icon.jsx'

function Stat({ label, value, tone }) {
  return (
    <div className="rounded-lg border border-line bg-elevated/40 px-3 py-2.5">
      <div className="text-xl font-semibold leading-tight text-txt-hi">{value}</div>
      <div className="flex items-center gap-1.5 text-[11px] text-txt-low">
        <span className={`h-1.5 w-1.5 rounded-full bg-current ${tone ?? 'text-txt-low'}`} />
        {label}
      </div>
    </div>
  )
}

export function JobOverview({ counts }) {
  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <Icon name="activity" size={16} className="text-accent" />
        <h3 className="text-sm font-semibold text-txt-hi">Job Overview</h3>
      </div>
      <div className="grid grid-cols-2 gap-2.5">
        <Stat label="Total Jobs" value={counts.total} />
        <Stat label="Completed" value={counts.completed} tone="text-ok" />
        <Stat label="Running" value={counts.running} tone="text-accent" />
        <Stat label="Failed" value={counts.failed} tone="text-danger" />
      </div>
    </div>
  )
}