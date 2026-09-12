import { Icon } from '../ui/Icon.jsx'

export function ExecutionSteps({ steps, running }) {
  return (
    <ol className="relative space-y-0" aria-label="Execution steps">
      {steps.map((step, i) => {
        const done = step.state === 'done'
        const active = step.state === 'active'
        const last = i === steps.length - 1

        return (
          <li key={step.label} className="relative flex gap-3 pb-5 last:pb-0">
            {!last && (
              <span
                className={`absolute left-[9px] top-5 h-full w-px ${done || active ? 'bg-accent/40' : 'bg-line'}`}
                aria-hidden="true"
              />
            )}
            <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center">
              {done ? (
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-ok-soft text-ok">
                  <Icon name="check" size={12} />
                </span>
              ) : active ? (
                <span className="h-5 w-5 animate-pulse rounded-full border-2 border-accent" aria-hidden="true" />
              ) : (
                <span className="h-2.5 w-2.5 rounded-full border border-lineStrong bg-surface" aria-hidden="true" />
              )}
            </span>
            <div className="min-w-0 pt-0.5">
              <div className={`text-[13px] leading-tight ${done || active ? 'text-txt-hi' : 'text-txt-low'}`}>
                {step.label}
              </div>
              {active && running ? (
                <div className="mono mt-0.5 text-[11px] text-accent">in progress&hellip;</div>
              ) : (
                <div className="mono mt-0.5 text-[11px] text-txt-dim">{step.event}</div>
              )}
            </div>
          </li>
        )
      })}
    </ol>
  )
}