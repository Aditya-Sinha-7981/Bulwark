import { Icon } from '../ui/Icon.jsx'

export function StatusBar({ healthState }) {
  const connected = healthState === 'connected'

  return (
    <footer className="flex h-9 shrink-0 items-center gap-4 border-t border-line bg-panel px-5 text-[11px] text-txt-low lg:px-8">
      <span className="flex items-center gap-1.5">
        <span
          className={`h-1.5 w-1.5 rounded-full ${connected ? 'bg-ok' : 'bg-danger'}`}
          aria-hidden="true"
        />
        {connected ? 'Local backend connected' : 'Backend unreachable'}
      </span>
      <span className="hidden items-center gap-1.5 sm:flex">
        <Icon name="lock" size={12} className="text-ok" />
        Zero external egress enforced
      </span>
      <span className="mono ml-auto hidden text-txt-dim md:inline">
        {connected ? '127.0.0.1:8000 • loopback only' : 'no connection • offline'}
      </span>
    </footer>
  )
}