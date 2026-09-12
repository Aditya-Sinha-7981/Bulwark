import { PageHeader } from '../components/ui/PageHeader.jsx'
import { Badge } from '../components/ui/Badge.jsx'

function SettingRow({ label, value, mono }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-line/60 py-3 last:border-0">
      <dt className="text-sm text-txt-mid">{label}</dt>
      <dd className={`text-sm font-medium text-txt-hi ${mono ? 'mono text-[13px]' : ''}`}>{value}</dd>
    </div>
  )
}

export default function Settings({ healthState }) {
  const connected = healthState === 'connected'

  return (
    <div className="mx-auto max-w-[900px]">
      <PageHeader title="Settings" description="Runtime configuration for this local Bulwark instance." />

      <div className="space-y-5">
        <section className="card p-5">
          <h3 className="mb-2 text-sm font-semibold text-txt-hi">Connection</h3>
          <dl>
            <SettingRow
              label="Backend"
              value={connected ? 'Connected' : 'Unreachable'}
              mono
            />
            <SettingRow label="API base" value="http://127.0.0.1:8000/api/v1" mono />
            <SettingRow label="CORS origin" value="http://localhost:5173" mono />
          </dl>
        </section>

        <section className="card p-5">
          <h3 className="mb-2 text-sm font-semibold text-txt-hi">Models</h3>
          <dl>
            <SettingRow label="Reasoning & vision" value="qwen3.5:9b" mono />
            <SettingRow label="Code generation" value="qwen2.5-coder:7b" mono />
            <SettingRow label="Embedding" value="qwen3-embedding:0.6b" mono />
            <SettingRow label="OCR" value="PaddleOCR PP-OCRv6 (CPU)" mono />
            <SettingRow label="Runtime" value="Ollama · localhost:11434" mono />
          </dl>
        </section>

        <section className="card p-5">
          <h3 className="mb-2 text-sm font-semibold text-txt-hi">Sovereignty</h3>
          <div className="flex flex-wrap gap-2 pb-3">
            <Badge tone="green" icon="shieldCheck">
              Zero external egress
            </Badge>
            <Badge tone="green" icon="lock">
              Loopback only
            </Badge>
            <Badge tone="gray" icon="server">
              Single machine
            </Badge>
          </div>
          <dl>
            <SettingRow label="Network policy" value="network_access: false" mono />
            <SettingRow label="Sandbox network" value="--network none" mono />
            <SettingRow label="Telemetry" value="Disabled" mono />
          </dl>
        </section>
      </div>
    </div>
  )
}