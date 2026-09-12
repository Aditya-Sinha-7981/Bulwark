import { Icon } from '../ui/Icon.jsx'

// SIH Demo: Workbench-only sidebar
const NAV_ITEMS = [
  { id: 'workbench', label: 'Workbench', icon: 'workbench' },
]

export function Sidebar({ current, onNavigate, open, onClose, healthState }) {
  const connected = healthState === 'connected'

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-line bg-panel transition-transform lg:translate-x-0 ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
        aria-label="Primary"
      >
        {/* Brand */}
        <div className="flex items-center gap-3 border-b border-line px-5 py-4">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent-strong text-white">
            <Icon name="shieldCheck" size={20} />
          </div>
          <div className="leading-tight">
            <div className="text-[15px] font-semibold tracking-wide text-txt-hi">Bulwark</div>
            <div className="mono text-[10px] uppercase tracking-[0.24em] text-txt-dim">Private AI</div>
          </div>
        </div>

        {/* Navigation - Workbench only for SIH demo */}
        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4" aria-label="Main">
          <div className="label px-2 pb-2">Workspace</div>
          {NAV_ITEMS.map((item) => {
            const active = current === item.id
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => {
                  onNavigate(item.id)
                  onClose()
                }}
                aria-current={active ? 'page' : undefined}
                className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                  active
                    ? 'bg-accent-soft font-medium text-accent'
                    : 'text-txt-mid hover:bg-elevated hover:text-txt-hi'
                }`}
              >
                <Icon name={item.icon} size={18} className={active ? 'text-accent' : ''} />
                {item.label}
                {active && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-accent" />}
              </button>
            )
          })}
        </nav>

        {/* Connection card */}
        <div className="border-t border-line p-3">
          <div
            className={`rounded-lg border px-3 py-2.5 ${
              connected ? 'border-ok/30 bg-ok-soft/60' : 'border-danger/30 bg-danger-soft'
            }`}
          >
            <div className="flex items-center gap-2">
              <span
                className={`h-2 w-2 rounded-full ${
                  connected ? 'bg-ok shadow-[0_0_8px_theme(colors.ok.DEFAULT)]' : 'bg-danger shadow-[0_0_8px_theme(colors.danger.DEFAULT)]'
                }`}
                aria-hidden="true"
              />
              <span className="mono text-[11px] font-semibold tracking-widest text-txt-hi">
                {connected ? 'NODE • CONNECTED' : 'NODE • OFFLINE'}
              </span>
            </div>
            <div className="mt-1 text-[11px] leading-snug text-txt-low">
              {connected ? 'Local backend on 127.0.0.1:8000' : 'Backend unreachable'}
            </div>
          </div>
        </div>
      </aside>
    </>
  )
}