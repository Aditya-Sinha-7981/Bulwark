import { useState } from 'react'
import { Sidebar } from './Sidebar.jsx'
import { Header } from './Header.jsx'
import { StatusBar } from './StatusBar.jsx'

export function AppShell({ page, onNavigate, healthState, children }) {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <div className="flex min-h-screen bg-ink text-txt-hi">
      <Sidebar
        current={page}
        onNavigate={onNavigate}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        healthState={healthState}
      />

      <div className="flex min-h-screen min-w-0 flex-1 flex-col lg:pl-64">
        <Header page={page} onMenu={() => setSidebarOpen(true)} healthState={healthState} />
        <main className="flex-1 overflow-x-hidden px-5 py-6 lg:px-8">{children}</main>
        <StatusBar healthState={healthState} />
      </div>
    </div>
  )
}