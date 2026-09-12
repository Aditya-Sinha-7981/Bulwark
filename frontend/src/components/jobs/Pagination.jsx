import { Icon } from '../ui/Icon.jsx'

export function Pagination({ page, pageSize, total, onPage, onPageSize }) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1
  const to = Math.min(page * pageSize, total)

  const pages = []
  for (let i = 1; i <= pageCount; i++) {
    if (i === 1 || i === pageCount || Math.abs(i - page) <= 1) {
      pages.push(i)
    } else if (pages[pages.length - 1] !== '…') {
      pages.push('…')
    }
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <span className="text-xs text-txt-low">
        Showing {from}–{to} of {total} jobs
      </span>

      <div className="flex items-center gap-1">
        <button
          type="button"
          className="btn-quiet btn h-8 w-8 !px-0"
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
          aria-label="Previous page"
        >
          <Icon name="arrowLeft" size={14} />
        </button>

        {pages.map((p, i) =>
          p === '…' ? (
            <span key={`e-${i}`} className="px-2 text-xs text-txt-dim">
              …
            </span>
          ) : (
            <button
              key={p}
              type="button"
              onClick={() => onPage(p)}
              aria-current={p === page ? 'page' : undefined}
              className={`btn h-8 w-8 !px-0 text-xs ${
                p === page ? 'bg-accent-soft text-accent' : 'text-txt-mid hover:text-txt-hi'
              }`}
            >
              {p}
            </button>
          )
        )}

        <button
          type="button"
          className="btn-quiet btn h-8 w-8 !px-0"
          disabled={page >= pageCount}
          onClick={() => onPage(page + 1)}
          aria-label="Next page"
        >
          <Icon name="arrowRight" size={14} />
        </button>
      </div>

      <label className="flex items-center gap-2 text-xs text-txt-low">
        Rows per page
        <select
          value={pageSize}
          onChange={(e) => onPageSize(Number(e.target.value))}
          aria-label="Rows per page"
          className="h-8 rounded-md border border-line bg-panel px-2 text-xs text-txt-mid focus:outline-none"
        >
          <option value={5}>5</option>
          <option value={10}>10</option>
          <option value={25}>25</option>
        </select>
      </label>
    </div>
  )
}