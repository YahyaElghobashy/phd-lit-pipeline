import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search } from 'lucide-react'
import Header from '../components/layout/Header'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import { StatusBadge, RelevanceBadge } from '../components/shared/Badge'
import { usePapers } from '../hooks/useData'

export default function Papers() {
  const [search, setSearch] = useState('')
  const params = new URLSearchParams()
  if (search) params.set('search', search)
  const { data: papers, isLoading } = usePapers(params)
  const navigate = useNavigate()

  if (isLoading) return <LoadingSpinner />

  return (
    <div>
      <Header title="Papers" subtitle={`${papers?.length ?? 0} papers in the pipeline`} />

      {/* Search */}
      <div className="relative mb-5">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
        <input
          type="text"
          placeholder="Search papers by ID, filename, journal, or theme..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-10 pr-4 py-2.5 rounded-lg bg-bg-surface border border-border text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-teal/50 transition-colors"
        />
      </div>

      {/* Table */}
      <div className="glass-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left text-xs font-medium text-text-muted uppercase tracking-wider px-4 py-3">Paper ID</th>
                <th className="text-left text-xs font-medium text-text-muted uppercase tracking-wider px-4 py-3">Year</th>
                <th className="text-left text-xs font-medium text-text-muted uppercase tracking-wider px-4 py-3">Journal</th>
                <th className="text-left text-xs font-medium text-text-muted uppercase tracking-wider px-4 py-3">Theme</th>
                <th className="text-left text-xs font-medium text-text-muted uppercase tracking-wider px-4 py-3">Relevance</th>
                <th className="text-left text-xs font-medium text-text-muted uppercase tracking-wider px-4 py-3">Status</th>
                <th className="text-right text-xs font-medium text-text-muted uppercase tracking-wider px-4 py-3">Duration</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {papers?.map((p) => (
                <tr
                  key={p.paper_id || p.original_filename}
                  onClick={() => p.paper_id && navigate(`/papers/${p.paper_id}`)}
                  className={`transition-colors ${p.paper_id ? 'cursor-pointer hover:bg-bg-elevated' : 'opacity-50'}`}
                >
                  <td className="px-4 py-3 text-sm font-mono text-accent-teal-light">{p.paper_id || '—'}</td>
                  <td className="px-4 py-3 text-sm text-text-secondary">{p.year || '—'}</td>
                  <td className="px-4 py-3 text-sm text-text-secondary max-w-[200px] truncate">{p.journal || '—'}</td>
                  <td className="px-4 py-3 text-sm text-text-secondary max-w-[180px] truncate">{p.theme || '—'}</td>
                  <td className="px-4 py-3"><RelevanceBadge tier={p.relevance_tier} /></td>
                  <td className="px-4 py-3"><StatusBadge status={p.status} /></td>
                  <td className="px-4 py-3 text-sm text-text-muted text-right font-mono">
                    {p.duration_seconds ? `${Math.round(p.duration_seconds)}s` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
