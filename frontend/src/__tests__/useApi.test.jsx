// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest'
import { render, act } from '@testing-library/react'
import { useApi } from '../hooks/useApi'

function Probe({ apiFn, args = [] }) {
  const { data, loading } = useApi(apiFn, ...args)
  return <div>{loading ? 'loading' : data ? JSON.stringify(data) : 'empty'}</div>
}

async function flush(times = 3) {
  for (let i = 0; i < times; i++) {
    await act(async () => {})
  }
}

describe('useApi request stability', () => {
  it('calls the API exactly once per mount — re-renders must not refetch', async () => {
    // Regression: the old dependency chain ([apiFn, args]) allocated a fresh
    // rest-array every render, so the fetch effect re-ran on every render and
    // hammered the endpoint in a tight loop (observed live 2026-09-12:
    // /api/v1/health flooded continuously while the UI was open).
    const apiFn = vi.fn().mockResolvedValue({ value: 'ok' })
    const { rerender } = render(<Probe apiFn={apiFn} />)
    await flush()
    rerender(<Probe apiFn={apiFn} />)
    rerender(<Probe apiFn={apiFn} />)
    await flush()
    expect(apiFn).toHaveBeenCalledTimes(1)
  })

  it('refetches when an arg value actually changes', async () => {
    const apiFn = vi.fn().mockResolvedValue({ value: 'ok' })
    const { rerender } = render(<Probe apiFn={apiFn} args={["a"]} />)
    await flush()
    expect(apiFn).toHaveBeenCalledTimes(1)
    rerender(<Probe apiFn={apiFn} args={["b"]} />)
    await flush()
    expect(apiFn).toHaveBeenCalledTimes(2)
    expect(apiFn).toHaveBeenLastCalledWith('b')
  })

  it('does not refetch when the same args are re-supplied', async () => {
    const apiFn = vi.fn().mockResolvedValue({ value: 'ok' })
    const { rerender } = render(<Probe apiFn={apiFn} args={["a"]} />)
    await flush()
    rerender(<Probe apiFn={apiFn} args={["a"]} />)
    await flush()
    expect(apiFn).toHaveBeenCalledTimes(1)
  })
})
