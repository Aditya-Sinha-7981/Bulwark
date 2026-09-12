import { Icon } from '../ui/Icon.jsx'

const ACTIONS = [
  {
    id: 'analyze-doc',
    label: 'Analyze Document',
    icon: 'file',
    iconColor: 'text-accent',
    prompt: 'Analyze the attached document and give me a summary of key points.',
  },
  {
    id: 'search-knowledge',
    label: 'Search Knowledge',
    icon: 'knowledge',
    iconColor: 'text-blue-400',
    prompt: 'Search the knowledge base for guidance on this topic.',
  },
  {
    id: 'create-artifact',
    label: 'Create Artifact',
    icon: 'artifacts',
    iconColor: 'text-band',
    prompt: 'Create an artifact (DOCX/XLSX) summarizing the findings.',
  },
  {
    id: 'audit-code',
    label: 'Audit Code',
    icon: 'audit',
    iconColor: 'text-teal-400',
    prompt: 'Audit the provided code for issues and verify it in the sandbox.',
  },
]

export function QuickActions({ onUse }) {
  return (
    <div className="flex flex-wrap gap-2">
      {ACTIONS.map((action) => (
        <button
          key={action.id}
          type="button"
          onClick={() => onUse(action)}
          className="flex items-center gap-1.5 rounded-full border border-line px-3 py-1.5 text-xs text-txt-mid transition-colors hover:border-lineStrong hover:text-txt-hi"
        >
          <Icon name={action.icon} size={14} className={action.iconColor} />
          {action.label}
        </button>
      ))}
    </div>
  )
}