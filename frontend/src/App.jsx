import { useState } from 'react'
import { AppShell } from './components/layout/AppShell.jsx'
import { useHealth } from './hooks/useHealth.js'
import { Workbench } from './pages/Workbench.jsx'
import { Jobs } from './pages/Jobs.jsx'
import Knowledge from './pages/Knowledge.jsx'
import Artifacts from './pages/Artifacts.jsx'
import Audit from './pages/Audit.jsx'
import Settings from './pages/Settings.jsx'

const PAGES = {
  workbench: Workbench,
  jobs: Jobs,
  knowledge: Knowledge,
  artifacts: Artifacts,
  audit: Audit,
  settings: Settings,
}

export default function App() {
  const [page, setPage] = useState('workbench')
  const health = useHealth()

  const navigate = (next) => {
    if (PAGES[next]) setPage(next)
  }

  const Page = PAGES[page]

  // Jobs/Workbench need an explicit onNewTask / onOpenJob callback; the other
  // pages render statically.
  const pageProps = {
    healthState: health.status,
    onNavigate: navigate,
  }
  if (page === 'jobs' || page === 'workbench') {
    pageProps.onNewTask = () => navigate('workbench')
    pageProps.onOpenJob = () => navigate('workbench')
  }

  return (
    <AppShell page={page} onNavigate={navigate} healthState={health.status}>
      <Page {...pageProps} />
    </AppShell>
  )
}