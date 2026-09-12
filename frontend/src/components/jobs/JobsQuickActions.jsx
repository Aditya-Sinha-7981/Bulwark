import { Button } from '../ui/Button.jsx'

export function JobsQuickActions({ onNewTask, onViewArtifacts, onSearchKnowledge }) {
  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold text-txt-hi">Quick Actions</h3>
      <div className="space-y-2">
        <Button variant="primary" icon="plus" className="w-full" onClick={onNewTask}>
          New Task
        </Button>
        <Button variant="ghost" icon="artifacts" className="w-full" onClick={onViewArtifacts}>
          View Artifacts
        </Button>
        <Button variant="ghost" icon="knowledge" className="w-full" onClick={onSearchKnowledge}>
          Search Knowledge
        </Button>
      </div>
    </div>
  )
}