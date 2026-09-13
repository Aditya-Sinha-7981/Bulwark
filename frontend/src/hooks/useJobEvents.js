import { useState, useEffect, useRef, useCallback } from 'react'
import { getJobTrace } from '../services/api.js'
import { jobEventsUrl } from '../services/api.js'

const TERMINAL_EVENT_TYPES = new Set(['job_completed'])

// Duplicate suppression: the hook fetches /trace (all persisted events) on
// mount AND opens the SSE stream, which replays persisted events by default
// (replay=true, backend/api/jobs.py) — without dedupe every historical event
// renders twice (backend contract audit, 2026-09-12).
const seenEventIds = new Set()

// EventSource wrapper for GET /api/v1/jobs/{job_id}/events (SSE).
// On mount: fetches GET /jobs/{job_id}/trace (late-join), then switches to live SSE.
// Returns { events: [...], status: 'connecting' | 'open' | 'closed', error, reconnect }
export function useJobEvents(jobId) {
  const [events, setEvents] = useState([])
  const [status, setStatus] = useState('connecting')
  const [error, setError] = useState(null)
  const eventSourceRef = useRef(null)
  const mountedRef = useRef(true)
  const traceFetchedRef = useRef(false)
  const reconnectTimerRef = useRef(null)

  const addEvent = useCallback((event) => {
    if (event.event_id && seenEventIds.has(event.event_id)) return
    if (event.event_id) seenEventIds.add(event.event_id)
    setEvents((prev) => [...prev, event])
    // Close on terminal event. Only job_completed is terminal — `error`
    // events fire on recoverable tool failures mid-job (docs/audit.md); the
    // Job continues after them and the trace must keep streaming.
    if (TERMINAL_EVENT_TYPES.has(event.event_type)) {
      closeEventSource()
      setStatus('closed')
    }
  }, [])

  const closeEventSource = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
  }, [])

  const fetchInitialTrace = useCallback(async () => {
    if (traceFetchedRef.current || !jobId) return
    traceFetchedRef.current = true
    try {
      const trace = await getJobTrace(jobId)
      if (mountedRef.current && trace?.events?.length) {
        // Route through addEvent (event_id dedupe) — the SSE stream replays
        // persisted events by default, so pushing the trace straight into
        // state double-rendered every event (observed live 2026-09-12:
        // "Job created" appeared twice).
        trace.events.forEach(addEvent)
      }
    } catch (err) {
      // Trace fetch failed — we'll rely on SSE for live events
      if (mountedRef.current) {
        console.warn('Failed to fetch initial trace:', err)
      }
    }
  }, [jobId, addEvent])

  const connect = useCallback(() => {
    if (!jobId || !mountedRef.current) return
    if (eventSourceRef.current) return

    setStatus('connecting')
    setError(null)

    // Fetch initial trace first (late-join / refresh)
    fetchInitialTrace()

    // Then open SSE stream
    const url = jobEventsUrl(jobId)
    const es = new EventSource(url)
    eventSourceRef.current = es

    es.onopen = () => {
      if (mountedRef.current) {
        setStatus('open')
        setError(null)
      }
    }

    es.onmessage = (messageEvent) => {
      if (!mountedRef.current) return
      try {
        const data = messageEvent.data
        if (!data || data.trim() === '') return
        // Each data: line is one event object per audit.md schema
        const event = JSON.parse(data)
        // Validate minimal shape
        if (event && event.event_type) {
          addEvent(event)
        }
      } catch (err) {
        console.warn('Failed to parse SSE event:', err)
      }
    }

    es.onerror = (err) => {
      if (!mountedRef.current) return
      closeEventSource()
      setStatus('closed')
      setError({ message: 'SSE connection lost', details: {} })
    }
  }, [jobId, fetchInitialTrace, addEvent, closeEventSource])

  const reconnect = useCallback(() => {
    if (!mountedRef.current || !jobId) return
    traceFetchedRef.current = false
    seenEventIds.clear()
    closeEventSource()
    // Small delay before reconnect to avoid tight loop
    reconnectTimerRef.current = setTimeout(() => {
      if (mountedRef.current) {
        connect()
      }
    }, 1000)
  }, [jobId, closeEventSource, connect])

  useEffect(() => {
    mountedRef.current = true
    traceFetchedRef.current = false
    seenEventIds.clear()
    setEvents([])
    setStatus('connecting')
    setError(null)
    connect()

    return () => {
      mountedRef.current = false
      closeEventSource()
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
      }
    }
  }, [jobId, connect, closeEventSource])

  return { events, status, error, reconnect }
}