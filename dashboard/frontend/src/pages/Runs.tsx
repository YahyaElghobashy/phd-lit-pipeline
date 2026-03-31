import { useState } from 'react'
import { Clock, CheckCircle, XCircle, ChevronDown, ChevronRight, FileText } from 'lucide-react'
import Header from '../components/layout/Header'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import { StatusBadge, RelevanceBadge } from '../components/shared/Badge'
import { useRuns, useRun } from '../hooks/useData'

function RunCard({ run, isExpanded, onToggle }: { run: any; isExpanded: boolean; onToggle: () => void }) {
  const { data: detail } = useRun(isExpanded ? run.run_id : '')

  const date = new Date(run.timestamp)
  const formattedDate = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  const formattedTime = date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
  const formatDuration = (s: number) => s >= 60 ? `${Math.round(s / 60)}m ${Math.round(s % 60)}s` : `${Math.round(s)}s`

  return (
    <div className="glass-card overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-4 px-5 py-4 text-left hover:bg-bg-elevated transition-colors"
      >
        <div className="flex items-center gap-2">
          {isExpanded ? <ChevronDown className="w-4 h-4 text-text-muted" /> : <ChevronRight className="w-4 h-4 text-text-muted" />}
          <Clock className="w-4 h-4 text-text-muted" />
        </div>

        <div className="flex-1">
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium">{formattedDate}</span>
            <span className="text-xs text-text-muted">{formattedTime}</span>
          </div>
          <p className="text-xs text-text-muted mt-0.5">{run.run_id}</p>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5 text-xs">
            <FileText className="w-3.5 h-3.5 text-text-muted" />
            <span className="text-text-secondary">{run.total_queued} queued</span>
          </div>
          <div className="flex items-center gap-1.5 text-xs">
            <CheckCircle className="w-3.5 h-3.5 text-success" />
            <span className="text-success">{run.completed}</span>
          </div>
          <div className="flex items-center gap-1.5 text-xs">
            <XCircle className="w-3.5 h-3.5 text-error" />
            <span className="text-error">{run.failed}</span>
          </div>
          {run.total_duration && (
            <span className="text-xs font-mono text-text-muted">{formatDuration(run.total_duration)}</span>
          )}
        </div>
      </button>

      {isExpanded && detail && (
        <div className="border-t border-border px-5 pb-4">
          <table className="w-full mt-3">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left text-xs font-medium text-text-muted uppercase tracking-wider px-3 py-2">Paper</th>
                <th className="text-left text-xs font-medium text-text-muted uppercase tracking-wider px-3 py-2">Status</th>
                <th className="text-left text-xs font-medium text-text-muted uppercase tracking-wider px-3 py-2">Relevance</th>
                <th className="text-left text-xs font-medium text-text-muted uppercase tracking-wider px-3 py-2">Failure</th>
                <th className="text-right text-xs font-medium text-text-muted uppercase tracking-wider px-3 py-2">Duration</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {detail.papers?.map((p: any, i: number) => (
                <tr key={i}>
                  <td className="px-3 py-2 text-sm font-mono text-accent-teal-light">{p.paper_id || p.filename}</td>
                  <td className="px-3 py-2"><StatusBadge status={p.status} /></td>
                  <td className="px-3 py-2">{p.relevance_tier ? <RelevanceBadge tier={p.relevance_tier} /> : <span className="text-xs text-text-muted">—</span>}</td>
                  <td className="px-3 py-2 text-xs text-text-muted max-w-[200px] truncate">{p.failure_reason || '—'}</td>
                  <td className="px-3 py-2 text-xs font-mono text-text-muted text-right">{p.duration ? formatDuration(p.duration) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default function Runs() {
  const { data: runs, isLoading } = useRuns()
  const [expandedRun, setExpandedRun] = useState<string | null>(null)

  if (isLoading) return <LoadingSpinner />

  return (
    <div>
      <Header title="Run History" subtitle={`${runs?.length ?? 0} pipeline runs recorded`} />

      <div className="space-y-3">
        {runs?.map((run) => (
          <RunCard
            key={run.run_id}
            run={run}
            isExpanded={expandedRun === run.run_id}
            onToggle={() => setExpandedRun(expandedRun === run.run_id ? null : run.run_id)}
          />
        ))}
        {(!runs || runs.length === 0) && (
          <div className="glass-card p-12 text-center">
            <Clock className="w-8 h-8 text-text-muted mx-auto mb-3" />
            <p className="text-sm text-text-muted">No run reports found</p>
          </div>
        )}
      </div>
    </div>
  )
}
