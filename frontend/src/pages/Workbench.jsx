import { useState, useEffect, useCallback, useRef } from 'react'
import { useApi, useApiMutation } from '../hooks/useApi'
import { getHealth, getJob, getNetworkStatus } from '../services/api'
import { ChatPanel } from '../components/ChatPanel'
import { JobTracePanel } from '../components/JobTracePanel'
import { ArtifactPanel } from '../components/ArtifactPanel'
import { RagEvidencePanel } from '../components/RagEvidencePanel'
import { ErrorBanner } from '../components/ErrorBanner'
import { Badge } from '../components/ui/Badge'
import { Icon } from '../components/ui/Icon'
import { Button } from '../components/ui/Button.jsx'

// Simulation fallback — used when backend is unreachable
const SIMULATED_STEPS = [
  { label: 'Task received', event: 'job_created' },
  { label: 'Policy checked', event: 'policy_decision · allow' },
  { label: 'Request loaded', event: 'tool_invoked' },
  { label: 'Content analyzed', event: 'model_invoked · qwen3.5:9b' },
  { label: 'Summary generated', event: 'artifact_created' },
  { label: 'Task completed', event: 'job_completed' },
]
const STEP_MS = 450

function buildSimulatedResult(prompt, file) {
  const docLabel = file ? ` of the attached "${file.name}" (${file.size})` : ''
  return {
    title: "Here's a summary of the document",
    summary:
      `I processed the request locally${docLabel}. All extraction and analysis ran on this machine — nothing ` +
      'left the loopback interface. The findings below are grounded in the source material.',
    points: [
      'Asset integrity and maintenance compliance are within acceptable thresholds for the reporting period.',
      'Two open action items require follow-up: calibration drift on Unit 2 and pending valve inspection.',
      'No confidential data was transmitted; the entire pipeline executed air-gapped.',
      'Suggested owner for each action item has been derived from the maintenance SOP knowledge base.',
      'Artifacts can be exported as DOCX or XLSX for the formal record.',
    ],
    artifact: { name: 'Summary_Report.md', size: '18 KB', type: 'MARKDOWN' },
  }
}

function initSimSteps() {
  return SIMULATED_STEPS.map((step) => ({ ...step, state: 'pending' }))
}

