// Centralized API layer.
// Every network call in the frontend must live in this module —
// do not call fetch() from components or hooks.
// All targets are the local Bulwark backend (loopback only).

const BASE_URL = 'http://127.0.0.1:8000'
const API_ROOT = `${BASE_URL}/api/v1`

export class ApiError extends Error {
  constructor(status, message, url) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.url = url
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
    try {
      const body = await response.json()
      if (body && body.error && body.error.message) {
        message = body.error.message
      }
    } catch {
      // non-JSON body — keep the generic message
    }
    throw new ApiError(response.status, message, response.url)
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

// ---- Jobs -----------------------------------------------------------------

// POST /api/v1/jobs — create a Job. Requires an existing conversation_id
// (backend), which currently has no create-conversation endpoint, so this is
// an integration point for when the conversations API ships.
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

// ---- Network status -------------------------------------------------------

// GET /api/v1/network-status — sovereignty proof used by the security indicator.
// Definition exists in docs/api.md; the backend router is not yet wired.
export async function getNetworkStatus() {
  return request('/network-status')
}

// ---- Integration point (backend not yet implemented) ----------------------
// Docs/api.md defines conversations, documents, knowledge-base and artifact
// list endpoints. They are not served by the backend yet, so no functions are
// exported here until those routers exist. New functions go in this module,
// one per endpoint, never in components.