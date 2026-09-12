import { Icon } from '../ui/Icon.jsx'
import { DocCard } from './DocCard.jsx'
import { FollowUpComposer } from './FollowUpComposer.jsx'

const FOLLOW_UPS = [
  'Show financial highlights',
  'Compare with previous year',
  'Create a presentation',
  'Analyze risks',
]

const EMPTY_LABEL = 'Request received'

export default function TaskResult({ submission, result, running, onFollowUp }) {
  const { prompt, file } = submission
  const title = result?.title ?? EMPTY_LABEL

  return (
    <div className="space-y-5" data-testid="task-result">
      {/* User message card */}
      <div className="flex items-start gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent">
          <Icon name="workbench" size={16} />
        </div>
        <div className="min-w-0 flex-1 rounded-xl rounded-tl-sm border border-line bg-surface px-4 py-3">
          <p className="text-sm leading-relaxed text-txt-mid">{prompt}</p>
          {file && (
            <div className="mt-3">
              <DocCard file={file} />
            </div>
          )}
        </div>
      </div>

      {/* Assistant / result card */}
      <div className="flex items-start gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-ok-soft text-ok">
          <Icon name="shieldCheck" size={16} />
        </div>
        <div className="min-w-0 flex-1 rounded-xl rounded-tl-sm border border-line bg-surface px-5 py-4">
          {running ? (
            <div className="flex items-center gap-2 text-sm text-txt-mid">
              <span className="h-2 w-2 animate-pulse rounded-full bg-accent" aria-hidden="true" />
              Analyzing locally&hellip;
            </div>
          ) : (
            <>
              <h3 className="text-[15px] font-semibold text-txt-hi">{title}</h3>
              {result?.summary && <p className="mt-2 text-sm leading-relaxed text-txt-mid">{result.summary}</p>}
              {result?.points && (
                <div className="mt-4">
                  <div className="label pb-2">Key points</div>
                  <ol className="space-y-2">
                    {result.points.map((point, i) => (
                      <li key={i} className="flex items-start gap-2.5 text-sm leading-relaxed text-txt-mid">
                        <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-accent-soft text-[11px] font-semibold text-accent">
                          {i + 1}
                        </span>
                        {point}
                      </li>
                    ))}
                  </ol>
                </div>
              )}
              {result?.artifact && (
                <div className="mt-4">
                  <div className="label pb-2">Generated artifact</div>
                  <div className="flex items-center gap-3 rounded-lg border border-band/40 bg-band-soft px-4 py-3">
                    <Icon name="artifacts" size={18} className="text-band" />
                    <div className="text-sm font-medium text-txt-hi">{result.artifact.name}</div>
                    <div className="flex items-center gap-1 text-txt-low">
                      <Icon name="download" size={14} />
                      <span className="mono text-[11px]">{result.artifact.size}</span>
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Suggested follow-ups */}
      {!running && (
        <>
          <div>
            <div className="label pb-2">Suggested follow-ups</div>
            <div className="flex flex-wrap gap-2">
              {FOLLOW_UPS.map((label) => (
                <button
                  key={label}
                  type="button"
                  onClick={() => onFollowUp(label)}
                  className="btn mr-1 border-line bg-transparent text-txt-mid hover:border-accent/50 hover:text-accent"
                >
                  <Icon name="plus" size={14} />
                  {label}
                </button>
              ))}
            </div>
          </div>
          <FollowUpComposer onSend={onFollowUp} />
        </>
      )}
    </div>
  )
}