export function Workbench({ healthState }) {
  // Real backend state
  const [conversationId, setConversationId] = useState(null)
  const [activeJobId, setActiveJobId] = useState(null)
  const [jobData, setJobData] = useState(null)
  const [errors, setErrors] = useState([])
  const [networkStatus, setNetworkStatus] = useState(null)

  // Simulation fallback state
  const [simMode, setSimMode] = useState(false)
  const [simPrompt, setSimPrompt] = useState('')
  const [simFile, setSimFile] = useState(null)
  const [simSubmission, setSimSubmission] = useState(null)
  const [simResult, setSimResult] = useState(null)
  const [simSteps, setSimSteps] = useState(initSimSteps())
  const simTimersRef = useRef([])

  // Health check to determine if we can use real backend
  const { data: healthData, loading: healthLoading } = useApi(getHealth)

  // Network status polling (for sovereignty indicator)
  useEffect(() => {
    if (healthState !== 'connected') return
    let cancelled = false
    const poll = async () => {
      try {
        const status = await getNetworkStatus()
        if (!cancelled) setNetworkStatus(status)
      } catch {
        // Ignore network status errors
      }
    }
    poll()
    const interval = setInterval(poll, 15000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [healthState])

  // Determine if we should use simulation fallback
  useEffect(() => {
    if (!healthLoading) {
      const backendConnected = healthState === 'connected' && healthData?.status === 'ok'
      setSimMode(!backendConnected)
    }
  }, [healthData, healthLoading, healthState])

  // Poll job status when we have an active job (real mode)
  useEffect(() => {
    if (!activeJobId || simMode) return
    let cancelled = false
    const poll = async () => {
      try {
        const job = await getJob(activeJobId)
        if (!cancelled) {
          setJobData(job)
          if (job.status === 'completed' || job.status === 'failed') {
            // Job finished, stop polling
          }
        }
      } catch {
        // Ignore polling errors
      }
    }
    poll()
    const interval = setInterval(poll, 3000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [activeJobId, simMode])

  // Simulation functions
  const clearSimTimers = useCallback(() => {
    simTimersRef.current.forEach(clearTimeout)
    simTimersRef.current = []
  }, [])

  const runSimulation = useCallback((sub) => {
    clearSimTimers()
    setSimSteps(initSimSteps())
    setSimSubmission(sub)
    setSimResult(null)

    SIMULATED_STEPS.forEach((_, index) => {
      simTimersRef.current.push(
        setTimeout(() => {
          setSimSteps((prev) =>
            prev.map((step, i) =>
              i === index ? { ...step, state: 'active' } : i < index ? { ...step, state: 'done' } : step
            )
          )
        }, index * STEP_MS)
      )
    })

    simTimersRef.current.push(
      setTimeout(() => {
        setSimSteps((prev) => prev.map((step) => ({ ...step, state: 'done' })))
        setSimResult(buildSimulatedResult(sub.prompt, sub.file))
      }, SIMULATED_STEPS.length * STEP_MS)
    )
  }, [clearSimTimers])

  const handleSimSubmit = () => {
    if (!simPrompt.trim()) return
    runSimulation({ prompt: simPrompt.trim(), file: simFile })
    setSimPrompt('')
    setSimFile(null)
  }

  // Real backend handlers
  const handleJobCreated = useCallback((jobId) => {
    setActiveJobId(jobId)
    setJobData(null)
  }, [])

  const handleError = useCallback((err) => {
    setErrors((prev) => [...prev, err])
  }, [])

  const dismissError = useCallback((err) => {
    setErrors((prev) => prev.filter((e) => e !== err))
  }, [])

  const clearAllErrors = useCallback(() => {
    setErrors([])
  }, [])

  // Determine what to render
  const running = simMode ? Boolean(simSubmission && !simResult) : Boolean(activeJobId && jobData?.status === 'running')
  const completed = simMode ? Boolean(simResult) : Boolean(jobData && (jobData.status === 'completed' || jobData.status === 'failed'))

  // Get artifact IDs from job data
  const artifactIds = jobData?.artifact_ids ?? []

  return (
    <div className="mx-auto max-w-[1400px]">
      {/* Top Bar - Mode indicator */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Badge tone="green" icon="shieldCheck">
            AIR-GAPPED & ENCRYPTED
          </Badge>
          {simMode ? (
            <Badge tone="purple" icon="alert">
              DEMO MODE (Backend unreachable)
            </Badge>
          ) : healthState === 'connected' ? (
            <Badge tone="blue" icon="node">
              Local Model Ready
            </Badge>
          ) : (
            <Badge tone="gray" icon="node">
              Local Model Starting
            </Badge>
          )}
          {networkStatus && (
            <Badge tone={networkStatus.external_connections_detected ? 'red' : 'green'} dot={false} icon={networkStatus.external_connections_detected ? 'alert' : 'check'}>
              {networkStatus.external_connections_detected ? 'External connections detected' : '0 external connections'}
            </Badge>
          )}
        </div>
        {errors.length > 0 && (
          <button
            type="button"
            className="btn-quiet btn text-xs text-danger"
            onClick={clearAllErrors}
          >
            <Icon name="x" size={12} />
            Dismiss all errors ({errors.length})
          </button>
        )}
      </div>

      {/* Error Banner */}
      <ErrorBanner errors={errors} onDismiss={dismissError} />

      {/* Main Layout */}
      {(!simMode && !activeJobId) || (simMode && !simSubmission) ? (
        // Empty state - centered composer
        <div className="mx-auto flex min-h-[70vh] max-w-3xl flex-col justify-center py-8">
          <h2 className="text-center text-3xl font-semibold tracking-tight text-txt-hi">
            What are you working on?
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-center text-sm leading-relaxed text-txt-low">
            Interact securely with your private enterprise repositories and local models without
            telemetry leakage.
          </p>

          <div className="mt-8 w-full">
            {simMode ? (
              // Simulation composer
              <div className="card overflow-hidden">
                <textarea
                  value={simPrompt}
                  onChange={(e) => setSimPrompt(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                      e.preventDefault()
                      handleSimSubmit()
                    }
                  }}
                  rows={3}
                  placeholder="Ask a question, analyze confidential files, or run local tasks…"
                  className="w-full resize-none bg-transparent px-5 py-4 text-[15px] text-txt-hi placeholder:text-txt-dim focus:outline-none"
                />
                <div className="flex flex-wrap items-center gap-2 border-t border-line px-4 py-2.5">
                  <input
                    type="file"
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0] ?? null
                      if (file) setSimFile({
                        name: file.name,
                        size: file.size,
                        type: file.type.split('/').pop().toUpperCase() || 'FILE',
                      })
                      e.target.value = ''
                    }}
                    id="sim-file-input"
                  />
                  <label
                    htmlFor="sim-file-input"
                    className="btn-quiet btn text-txt-mid cursor-pointer"
                  >
                    <Icon name="paperclip" size={15} />
                    Attach file
                  </label>
                  {simFile && (
                    <span className="ml-2 text-sm text-txt-mid">
                      {simFile.name} ({simFile.size})
                    </span>
                  )}
                  <button
                    type="button"
                    className="btn-primary ml-auto h-9 w-9 !px-0 rounded-full flex items-center justify-center"
                    onClick={handleSimSubmit}
                    disabled={!simPrompt.trim()}
                  >
                    <Icon name="send" size={18} className="text-white" />
                  </button>
                </div>
              </div>
            ) : (
              // Real ChatPanel
              <ChatPanel onJobCreated={handleJobCreated} conversationId={conversationId} />
            )}
          </div>
        </div>
      ) : (
        // Active/Completed layout - three panels
        <div className="flex flex-col gap-6 xl:flex-row">
          {/* Left: Chat or Trace */}
          <div className="min-w-0 flex-1 xl:w-1/2">
            {simMode ? (
              // Simulation result view
              <div className="card flex flex-col h-full">
                <div className="p-4 border-b border-line flex items-center justify-between">
                  <Badge tone={running ? 'blue' : 'green'}>{running ? 'Running…' : 'Completed'}</Badge>
                  <span className="mono text-[11px] text-txt-dim">simulated execution</span>
                </div>
                <div className="flex-1 overflow-y-auto p-4">
                  {simSubmission && (
                    <div className="space-y-4">
                      <div className="p-3 rounded-lg bg-elevated">
                        <p className="font-medium text-txt-hi">{simSubmission.prompt}</p>
                        {simSubmission.file && (
                          <p className="text-sm text-txt-dim mt-1">Attached: {simSubmission.file.name}</p>
                        )}
                      </div>
                      {simResult && (
                        <div className="space-y-3">
                          <h3 className="text-lg font-semibold text-txt-hi">{simResult.title}</h3>
                          <p className="text-txt-mid">{simResult.summary}</p>
                          <div>
                            <h4 className="text-sm font-medium text-txt-hi mb-2">Key points</h4>
                            <ul className="space-y-1">
                              {simResult.points.map((point, i) => (
                                <li key={i} className="text-sm text-txt-mid flex items-start gap-2">
                                  <Icon name="check" size={14} className="text-ok shrink-0 mt-0.5" />
                                  {point}
                                </li>
                              ))}
                            </ul>
                          </div>
                          <div className="pt-3 border-t border-line">
                            <h4 className="text-sm font-medium text-txt-hi mb-2">Generated artifact</h4>
                            <div className="flex items-center gap-3 p-3 rounded-lg border border-line bg-surface">
                              <div className="p-2 rounded-lg bg-band-soft text-band">
                                <Icon name="file" size={20} />
                              </div>
                              <div>
                                <p className="font-medium text-txt-hi">{simResult.artifact.name}</p>
                                <p className="text-xs text-txt-dim">{simResult.artifact.size} • {simResult.artifact.type}</p>
                              </div>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ) : (
              // Real ChatPanel (shows history for conversation)
              <ChatPanel
                onJobCreated={handleJobCreated}
                conversationId={conversationId}
              />
            )}
          </div>

          {/* Right: Trace + Artifacts + RAG Evidence */}
          <div className="w-full shrink-0 xl:w-1/2 space-y-4">
            {/* Live Trace */}
            <JobTracePanel jobId={simMode ? null : activeJobId} />

            {/* Artifacts & RAG Evidence - stacked */}
            <div className="space-y-4">
              <ArtifactPanel
                jobId={simMode ? null : activeJobId}
                artifactIds={artifactIds}
              />
              <RagEvidencePanel
                events={simMode ? [] : []} // TODO: pass real trace events when available
              />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}