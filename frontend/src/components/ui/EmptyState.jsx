import { Icon } from './Icon.jsx'

export function EmptyState({ icon, title, description, action }) {
  return (
    <div className="card flex min-h-[320px] flex-col items-center justify-center gap-2 px-6 py-12 text-center">
      <div className="mb-1 flex h-12 w-12 items-center justify-center rounded-xl border border-line bg-elevated text-txt-low">
        <Icon name={icon} size={22} />
      </div>
      <h3 className="text-base font-semibold text-txt-hi">{title}</h3>
      {description && (
        <p className="max-w-md text-sm leading-relaxed text-txt-low">{description}</p>
      )}
      {action}
    </div>
  )
}