export function PageHeader({ title, description, children }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight text-txt-hi">{title}</h2>
        {description && <p className="mt-1 text-sm text-txt-low">{description}</p>}
      </div>
      {children}
    </div>
  )
}