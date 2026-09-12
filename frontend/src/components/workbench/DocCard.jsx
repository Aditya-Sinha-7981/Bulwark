import { Icon } from '../ui/Icon.jsx'

export function DocCard({ file }) {
  if (!file) return null
  return (
    <div className="flex items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3">
      <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-band/40 bg-band-soft text-band">
        <Icon name="file" size={20} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium text-txt-hi">{file.name}</div>
        <div className="text-xs text-txt-low">
          {file.size} &bull; {file.type}
        </div>
      </div>
      <span className="badge-purple">Encrypted</span>
    </div>
  )
}