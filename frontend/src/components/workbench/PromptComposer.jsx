import { useRef, useState } from 'react'
import { Icon } from '../ui/Icon.jsx'
import { KB_SOURCES } from '../../data/mockJobs.js'

export function PromptComposer({ value, onChange, onSubmit, onAttach, attachedFile }) {
  const [kbOpen, setKbOpen] = useState(false)
  const [kb, setKb] = useState(KB_SOURCES[0].id)
  const [hovered, setHovered] = useState(false)
  const textareaRef = useRef(null)
  const fileInputRef = useRef(null)
  const kbLabel = KB_SOURCES.find((s) => s.id === kb)?.label ?? KB_SOURCES[0].label
  const hasContent = value.trim().length > 0 || attachedFile

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault()
      if (hasContent) onSubmit()
    }
  }

  const handlePickFile = (e) => {
    const file = e.target.files?.[0] ?? null
    if (file) onAttach({
      name: file.name,
      size: formatBytes(file.size),
      type: file.type.split('/').pop().toUpperCase() || 'FILE',
    })
    e.target.value = ''
  }

  return (
    <div className="card overflow-hidden relative" onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}>
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        rows={3}
        placeholder="Ask a question, analyze confidential files, or run local tasks..."
        aria-label="Prompt"
        className="w-full resize-none bg-transparent px-5 py-4 text-[15px] text-txt-hi placeholder:text-txt-dim focus:outline-none pr-16"
      />

      {attachedFile && (
        <div className="px-5 pb-2">
          <div className="inline-flex items-center gap-2 rounded-lg border border-band/40 bg-band-soft px-3 py-1.5 text-sm">
            <Icon name="file" size={14} className="text-band" />
            <span className="text-txt-hi">{attachedFile.name}</span>
            <span className="text-xs text-txt-low">
              {attachedFile.size} &bull; {attachedFile.type}
            </span>
            <button
              type="button"
              className="ml-1 text-txt-low transition-colors hover:text-danger"
              onClick={() => onAttach(null)}
              aria-label={`Remove ${attachedFile.name}`}
            >
              <Icon name="x" size={14} />
            </button>
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 border-t border-line px-4 py-2.5">
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          onChange={handlePickFile}
          aria-label="Attach a file"
        />
        <button
          type="button"
          className="btn-quiet btn text-txt-mid"
          onClick={() => fileInputRef.current?.click()}
        >
          <Icon name="paperclip" size={15} />
          Attach file
        </button>

        <div className="relative">
          <button
            type="button"
            className="btn-quiet btn text-txt-mid"
            onClick={() => setKbOpen((o) => !o)}
            aria-haspopup="listbox"
            aria-expanded={kbOpen}
          >
            <Icon name="knowledge" size={15} />
            {kbLabel}
            <Icon name="chevronDown" size={14} />
          </button>

          {kbOpen && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setKbOpen(false)} aria-hidden="true" />
              <ul
                role="listbox"
                aria-label="Knowledge base"
                className="absolute left-0 top-full z-20 mt-1 w-56 overflow-hidden rounded-lg border border-line bg-panel shadow-xl"
              >
                {KB_SOURCES.map((source) => (
                  <li key={source.id}>
                    <button
                      type="button"
                      role="option"
                      aria-selected={kb === source.id}
                      className={`flex w-full items-center gap-2 px-3 py-2 text-sm transition-colors ${
                        kb === source.id ? 'bg-accent-soft text-accent' : 'text-txt-mid hover:bg-elevated hover:text-txt-hi'
                      }`}
                      onClick={() => {
                        setKb(source.id)
                        setKbOpen(false)
                      }}
                    >
                      {kb === source.id && <Icon name="check" size={14} />}
                      {source.label}
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>

        <span className="mono ml-auto hidden items-center gap-1 text-[11px] text-txt-dim md:flex">
          <span className="rounded border border-line px-1">Ctrl</span>
          <span className="rounded border border-line px-1">Enter</span>
          to run
        </span>

        <button
          type="button"
          className="btn-primary ml-auto h-9 w-9 !px-0 rounded-full transition-all duration-150 hover:bg-accent hover:shadow-[0_0_12px_theme(colors.accent.DEFAULT/40)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 disabled:opacity-50 disabled:pointer-events-none flex items-center justify-center"
          onClick={onSubmit}
          disabled={!hasContent}
          aria-label="Run prompt"
        >
          <Icon name="send" size={18} className="text-white" />
        </button>
      </div>
    </div>
  )
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / 1024 ** i).toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}