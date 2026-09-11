// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import App from '../App.jsx'

const mockGetHealth = vi.fn()

vi.mock('../services/api.js', () => ({
  getHealth: () => mockGetHealth(),
}))

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe('App shell + health', () => {
  beforeEach(() => {
    mockGetHealth.mockReset()
  })

  it('renders the Workbench and a connected indicator when health succeeds', async () => {
    mockGetHealth.mockResolvedValue({ status: 'ok' })

    render(<App />)

    expect(screen.getByRole('heading', { name: 'What are you working on?' })).toBeInTheDocument()
    expect(await screen.findByText('LOCAL • SECURE')).toBeInTheDocument()
    expect(screen.getByText('NODE • CONNECTED')).toBeInTheDocument()
    expect(screen.getByText('Local Model Ready')).toBeInTheDocument()
  })

  it('shows an unreachable state when health fails', async () => {
    mockGetHealth.mockRejectedValue(new Error('network down'))

    render(<App />)

    expect(await screen.findByText('BACKEND UNREACHABLE')).toBeInTheDocument()
    expect(screen.getByText('NODE • OFFLINE')).toBeInTheDocument()
    expect(screen.getAllByText('Backend unreachable').length).toBeGreaterThan(0)
    expect(screen.getByText('Local Model Starting')).toBeInTheDocument()
  })
})

describe('Workbench task flow (simulated timers)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockGetHealth.mockReset()
    mockGetHealth.mockResolvedValue({ status: 'ok' })
  })

  it('submits a prompt and runs through to a completed result', async () => {
    render(<App />)

    // flush the initial health check microtask
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })

    const prompt = screen.getByLabelText('Prompt')
    fireEvent.change(prompt, { target: { value: 'Analyze the Q3 safety report' } })

    fireEvent.click(screen.getByRole('button', { name: /run prompt/i }))

    expect(screen.getByText('Analyzing locally…')).toBeInTheDocument()
    expect(screen.getAllByText('Analyze the Q3 safety report').length).toBeGreaterThan(0)
    expect(screen.getByText('Running…')).toBeInTheDocument()

    // 6 simulated steps × 450 ms + final completion
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000)
    })

    expect(screen.getAllByText('Completed').length).toBeGreaterThan(0)
    expect(screen.getByText("Here's a summary of the document")).toBeInTheDocument()
    expect(screen.getAllByText('Summary_Report.md').length).toBeGreaterThan(0)
    expect(screen.getByText('Key points')).toBeInTheDocument()
    expect(screen.getByText('Suggested follow-ups')).toBeInTheDocument()
  })

  it('does not submit an empty prompt', async () => {
    render(<App />)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })

    const run = screen.getByRole('button', { name: /run prompt/i })
    expect(run).toBeDisabled()

    fireEvent.click(run)

    expect(screen.queryByText('Analyzing locally…')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'What are you working on?' })).toBeInTheDocument()
  })
})

describe('Navigation and Jobs', () => {
  beforeEach(() => {
    mockGetHealth.mockReset()
    mockGetHealth.mockResolvedValue({ status: 'ok' })
  })

  it('navigates between sidebar pages', async () => {
    render(<App />)

    await screen.findByText('LOCAL • SECURE')

    fireEvent.click(screen.getByRole('button', { name: 'Jobs' }))
    expect(
      screen.getByText('View and manage your tasks and their results.')
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Knowledge' }))
    expect(screen.getByText('Curate the local knowledge base your models retrieve from.')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Settings' }))
    expect(screen.getByText('Runtime configuration for this local Bulwark instance.')).toBeInTheDocument()
  })

  it('filters jobs by status', async () => {
    render(<App />)

    await screen.findByText('LOCAL • SECURE')
    fireEvent.click(screen.getByRole('button', { name: 'Jobs' }))

    fireEvent.click(screen.getByRole('button', { name: 'Failed' }))

    expect(screen.getByText('Generate monthly production report')).toBeInTheDocument()
    expect(screen.queryByText('Extract text from handwritten shift notes')).not.toBeInTheDocument()
  })

  it('searches jobs by task', async () => {
    render(<App />)

    await screen.findByText('LOCAL • SECURE')
    fireEvent.click(screen.getByRole('button', { name: 'Jobs' }))

    fireEvent.change(screen.getByRole('searchbox', { name: 'Search tasks' }), {
      target: { value: 'handwritten' },
    })

    expect(screen.getByText('Extract text from handwritten shift notes')).toBeInTheDocument()
    expect(screen.queryByText('Analyze Q3 safety inspection report')).not.toBeInTheDocument()
  })
})