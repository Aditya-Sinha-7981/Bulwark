// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import App from '../App.jsx'

// Mock all API functions - define classes inside the factory
vi.mock('../services/api.js', () => {
  class MockApiError extends Error {
    constructor(status, message, url, details = {}) {
      super(message)
      this.name = 'ApiError'
      this.status = status
      this.url = url
      this.details = details
    }
  }

  return {
    getHealth: vi.fn(),
    createConversation: vi.fn(),
    getConversation: vi.fn(),
    createJob: vi.fn(),
    getJob: vi.fn(),
    getJobTrace: vi.fn(),
    jobEventsUrl: vi.fn((jobId) => `http://127.0.0.1:8000/api/v1/jobs/${jobId}/events`),
    uploadDocument: vi.fn(),
    getDocument: vi.fn(),
    getArtifact: vi.fn(),
    artifactDownloadUrl: vi.fn((id) => `http://127.0.0.1:8000/api/v1/artifacts/${id}/download`),
    getKnowledgeBase: vi.fn(),
    ingestKnowledgeDocument: vi.fn(),
    deleteKnowledgeDocument: vi.fn(),
    getNetworkStatus: vi.fn(),
    ApiError: MockApiError,
  }
})

vi.mock('../hooks/useJobEvents.js', () => ({
  useJobEvents: () => ({
    events: [],
    status: 'closed',
    error: null,
    reconnect: vi.fn(),
  }),
}))

import { getHealth, getNetworkStatus } from '../services/api.js'

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.clearAllMocks()
})

describe('App shell + health', () => {
  beforeEach(() => {
    getHealth.mockReset()
    getNetworkStatus.mockReset()
  })

  it('renders the Workbench and a connected indicator when health succeeds', async () => {
    getHealth.mockResolvedValue({ status: 'ok' })
    getNetworkStatus.mockResolvedValue({
      external_connections_detected: false,
      checked_at: new Date().toISOString(),
      monitoring_since: new Date().toISOString(),
    })

    render(<App />)

    expect(screen.getByRole('heading', { name: 'What are you working on?' })).toBeInTheDocument()
    expect(await screen.findByText('LOCAL • SECURE')).toBeInTheDocument()
    expect(screen.getByText('NODE • CONNECTED')).toBeInTheDocument()
    expect(screen.getByText('Local Model Ready')).toBeInTheDocument()
  })

  it('shows an unreachable state when health fails', async () => {
    getHealth.mockRejectedValue(new Error('network down'))
    getNetworkStatus.mockRejectedValue(new Error('network down'))

    render(<App />)

    expect(await screen.findByText('BACKEND UNREACHABLE')).toBeInTheDocument()
    expect(screen.getByText('NODE • OFFLINE')).toBeInTheDocument()
    expect(screen.getAllByText('Backend unreachable').length).toBeGreaterThan(0)
    expect(screen.getByText(/Local Model/i)).toBeInTheDocument()
  })
})

describe('Navigation removed - Workbench only', () => {
  beforeEach(() => {
    getHealth.mockReset()
    getNetworkStatus.mockReset()
    getHealth.mockResolvedValue({ status: 'ok' })
    getNetworkStatus.mockResolvedValue({
      external_connections_detected: false,
      checked_at: new Date().toISOString(),
      monitoring_since: new Date().toISOString(),
    })
  })

  it('renders only Workbench (no sidebar navigation for Jobs/Knowledge/Settings)', async () => {
    render(<App />)

    await screen.findByText('LOCAL • SECURE')
    expect(screen.getByRole('heading', { name: 'What are you working on?' })).toBeInTheDocument()
    // Jobs, Knowledge, Settings pages should not be accessible
    expect(screen.queryByRole('button', { name: 'Jobs' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Knowledge' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Settings' })).not.toBeInTheDocument()
  })
})