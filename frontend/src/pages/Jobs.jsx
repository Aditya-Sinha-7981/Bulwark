import { useEffect, useMemo, useState } from 'react'
import { JobFilters } from '../components/jobs/JobFilters.jsx'
import { JobsTable } from '../components/jobs/JobsTable.jsx'
import { JobOverview } from '../components/jobs/JobOverview.jsx'
import { RecentActivity } from '../components/jobs/RecentActivity.jsx'
import { JobsQuickActions } from '../components/jobs/JobsQuickActions.jsx'
import { Pagination } from '../components/jobs/Pagination.jsx'
import { MOCK_JOBS, MOCK_ACTIVITY } from '../data/mockJobs.js'
import { Button } from '../components/ui/Button.jsx'

export function Jobs({ onNewTask, onOpenJob, onNavigate }) {
  const [filter, setFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return MOCK_JOBS.filter((job) => {
      const matchesFilter = filter === 'all' || job.status === filter
      const matchesSearch = !q || job.task.toLowerCase().includes(q)
      return matchesFilter && matchesSearch
    })
  }, [filter, search])

  const paged = useMemo(() => {
    const start = (page - 1) * pageSize
    return filtered.slice(start, start + pageSize)
  }, [filtered, page, pageSize])

  // Reset to page 1 whenever the result set changes
  useEffect(() => {
    setPage(1)
  }, [filter, search, pageSize])

  const counts = useMemo(
    () => ({
      total: MOCK_JOBS.length,
      completed: MOCK_JOBS.filter((j) => j.status === 'completed').length,
      running: MOCK_JOBS.filter((j) => j.status === 'running').length,
      failed: MOCK_JOBS.filter((j) => j.status === 'failed').length,
    }),
    []
  )

  return (
    <div className="mx-auto max-w-[1400px]">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div className="mb-4">
          <h2 className="text-2xl font-semibold tracking-tight text-txt-hi">Jobs</h2>
          <p className="mt-1 text-sm text-txt-low">View and manage your tasks and their results.</p>
        </div>
        <Button icon="plus" onClick={onNewTask}>
          New Task
        </Button>
      </div>

      <div className="mb-5">
        <JobFilters filter={filter} onFilter={setFilter} search={search} onSearch={setSearch} />
      </div>

      <div className="flex flex-col gap-6 xl:flex-row">
        <div className="min-w-0 flex-1">
          <JobsTable jobs={paged} onSelect={onOpenJob} onRun={onNewTask} />

          {filtered.length === 0 && (
            <div className="card mt-4 flex flex-col items-center gap-2 py-10 text-center">
              <span className="text-sm text-txt-mid">No jobs match your filters.</span>
              <button
                type="button"
                className="btn-quiet btn text-xs"
                onClick={() => {
                  setFilter('all')
                  setSearch('')
                }}
              >
                Clear filters
              </button>
            </div>
          )}

          {filtered.length > 0 && (
            <div className="mt-4">
              <Pagination
                page={page}
                pageSize={pageSize}
                total={filtered.length}
                onPage={setPage}
                onPageSize={(s) => {
                  setPageSize(s)
                  setPage(1)
                }}
              />
            </div>
          )}
        </div>

        <aside className="w-full shrink-0 space-y-6 xl:w-[300px]" aria-label="Jobs sidebar">
          <div className="card p-4">
            <JobOverview counts={counts} />
          </div>
          <div className="card p-4">
            <RecentActivity items={MOCK_ACTIVITY} />
          </div>
          <div className="card p-4">
            <JobsQuickActions
              onNewTask={onNewTask}
              onViewArtifacts={() => onNavigate('artifacts')}
              onSearchKnowledge={() => onNavigate('workbench')}
            />
          </div>
        </aside>
      </div>
    </div>
  )
}