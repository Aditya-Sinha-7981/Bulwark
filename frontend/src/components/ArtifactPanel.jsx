import { useState, useEffect } from 'react'
import { useApi } from '../hooks/useApi'
import { getArtifact, artifactDownloadUrl } from '../services/api'
import { Icon } from './ui/Icon'

// Artifact panel — lists artifacts for the current Job.
// Each links directly to download endpoint (browser-native).
export function ArtifactPanel({ jobId, artifactIds = [] }) {
  const [artifacts, setArtifacts] = useState([])

  // Fetch metadata for each artifact
  useEffect(() => {
    if (!artifactIds.length) {
      setArtifacts([])
      return
    }
    const fetchAll = async () => {
      const results = await Promise.allSettled(
        artifactIds.map((id) => getArtifact(id))
      )
      const loaded = results
        .filter((r) => r.status === 'fulfilled')
        .map((r) => r.value)
      setArtifacts(loaded)
    }
    fetchAll()
  }, [artifactIds.join(',')])

  if (!artifactIds.length) {
    return (
      <div className="card flex items-center justify-center h-full min-h-[200px] text-txt-dim">
        No artifacts generated yet.
      </div>
    )
  }

  return (
    <div className="card flex flex-col h-full min-h-0">
      <div className="px-4 py-3 border-b border-line flex items-center justify-between">
        <h3 className="text-sm font-semibold text-txt-hi">Artifacts</h3>
        <span className="mono text-[11px] text-txt-dim">{artifacts.length} file{artifacts.length !== 1 ? 's' : ''}</span>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {artifacts.map((artifact) => (
          <a
            key={artifact.artifact_id}
            href={artifactDownloadUrl(artifact.artifact_id)}
            download={artifact.filename}
            className="flex items-center gap-3 p-3 rounded-lg border border-line bg-surface hover:border-accent/40 hover:bg-elevated transition-colors"
            target="_blank"
            rel="noopener noreferrer"
          >
            <div className="p-2 rounded-lg bg-band-soft text-band">
              <Icon name="file" size={20} />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-txt-hi truncate">{artifact.filename}</p>
              <div className="flex items-center gap-3 mt-1 text-[11px] text-txt-dim mono">
                <span>{artifact.type?.toUpperCase()}</span>
                <span>{formatBytes(artifact.size_bytes)}</span>
                <span>{new Date(artifact.created_at).toLocaleString()}</span>
              </div>
            </div>
            <Icon name="download" size={16} className="text-txt-low" />
          </a>
        ))}

        {artifacts.length === 0 && artifactIds.length > 0 && (
          <div className="text-center text-txt-dim py-8">
            <Icon name="activity" size={24} className="mx-auto mb-2 text-txt-low" />
            Loading artifact metadata…
          </div>
        )}
      </div>
    </div>
  )
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / 1024 ** i).toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}