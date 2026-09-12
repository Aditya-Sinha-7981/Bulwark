// Centralized API layer.
// Every network call in the frontend must live in this module —
// do not call fetch() from components or hooks.
// All targets are the local Bulwark backend (loopback only).

const BASE_URL = 'http://127.0.0.1:8000'
const API_ROOT = `${BASE_URL}/api/v1`

export class ApiError extends Error {
  constructor(status, message, url, details = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.url = url
    this.details = details
  }
}

async function request(path, options = {}) {
  let response
  try {
    response = await fetch(`${API_ROOT}${path}`, options)
  } catch (err) {
    // Network-level failure (backend down, connection refused, CORS blocked).
    // Re-thrown as-is; callers treat any thrown error as "backend unreachable".
    throw err
  }

  if (!response.ok) {
    let message = `Request failed with HTTP ${response.status}`
    let details = {}
    try {
      const body = await response.json()
      if (body && body.error && body.error.message) {
        message = body.error.message
      }
      if (body && body.error && body.error.details) {
        details = body.error.details
      }
    } catch {
      // non-JSON body — keep the generic message
    }
    throw new ApiError(response.status, message, response.url, details)
  }

  if (response.status === 204) {
    return null
  }

  return response.json()
}

// ---- Health ---------------------------------------------------------------

export async function getHealth() {
  return request('/health')
}

// ---- Conversations --------------------------------------------------------

// POST /api/v1/conversations — create a new conversation.
export async function createConversation() {
  return request('/conversations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  })
}

// GET /api/v1/conversations/{conversation_id} — conversation with messages.
export async function getConversation(conversationId) {
  return request(`/conversations/${conversationId}`)
}

// ---- Jobs -----------------------------------------------------------------

// POST /api/v1/jobs — create a Job. Requires an existing conversation_id.
export async function createJob({ conversationId, message, documentIds = [] }) {
  return request('/jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      conversation_id: conversationId,
      message,
      document_ids: documentIds,
    }),
  })
}

// GET /api/v1/jobs/{job_id} — current Job state.
export async function getJob(jobId) {
  return request(`/jobs/${jobId}`)
}

// GET /api/v1/jobs/{job_id}/trace — full filtered Audit event trace.
export async function getJobTrace(jobId) {
  return request(`/jobs/${jobId}/trace`)
}

// GET /api/v1/jobs/{job_id}/events — live SSE stream (see hooks/useJobEvents.js).
export function jobEventsUrl(jobId) {
  return `${API_ROOT}/jobs/${jobId}/events`
}

// ---- Documents ------------------------------------------------------------

// POST /api/v1/documents — upload a file (multipart) for later reference by a Job.
export async function uploadDocument(file) {
  const formData = new FormData()
  formData.append('file', file)
  return request('/documents', {
    method: 'POST',
    body: formData,
    // Do NOT set Content-Type — let the browser set it with the boundary for multipart
  })
}

// GET /api/v1/documents/{document_id} — metadata for an uploaded document.
export async function getDocument(documentId) {
  return request(`/documents/${documentId}`)
}

// ---- Artifacts ------------------------------------------------------------

// GET /api/v1/artifacts/{artifact_id} — artifact metadata.
export async function getArtifact(artifactId) {
  return request(`/artifacts/${artifactId}`)
}

// GET /api/v1/artifacts/{artifact_id}/download — raw file bytes.
export function artifactDownloadUrl(artifactId) {
  return `${API_ROOT}/artifacts/${artifactId}/download`
}

// ---- Knowledge Base -------------------------------------------------------

// GET /api/v1/knowledge-base — list ingested knowledge-base documents.
export async function getKnowledgeBase() {
  return request('/knowledge-base')
}

// POST /api/v1/knowledge-base/documents — ingest a document into the local knowledge base.
export async function ingestKnowledgeDocument(file, metadata = {}) {
  const formData = new FormData()
  formData.append('file', file)
  if (Object.keys(metadata).length > 0) {
    formData.append('metadata', JSON.stringify(metadata))
  }
  return request('/knowledge-base/documents', {
    method: 'POST',
    body: formData,
  })
}

// DELETE /api/v1/knowledge-base/documents/{kb_document_id} — remove a document.
export async function deleteKnowledgeDocument(kbDocumentId) {
  return request(`/knowledge-base/documents/${kbDocumentId}`, {
    method: 'DELETE',
  })
}

// ---- Network status -------------------------------------------------------

// GET /api/v1/network-status — sovereignty proof used by the security indicator.
export async function getNetworkStatus() {
  return request('/network-status')
}