import { Icon } from '../ui/Icon.jsx'

const STATUS_ICON = {
  completed: { icon: 'check', class: 'bg-ok-soft text-ok' },
  running: { icon: 'activity', class: 'bg-accent-soft text-accent' },
  failed: { icon: 'x', class: 'bg-danger-soft text-danger' },
}

export function RecentActivity({ items }) {
  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <Icon name="clock" size={16} className="text-accent" />
        <h3 className="text-sm font-semibold text-txt-hi">Recent Activity</h3>
      </div>
      <ul className="space-y-3">
        {items.map((item) => {
          const meta = STATUS_ICON[item.status] ?? STATUS_ICON.completed
          return (
            <li key={item.id} className="flex items-start gap-2.5">
              <span className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md ${meta.class}`}>
                <Icon name={meta.icon} size={13} />
              </span>
              <div className="min-w-0">
                <div className="truncate text-[13px] leading-tight text-txt-mid">{item.label}</div>
                <div className="mono mt-0.5 text-[11px] text-txt-dim">{item.at}</div>
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}