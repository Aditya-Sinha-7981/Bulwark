import { useState, useEffect, useRef } from 'react'
import { useApiMutation } from '../hooks/useApi'
import { createConversation, getConversation, createJob } from '../services/api'
import { UploadButton } from './UploadButton'
import { DocumentPicker } from './DocumentPicker'
import { Icon } from './ui/Icon'
import { ErrorBanner } from './ErrorBanner'

// The backend embeds "[Attached document(s): document_id=<uuid>, ...]" into
// the persisted message content itself — it's the only channel the
// Orchestrator has to learn which documents to pass into extract_document's
// arguments (backend/domain/job_manager/manager.py). That's necessary for
// the model's prompt, but showing the raw note verbatim in a chat bubble is
// not — split it out here so the UI can render a clean attachment chip
// instead of a paragraph of raw UUIDs.
const ATTACHMENT_NOTE_RE = /\n\n\[Attached document\(s\): ((?:document_id=[0-9a-f-]+(?:, )?)+)\]$/i

function splitAttachmentNote(content) {
  const match = content.match(ATTACHMENT_NOTE_RE)
  if (!match) return { text: content, documentIds: [] }
  const documentIds = match[1].match(/[0-9a-f-]{36}/gi) ?? []
  return { text: content.slice(0, match.index), documentIds }
}

// Chat panel — message history + input + file upload.
// On submit: ensures conversation exists, creates Job, returns jobId.
// `job` (optional): the current Job's state from GET /jobs/{id}, as polled by
// the parent — used to know when to refetch history so the orchestrator's
// final_message (persisted server-side as a conversation message on job
// completion, backend/domain/job_manager/manager.py) actually shows up as a
// chat bubble instead of only existing in the trace panel.
export function ChatPanel({ onJobCreated, onConversationCreated, conversationId: initialConversationId, job }) {
  const [conversationId, setConversationId] = useState(initialConversationId ?? null)
  const [messages, setMessages] = useState([])
  const [inputValue, setInputValue] = useState('')
  const [attachedDocumentIds, setAttachedDocumentIds] = useState([])
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [errors, setErrors] = useState([])
  const [refreshKey, setRefreshKey] = useState(0)
  const messagesEndRef = useRef(null)
  const settledJobIdRef = useRef(null)

  const { mutate: createConv, loading: creatingConv } = useApiMutation(createConversation)
  const { mutate: createJobMutation, loading: creatingJob } = useApiMutation(createJob)

  // Load conversation history whenever conversationId changes, or a refresh
  // is requested (job created / job settled — see effect below).
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
  }, [conversationId, refreshKey])

  // Refetch when the active job reaches a terminal state, so the
  // orchestrator's final_message (appended as a conversation message on the
  // backend at completion time) appears as a chat bubble. Guarded by
  // settledJobIdRef so a single completed job only triggers this once.
  //
  // The backend updates the Job row to status="completed" BEFORE appending
  // the orchestrator's message to the conversation (two sequential DB calls
  // in backend/domain/job_manager/manager.py, no transaction between them) —
  // a poll that lands in that gap sees "completed" with the message not yet
  // there. Observed live: the first refetch's response had only the user's
  // message even though the job was already "completed". A second refetch
  // shortly after closes that window without depending on backend ordering.
  useEffect(() => {
    if (!job || (job.status !== 'completed' && job.status !== 'failed')) return
    if (settledJobIdRef.current === job.job_id) return
    settledJobIdRef.current = job.job_id
    setRefreshKey((k) => k + 1)
    const retryTimer = setTimeout(() => setRefreshKey((k) => k + 1), 1500)
    return () => clearTimeout(retryTimer)
  }, [job])

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
        // Lift the new conversation_id to the parent (Workbench) — it owns
        // the `conversationId` it hands back down as a prop, and without
        // this it stays null there forever, so the next mount of ChatPanel
        // (e.g. when Workbench switches from its empty-state layout to the
        // active chat+trace layout on job creation) starts with no
        // conversation and never fetches history (Task 17 integration
        // finding: chat history/final answer never appeared in the browser).
        onConversationCreated?.(convId)
      }

      const createdJob = await createJobMutation({
        conversationId: convId,
        message,
        documentIds: attachedDocumentIds,
      })

      setAttachedDocumentIds([])
      settledJobIdRef.current = null
      // Refetch history so the user's own message (persisted server-side as
      // part of Job creation) shows up immediately rather than only on the
      // next terminal-state refresh.
      setRefreshKey((k) => k + 1)
      onJobCreated?.(createdJob.job_id)
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
            {messages.map((msg, idx) => {
              const { text, documentIds } = splitAttachmentNote(msg.content)
              return (
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
                      {text}
                    </div>
                    {documentIds.length > 0 && (
                      <div className={`mt-1 flex flex-wrap gap-1 ${msg.role === 'user' ? 'justify-end' : ''}`}>
                        {documentIds.map((docId) => (
                          <span
                            key={docId}
                            className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-band-soft text-band text-[11px]"
                          >
                            <Icon name="file" size={11} />
                            {docId.slice(0, 8)}…
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="mt-1 text-[10px] text-txt-dim mono">
                      {new Date(msg.created_at ?? msg.timestamp).toLocaleTimeString()}
                    </div>
                  </div>
                </div>
              )
            })}
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
            <DocumentPicker onSelectDocument={handleAttachDocument} disabled={loading} />
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