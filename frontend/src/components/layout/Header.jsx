import { Icon } from '../ui/Icon.jsx'

const PAGE_META = {
  workbench: { title: 'Workbench', crumb: 'Workspace / Workbench' },
  documents: { title: 'Documents', crumb: 'Workspace / Documents' },
  jobs: { title: 'Jobs', crumb: 'Workspace / Jobs' },
  knowledge: { title: 'Knowledge', crumb: 'Workspace / Knowledge' },
  artifacts: { title: 'Created', crumb: 'Workspace / Created' },
  audit: { title: 'Audit', crumb: 'System / Audit' },
  settings: { title: 'Settings', crumb: 'System / Settings' },
}

export function Header({ page, onMenu, healthState }) {
  const meta = PAGE_META[page] ?? PAGE_META.workbench
  const connected = healthState === 'connected'

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-4 border-b border-line bg-ink/85 px-5 backdrop-blur lg:px-8">
      <button
        type="button"
        className="btn-quiet btn h-9 w-9 !px-0 lg:hidden"
        onClick={onMenu}
        aria-label="Open navigation"
      >
        <Icon name="menu" size={20} />
      </button>

      <div className="min-w-0 flex-1">
        <h1 className="truncate text-lg font-semibold text-txt-hi">{meta.title}</h1>
        <p className="mono truncate text-[11px] text-txt-dim">{meta.crumb}</p>
      </div>

      <div className="hidden items-center gap-2 sm:flex">
        {connected ? (
          <span className="pill border-ok/40 bg-ok-soft text-ok">
            <span className="h-1.5 w-1.5 rounded-full bg-current" />
            LOCAL &bull; SECURE
          </span>
        ) : (
          <span className="pill border-danger/40 bg-danger-soft text-danger">
            <span className="h-1.5 w-1.5 rounded-full bg-current" />
            BACKEND UNREACHABLE
          </span>
        )}
      </div>

      <div className="flex h-9 w-9 items-center justify-center rounded-full border border-line bg-surface text-xs font-semibold text-txt-mid">
        OP
      </div>
    </header>
  )
}