import { useEffect, useState } from 'react'
import { getHealth } from '../services/api.js'

// Polls GET /api/v1/health on mount and on an interval so the connection
// indicator stays honest while the backend (un)starts. No fetch here —
// all I/O lives in services/api.js.
export function useHealth(intervalMs = 15000) {
  const [state, setState] = useState({ status: 'checking', data: null })

  useEffect(() => {
    let cancelled = false
    let timer

    const check = async () => {
      try {
        const data = await getHealth()
        if (!cancelled) setState({ status: 'connected', data })
      } catch {
        if (!cancelled) setState({ status: 'unreachable', data: null })
      }
    }

    check()
    if (intervalMs) {
      timer = setInterval(check, intervalMs)
    }

    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [intervalMs])

  return state
}