import { useState } from 'react'
import { Icon } from './ui/Icon'

// Non-destructive error banner — surfaces trace errors and HTTP errors.
// Does not clear the trace or chat when dismissed.
export function ErrorBanner({ errors = [], onDismiss }) {
  if (!errors.length) return null

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 w-full max-w-md animate-slide-up" role="alert" aria-live="polite">
      {errors.map((err, idx) => (
        <div
          key={`${err.code}-${err.message}-${idx}`}
          className="card border-danger/40 bg-danger-soft/30 flex items-start gap-3 p-3"
        >
          <Icon name="alert" size={18} className="text-danger shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-medium text-danger">{err.code ?? 'ERROR'}</span>
              <button
                type="button"
                className="text-txt-low hover:text-txt-hi transition-colors"
                onClick={() => onDismiss?.(err)}
                aria-label="Dismiss error"
              >
                <Icon name="x" size={16} />
              </button>
            </div>
            <p className="mt-1 text-sm text-txt-hi">{err.message}</p>
            {err.details && Object.keys(err.details).length > 0 && (
              <details className="mt-2">
                <summary className="text-xs text-txt-low cursor-pointer">Details</summary>
                <pre className="mt-1 text-[10px] mono text-txt-mid bg-elevated p-2 rounded overflow-auto max-h-24">
                  {JSON.stringify(err.details, null, 2)}
                </pre>
              </details>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}