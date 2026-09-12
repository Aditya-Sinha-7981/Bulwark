import { useState, useCallback, useRef, useEffect } from 'react'
import { ApiError } from '../services/api.js'

// Thin fetch wrapper for api.md endpoints.
// Returns { data, loading, error, refetch }.
export function useApi(apiFn, ...args) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const mountedRef = useRef(true)

  const execute = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await apiFn(...args)
      if (mountedRef.current) {
        setData(result)
        setError(null)
      }
    } catch (err) {
      if (mountedRef.current) {
        if (err instanceof ApiError) {
          setError({ code: err.status, message: err.message, details: err.details })
        } else if (err instanceof TypeError && err.message.includes('fetch')) {
          setError({ code: 'NETWORK_ERROR', message: 'Backend unreachable', details: {} })
        } else {
          setError({ code: 'UNKNOWN_ERROR', message: err?.message ?? 'Unknown error', details: {} })
        }
        setData(null)
      }
    } finally {
      if (mountedRef.current) {
        setLoading(false)
      }
    }
  }, [apiFn, args])

  useEffect(() => {
    mountedRef.current = true
    execute()
    return () => {
      mountedRef.current = false
    }
  }, [execute])

  const refetch = useCallback(() => {
    execute()
  }, [execute])

  return { data, loading, error, refetch }
}

// Mutation variant — for POST/PUT/DELETE calls that shouldn't auto-execute on mount.
export function useApiMutation(apiFn) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const mutate = useCallback(async (...args) => {
    setLoading(true)
    setError(null)
    try {
      const result = await apiFn(...args)
      setData(result)
      setError(null)
      return result
    } catch (err) {
      if (err instanceof ApiError) {
        setError({ code: err.status, message: err.message, details: err.details })
      } else if (err instanceof TypeError && err.message.includes('fetch')) {
        setError({ code: 'NETWORK_ERROR', message: 'Backend unreachable', details: {} })
      } else {
        setError({ code: 'UNKNOWN_ERROR', message: err?.message ?? 'Unknown error', details: {} })
      }
      setData(null)
      throw err
    } finally {
      setLoading(false)
    }
  }, [apiFn])

  const reset = useCallback(() => {
    setData(null)
    setError(null)
    setLoading(false)
  }, [])

  return { data, loading, error, mutate, reset }
}