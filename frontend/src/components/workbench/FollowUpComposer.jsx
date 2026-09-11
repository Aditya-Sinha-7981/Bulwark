import { useState } from 'react'
import { Icon } from '../ui/Icon.jsx'
import { KB_SOURCES } from '../../data/mockJobs.js'

export function FollowUpComposer({ disabled, onSend }) {
  const [text, setText] = useState('')

  const handleSend = () => {
    if (!text.trim() || disabled) return
    onSend(text)
    setText('')
  }

  return (
    <div className="flex items-center gap-2 rounded-xl border border-line bg-panel px-3 py-2">
      <button
        type="button"
        className="btn-quiet btn h-8 w-8 !px-0 text-txt-low"
        aria-label="Attach a file"
        disabled={disabled}
      >
        <Icon name="paperclip" size={15} />
      </button>

      <select
        aria-label="Knowledge base"
        className="h-8 rounded-md border border-line bg-panel px-2 text-xs text-txt-mid focus:border-accent/60 focus:outline-none"
        defaultValue={KB_SOURCES[0].id}
      >
        {KB_SOURCES.map((s) => (
          <option key={s.id} value={s.id}>
            {s.label}
          </option>
        ))}
      </select>

      <input
        type="text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') handleSend()
        }}
        placeholder="Follow up on this task..."
        aria-label="Follow up message"
        disabled={disabled}
        className="h-8 min-w-0 flex-1 bg-transparent text-sm text-txt-hi placeholder:text-txt-dim focus:outline-none"
      />

      <button
        type="button"
        className="btn-primary !h-8"
        onClick={handleSend}
        disabled={disabled || !text.trim()}
      >
        <Icon name="send" size={14} />
      </button>
    </div>
  )
}