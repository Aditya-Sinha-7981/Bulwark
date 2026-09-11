import { useState } from 'react'
import { Icon } from '../ui/Icon.jsx'
import { Button } from '../ui/Button.jsx'

export function ArtifactCard({ artifact }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(`bulwark://artifact/${artifact.name}`)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // clipboard unavailable (non-secure context) — nothing to do
    }
  }

  return (
    <div className="rounded-xl border border-band/40 bg-band-soft p-4">
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-band/20 text-band">
          <Icon name="artifacts" size={20} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-txt-hi">{artifact.name}</div>
          <div className="mt-0.5 text-xs text-txt-low">
            {artifact.size} &bull; {artifact.type}
          </div>
        </div>
        <Icon name="download" size={16} className="text-band" />
      </div>

      <div className="mt-3 flex items-center gap-2">
        <Button variant="ghost" size="sm" icon="external">
          Open
        </Button>
        <Button variant="ghost" size="sm" icon="download" onClick={() => {}}>
          Download
        </Button>
        <Button variant="ghost" size="sm" icon={copied ? 'check' : 'copy'} onClick={handleCopy}>
          {copied ? 'Copied' : 'Copy'}
        </Button>
      </div>
    </div>
  )
}