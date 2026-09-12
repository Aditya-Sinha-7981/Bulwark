import { Icon } from '../ui/Icon.jsx'

const ITEMS = [
  { label: 'Processed locally', icon: 'node', tone: 'text-ok', detail: 'CPU/GPU on this machine' },
  { label: 'No external network calls', icon: 'activity', tone: 'text-ok', detail: 'Loopback only' },
  { label: 'Data stays on this machine', icon: 'server', tone: 'text-ok', detail: 'Air-gapped by design' },
  { label: 'Encrypted in transit (local)', icon: 'lock', tone: 'text-ok', detail: '127.0.0.1:8000' },
]

export function SecurityPanel() {
  return (
    <div className="card p-4">
      <div className="mb-3 flex items-center gap-2">
        <Icon name="shieldCheck" size={16} className="text-ok" />
        <h3 className="text-sm font-semibold text-txt-hi">Security &amp; Privacy</h3>
      </div>
      <ul className="space-y-2.5">
        {ITEMS.map((item) => (
          <li key={item.label} className="flex items-start gap-2.5">
            <Icon name={item.icon} size={15} className={`mt-0.5 ${item.tone}`} />
            <div>
              <div className="text-[13px] text-txt-mid">{item.label}</div>
              <div className="mono text-[11px] text-txt-dim">{item.detail}</div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}