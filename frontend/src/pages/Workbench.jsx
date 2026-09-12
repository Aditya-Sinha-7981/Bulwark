import SovereigntyIndicator from "../components/SovereigntyIndicator";

export default function Workbench() {
  return (
    <div className="workbench min-h-screen bg-slate-50">
      <header className="workbench__standing-panel border-b border-slate-200 bg-white sticky top-0 z-10" data-testid="workbench-standing-panel">
        <div className="max-w-7xl mx-auto px-4 py-3">
          <SovereigntyIndicator />
        </div>
      </header>

      <main className="workbench__main max-w-7xl mx-auto px-4 py-6">
        <div className="workbench__job-flow-placeholder text-center text-slate-400 py-12" data-testid="workbench-job-flow-placeholder">
          <p className="text-lg font-medium mb-2">Chat / Job Trace / Artifacts / RAG Evidence</p>
          <p className="text-sm">(Task 16.a scope — not yet implemented)</p>
        </div>
      </main>
    </div>
  );
}