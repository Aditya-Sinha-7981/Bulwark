import { useEffect, useRef, useState } from 'react'
import { PromptComposer } from '../components/workbench/PromptComposer.jsx'
import { QuickActions } from '../components/workbench/QuickActions.jsx'
import { TaskDetailsPanel } from '../components/workbench/TaskDetailsPanel.jsx'
import TaskResult from '../components/workbench/TaskResult.jsx'
import { Badge } from '../components/ui/Badge.jsx'

// Task simulation engine — frontend integration point.
// A real submission would call createJob() from services/api.js once the
// backend exposes a create-conversation endpoint. Until then the workflow is
// simulated locally (clearly separated here) so the UI is fully testable.
const SIMULATED_STEPS = [
  { label: 'Task received', event: 'job_created' },
  { label: 'Policy checked', event: 'policy_decision · allow' },
  { label: 'Request loaded', event: 'tool_invoked' },
  { label: 'Content analyzed', event: 'model_invoked · qwen3.5:9b' },
  { label: 'Summary generated', event: 'artifact_created' },
  { label: 'Task completed', event: 'job_completed' },
]

const STEP_MS = 450

function buildResult(prompt, file) {
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

function initSteps() {
  return SIMULATED_STEPS.map((step) => ({ ...step, state: 'pending' }))
}

export function Workbench({ healthState }) {
  const [prompt, setPrompt] = useState('')
  const [file, setFile] = useState(null)
  const [submission, setSubmission] = useState(null)
  const [result, setResult] = useState(null)
  const [steps, setSteps] = useState(initSteps())
  const timers = useRef([])
  const running = Boolean(submission && !result)

  const clearTimers = () => {
    timers.current.forEach(clearTimeout)
    timers.current = []
  }

  const runSimulation = (sub) => {
    setSteps(initSteps())
    setSubmission(sub)
    setResult(null)

    SIMULATED_STEPS.forEach((_, index) => {
      timers.current.push(
        setTimeout(() => {
          setSteps((prev) =>
            prev.map((step, i) =>
              i === index ? { ...step, state: 'active' } : i < index ? { ...step, state: 'done' } : step
            )
          )
        }, index * STEP_MS)
      )
    })

    timers.current.push(
      setTimeout(() => {
        setSteps((prev) => prev.map((step) => ({ ...step, state: 'done' })))
        setResult(buildResult(sub.prompt, sub.file))
      }, SIMULATED_STEPS.length * STEP_MS)
    )
  }

  useEffect(() => clearTimers, [])

  const handleSubmit = () => {
    if (!prompt.trim() || running) return
    runSimulation({ prompt: prompt.trim(), file })
  }

  const handleQuickAction = (action) => {
    setPrompt(action.prompt)
    if (action.id === 'search-knowledge') setFile(null)
    document.querySelector('[aria-label="Prompt"]')?.focus()
  }

  const handleFollowUp = (text) => {
    setPrompt(text)
    setFile(null)
    runSimulation({ prompt: text, file: null })
  }

  return (
    <div className="mx-auto max-w-[1400px]">
      {/* Empty / running layout: centered composer */}
      {!submission && (
        <div className="mx-auto flex min-h-[70vh] max-w-3xl flex-col justify-center py-8">
          <div className="mb-8 flex flex-wrap items-center justify-center gap-2">
            <Badge tone="green" icon="shieldCheck">
              AIR-GAPPED &amp; ENCRYPTED
            </Badge>
            {healthState === 'connected' ? (
              <Badge tone="blue" icon="node">
                Local Model Ready
              </Badge>
            ) : (
              <Badge tone="gray" icon="node">
                Local Model Starting
              </Badge>
            )}
          </div>

          <h2 className="text-center text-3xl font-semibold tracking-tight text-txt-hi">
            What are you working on?
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-center text-sm leading-relaxed text-txt-low">
            Interact securely with your private enterprise repositories and local models without
            telemetry leakage.
          </p>

          <div className="mt-8">
            <PromptComposer
              value={prompt}
              onChange={setPrompt}
              onSubmit={handleSubmit}
              onAttach={setFile}
              attachedFile={file}
            />
          </div>

          <div className="mt-8">
            <QuickActions onUse={handleQuickAction} />
          </div>
        </div>
      )}

      {/* Result layout: main + right details sidebar */}
      {submission && (
        <div className="flex flex-col gap-6 xl:flex-row">
          <div className="min-w-0 flex-1">
            <div className="mb-5 flex items-center gap-2">
              <Badge tone={running ? 'blue' : 'green'}>{running ? 'Running…' : 'Completed'}</Badge>
              <span className="mono text-[11px] text-txt-dim">execution steps tracked in audit</span>
            </div>
            <TaskResult
              submission={submission}
              result={result}
              running={running}
              onFollowUp={handleFollowUp}
            />
          </div>

          <aside className="w-full shrink-0 xl:w-[340px]" aria-label="Task details">
            <TaskDetailsPanel
              task={{
                id: 'task-local',
                name: submission.prompt.slice(0, 48),
                description:
                  submission.prompt.length > 48
                    ? `${submission.prompt.slice(48, 160)}${submission.prompt.length > 160 ? '…' : ''}`
                    : 'Local task execution',
                started: '14:21:09',
                completed: running ? '—' : '14:21:44',
                duration: running ? '…' : '35s',
                model: 'qwen3.5:9b',
              }}
              artifact={result?.artifact ?? { name: 'Summary_Report.md', size: '18 KB', type: 'MARKDOWN' }}
              steps={steps}
              running={running}
            />
          </aside>
        </div>
      )}
    </div>
  )
}