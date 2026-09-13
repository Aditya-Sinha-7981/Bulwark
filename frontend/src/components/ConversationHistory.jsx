import { useEffect, useRef, useState } from 'react'
import { listConversations } from '../services/api'
import { Icon } from './ui/Icon'

// Conversation history picker — lets the user resume a past conversation
// without losing it once the page navigates away from it. GET /api/v1/conversations.
export function ConversationHistory({ activeConversationId, onSelectConversation }) {
  const [open, setOpen] = useState(false)
  const [conversations, setConversations] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const containerRef = useRef(null)

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setLoading(true)
    setError(null)
    listConversations({ limit: 20 })
      .then((res) => {
        if (!cancelled) setConversations(res.conversations ?? [])
      })
      .catch((err) => {
        if (!cancelled) setError(err?.message ?? 'Failed to load conversations')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    const handleClickOutside = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [open])

  const handleSelect = (conversationId) => {
    onSelectConversation?.(conversationId)
    setOpen(false)
  }

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        className="btn-quiet btn text-txt-mid"
        onClick={() => setOpen((v) => !v)}
        aria-label="Conversation history"
        aria-expanded={open}
      >
        <Icon name="clock" size={14} />
        History
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-80 max-h-96 overflow-y-auto rounded-lg border border-line bg-surface shadow-lg z-20">
          <div className="px-3 py-2 border-b border-line text-xs font-medium text-txt-dim">
            Conversation history
          </div>
          {loading && (
            <div className="px-3 py-4 text-sm text-txt-dim text-center">Loading…</div>
          )}
          {error && (
            <div className="px-3 py-4 text-sm text-danger text-center">{error}</div>
          )}
          {!loading && !error && conversations.length === 0 && (
            <div className="px-3 py-4 text-sm text-txt-dim text-center">No conversations yet.</div>
          )}
          {!loading && !error && conversations.map((conv) => (
            <button
              key={conv.conversation_id}
              type="button"
              className={`w-full flex items-start gap-2 px-3 py-2 text-left text-sm hover:bg-elevated transition-colors ${
                conv.conversation_id === activeConversationId ? 'bg-band-soft' : ''
              }`}
              onClick={() => handleSelect(conv.conversation_id)}
            >
              <Icon name="activity" size={14} className="mt-0.5 shrink-0 text-txt-low" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-txt-hi">
                  {conv.preview ?? 'Empty conversation'}
                </p>
                <p className="text-[11px] text-txt-dim mono">
                  {new Date(conv.updated_at).toLocaleString()} · {conv.message_count} message{conv.message_count !== 1 ? 's' : ''}
                </p>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
