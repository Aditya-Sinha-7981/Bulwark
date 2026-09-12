import { useState } from 'react'
import { AppShell } from './components/layout/AppShell.jsx'
import { useHealth } from './hooks/useHealth.js'
import { Workbench } from './pages/Workbench.jsx'

export default function App() {
  const health = useHealth()

  return (
    <AppShell page="workbench" onNavigate={() => {}} healthState={health.status}>
      <Workbench healthState={health.status} />
    </AppShell>
  )
}