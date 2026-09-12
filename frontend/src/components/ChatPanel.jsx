import { useState, useEffect, useRef } from 'react'
import { useApiMutation } from '../hooks/useApi'
import { createConversation, getConversation, createJob } from '../services/api'
import { UploadButton } from './UploadButton'
import { Icon } from './ui/Icon'
import { ErrorBanner } from './ErrorBanner'

// Chat panel — message history + input + file upload.
// On submit: ensures conversation exists, creates Job, returns jobId.
export function ChatPanel({ onJobCreated, conversationId: initialConversationId }) {
  const [conversationId, setConversationId] = useState(initialConversationId ?? null)
  const [messages, setMessages] = useState([])
  const [inputValue, setInputValue] = useState('')
  const [attachedDocumentIds, setAttachedDocumentIds] = useState([])
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [errors, setErrors] = useState([])
  const messagesEndRef = useRef(null)

  const { mutate: createConv, loading: creatingConv } = useApiMutation(createConversation)
  const { mutate: createJobMutation, loading: creatingJob } = useApiMutation(createJob)

  // Load conversation history when conversationId changes
  useEffect(() => {
    if (!conversationId) return
    setLoadingHistory(true)
    getConversation(conversationId)
      .then((conv) => {
        setMessages(conv.messages ?? [])
      })
      .catch((err) => {
        setErrors((prev) => [...prev, { code: err.status, message: err.message, details: err.details }])
      })
      .finally(() => setLoadingHistory(false))
  }, [conversationId])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const handleAttachDocument = (doc) => {
    if (doc) {
      setAttachedDocumentIds((prev) => [...prev, doc.document_id])
    }
  }

  const handleRemoveDocument = (docId) => {
    setAttachedDocumentIds((prev) => prev.filter((id) => id !== docId))
  }

  const handleSubmit = async (e) => {
    e?.preventDefault()
    if (!inputValue.trim() && !attachedDocumentIds.length) return
    if (creatingConv || creatingJob) return

    const message = inputValue.trim()
    setInputValue('')

    try {
      let convId = conversationId
      if (!convId) {
        const conv = await createConv()
        convId = conv.conversation_id
        setConversationId(convId)
      }

      const job = await createJobMutation({
        conversationId: convId,
        message,
        documentIds: attachedDocumentIds,
      })

      setAttachedDocumentIds([])
      onJobCreated?.(job.job_id)
    } catch (err) {
      setErrors((prev) => [...prev, { code: err.status, message: err.message, details: err.details }])
    }
  }

  const dismissError = (err) => {
    setErrors((prev) => prev.filter((e) => e !== err))
  }

  const loading = creatingConv || creatingJob || loadingHistory

  return (
    <div className="card flex flex-col h-full min-h-0">
      {/* Header */}
      <div className="px-4 py-3 border-b border-line flex items-center justify-between">
        <h3 className="text-sm font-semibold text-txt-hi">Conversation</h3>
        <div className="flex items-center gap-2">
          {conversationId && (
            <span className="mono text-[11px] text-txt-dim">{conversationId.slice(0, 8)}…</span>
          )}
          {creatingConv && <span className="text-xs text-accent">Creating conversation…</span>}
        </div>
      </div>

      {/* Error Banner */}
      <ErrorBanner errors={errors} onDismiss={dismissError} />

      {/* Message History */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4" aria-live="polite">
        {loadingHistory && messages.length === 0 ? (
          <div className="flex items-center justify-center h-full text-txt-low">Loading history…</div>
        ) : messages.length === 0 ? (
          <div className="flex items-center justify-center h-full text-txt-dim">
            No messages yet. Start the conversation below.
          </div>
        ) : (
          <>
            {messages.map((msg, idx) => (
              <div
                key={msg.message_id ?? idx}
                className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
              >
                <div
                  className={`flex-1 max-w-[80%] ${msg.role === 'user' ? 'text-right' : ''}`}
                >
                  <div
                    className={`inline-block px-4 py-2 rounded-2xl text-sm ${
                      msg.role === 'user'
                        ? 'bg-accent-soft text-accent rounded-tr-none'
                        : 'bg-elevated text-txt-hi rounded-tl-none'
                    }`}
                  >
                    {msg.content}
                  </div>
                  <div className="mt-1 text-[10px] text-txt-dim mono">
                    {new Date(msg.timestamp).toLocaleTimeString()}
                  </div>
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* Attached Documents */}
      {attachedDocumentIds.length > 0 && (
        <div className="px-4 pb-2 border-b border-line">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-txt-dim">Attached:</span>
            {attachedDocumentIds.map((docId) => (
              <span
                key={docId}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-band-soft text-band"
              >
                <Icon name="file" size={12} />
                {docId.slice(0, 8)}…
                <button
                  type="button"
                  className="ml-1 text-band hover:text-danger"
                  onClick={() => handleRemoveDocument(docId)}
                  aria-label="Remove attachment"
                >
                  <Icon name="x" size={10} />
                </button>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Input Area */}
      <div className="p-4 border-t border-line">
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <div className="flex items-end gap-2">
            <textarea
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              rows={3}
              placeholder="Ask a question, analyze confidential files, or run local tasks…"
              className="input flex-1 resize-none pr-12"
              disabled={loading}
              aria-label="Prompt"
            />
            <UploadButton onDocumentUploaded={handleAttachDocument} disabled={loading} />
          </div>

          <div className="flex items-center justify-between">
            <span className="mono text-[11px] text-txt-dim hidden md:flex">
              <span className="rounded border border-line px-1">Ctrl</span>
              <span className="rounded border border-line px-1">Enter</span>
              to send
            </span>
            <button
              type="submit"
              className="btn-primary h-9 w-9 !px-0 rounded-full flex items-center justify-center disabled:opacity-50"
              disabled={loading || (!inputValue.trim() && !attachedDocumentIds.length)}
              aria-label="Send message"
            >
              <Icon name="send" size={18} className="text-white" />
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}