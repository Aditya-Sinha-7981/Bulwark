import { useState } from 'react'
import { AppShell } from './components/layout/AppShell.jsx'
import { useHealth } from './hooks/useHealth.js'
import { Workbench } from './pages/Workbench.jsx'
import Documents from './pages/Documents.jsx'
import Artifacts from './pages/Artifacts.jsx'
import KnowledgeBase from './pages/KnowledgeBase.jsx'

export default function App() {
  const health = useHealth()
  const [page, setPage] = useState('workbench')

  return (
    <AppShell page={page} onNavigate={setPage} healthState={health.status}>
      {page === 'documents' ? (
        <Documents />
      ) : page === 'artifacts' ? (
        <Artifacts />
      ) : page === 'knowledge' ? (
        <KnowledgeBase />
      ) : (
        <Workbench healthState={health.status} />
      )}
    </AppShell>
  )
}
