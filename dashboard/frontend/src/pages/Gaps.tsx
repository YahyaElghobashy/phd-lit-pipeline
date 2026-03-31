import { useState } from 'react'
import { Search, ChevronDown, ChevronRight } from 'lucide-react'
import Header from '../components/layout/Header'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import { CoverageBadge } from '../components/shared/Badge'
import { useGaps } from '../hooks/useData'

const COVERAGE_LEVELS = ['', 'NOT ADDRESSED', 'PARTIALLY ADDRESSED', 'SUBSTANTIALLY COVERED', 'DIRECTLY TACKLED']

export default function Gaps() {
  const [search, setSearch] = useState('')
  const [coverageFilter, setCoverageFilter] = useState('')
  const [expandedGap, setExpandedGap] = useState<string | null>(null)

  const params = new URLSearchParams()
  if (coverageFilter) params.set('coverage', coverageFilter)
  const { data: gaps, isLoading } = useGaps(params)

  const filtered = gaps?.filter((g) => {
    if (!search) return true
    const s = search.toLowerCase()
    return (
      g.gap_id?.toLowerCase().includes(s) ||
      g.gap_statement?.toLowerCase().includes(s) ||
      g.gap_type?.toLowerCase().includes(s)
    )
  })

  if (isLoading) return <LoadingSpinner />

  // Summary counts
  const coverageCounts = gaps?.reduce((acc, g) => {
    const level = g.coverage_level || 'UNKNOWN'
    acc[level] = (acc[level] || 0) + 1
    return acc
  }, {} as Record<string, number>) || {}

  return (
    <div>
      <Header title="Research Gaps" subtitle={`${gaps?.length ?? 0} gaps tracked across the literature`} />

      {/* Summary Bar */}
      <div className="flex gap-3 mb-5">
        {Object.entries(coverageCounts).map(([level, count]) => (
          <button
            key={level}
            onClick={() => setCoverageFilter(coverageFilter === level ? '' : level)}
            className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs transition-colors ${
              coverageFilter === level ? 'bg-accent-teal/20 border border-accent-teal/40' : 'glass-card'
            }`}
          >
            <CoverageBadge level={level} />
            <span className="font-semibold">{count}</span>
          </button>
        ))}
      </div>

      {/* Search & Filters */}
      <div className="flex gap-3 mb-5">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
          <input
            type="text"
            placeholder="Search gaps by ID, statement, or type..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 rounded-lg bg-bg-surface border border-border text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-teal/50 transition-colors"
          />
        </div>
        <select
          value={coverageFilter}
          onChange={(e) => setCoverageFilter(e.target.value)}
          className="px-3 py-2.5 rounded-lg bg-bg-surface border border-border text-sm text-text-secondary focus:outline-none focus:border-accent-teal/50"
        >
          {COVERAGE_LEVELS.map((l) => (
            <option key={l} value={l}>{l || 'All Coverage Levels'}</option>
          ))}
        </select>
      </div>

      {/* Gap Cards */}
      <div className="space-y-2">
        {filtered?.map((gap) => {
          const isExpanded = expandedGap === gap.gap_id
          return (
            <div key={gap.gap_id} className="glass-card overflow-hidden">
              <button
                onClick={() => setExpandedGap(isExpanded ? null : gap.gap_id)}
                className="w-full flex items-start gap-4 px-5 py-4 text-left hover:bg-bg-elevated transition-colors"
              >
                <div className="mt-0.5">
                  {isExpanded ? <ChevronDown className="w-4 h-4 text-text-muted" /> : <ChevronRight className="w-4 h-4 text-text-muted" />}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 mb-1">
                    <span className="text-xs font-mono text-accent-teal-light">{gap.gap_id}</span>
                    <CoverageBadge level={gap.coverage_level} />
                    {gap.gap_type && <span className="text-xs text-text-muted px-2 py-0.5 rounded bg-bg-surface">{gap.gap_type}</span>}
                    {gap.severity && <span className="text-xs text-text-muted">Severity: {gap.severity}</span>}
                  </div>
                  <p className="text-sm text-text-secondary truncate">{gap.gap_statement}</p>
                </div>
                {gap.priority_score && (
                  <span className="text-xs font-mono text-accent-gold whitespace-nowrap">P{gap.priority_score}</span>
                )}
              </button>

              {isExpanded && (
                <div className="px-5 pb-4 border-t border-border ml-9">
                  <div className="grid gap-3 mt-3">
                    {gap.gap_statement && (
                      <div>
                        <span className="text-xs text-text-muted font-mono block mb-1">Statement</span>
                        <p className="text-sm text-text-secondary">{gap.gap_statement}</p>
                      </div>
                    )}
                    <div className="grid grid-cols-2 gap-3">
                      {gap.potential_hypothesis && (
                        <div>
                          <span className="text-xs text-text-muted font-mono block mb-1">Hypothesis</span>
                          <p className="text-sm text-text-secondary">{gap.potential_hypothesis}</p>
                        </div>
                      )}
                      {gap.variables_needed && (
                        <div>
                          <span className="text-xs text-text-muted font-mono block mb-1">Variables Needed</span>
                          <p className="text-sm text-text-secondary">{gap.variables_needed}</p>
                        </div>
                      )}
                      {gap.methodology_needed && (
                        <div>
                          <span className="text-xs text-text-muted font-mono block mb-1">Methodology</span>
                          <p className="text-sm text-text-secondary">{gap.methodology_needed}</p>
                        </div>
                      )}
                      {gap.paper_assignment && (
                        <div>
                          <span className="text-xs text-text-muted font-mono block mb-1">Paper Assignment</span>
                          <p className="text-sm text-text-secondary">{gap.paper_assignment}</p>
                        </div>
                      )}
                    </div>
                    {gap.covering_paper_ids && (
                      <div>
                        <span className="text-xs text-text-muted font-mono block mb-1">Covering Papers</span>
                        <p className="text-sm text-accent-teal">{gap.covering_paper_ids}</p>
                      </div>
                    )}
                    {gap.coverage_notes && (
                      <div>
                        <span className="text-xs text-text-muted font-mono block mb-1">Coverage Notes</span>
                        <p className="text-sm text-text-secondary italic">{gap.coverage_notes}</p>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
