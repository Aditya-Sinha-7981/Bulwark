import { Icon } from '../ui/Icon.jsx'

const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'completed', label: 'Completed' },
  { id: 'running', label: 'Running' },
  { id: 'failed', label: 'Failed' },
]

export function JobFilters({ filter, onFilter, search, onSearch }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex items-center gap-1 rounded-lg border border-line bg-panel p-1">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            onClick={() => onFilter(f.id)}
            aria-pressed={filter === f.id}
            className={`rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors ${
              filter === f.id ? 'bg-accent-soft text-accent' : 'text-txt-mid hover:text-txt-hi'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="relative min-w-[200px] flex-1 sm:max-w-xs">
        <Icon
          name="search"
          size={15}
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-txt-dim"
        />
        <input
          type="search"
          value={search}
          onChange={(e) => onSearch(e.target.value)}
          placeholder="Search tasks…"
          aria-label="Search tasks"
          className="input !pl-9"
        />
      </div>
    </div>
  )
}