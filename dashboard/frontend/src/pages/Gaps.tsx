import { useState, useEffect } from 'react'
import { Search, ChevronDown, ChevronRight, Zap, BookOpen, Eye, BarChart3 } from 'lucide-react'
import Header from '../components/layout/Header'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import { CoverageBadge } from '../components/shared/Badge'
import { useGaps } from '../hooks/useData'

const TIER_STYLES: Record<string, { bg: string; text: string; icon: React.ReactNode }> = {
  Core: { bg: 'bg-blue-500/20 border-blue-400/40', text: 'text-blue-300', icon: <Zap className="w-3 h-3" /> },
  Supporting: { bg: 'bg-amber-500/20 border-amber-400/40', text: 'text-amber-300', icon: <BookOpen className="w-3 h-3" /> },
  Niche: { bg: 'bg-gray-500/20 border-gray-400/40', text: 'text-gray-400', icon: <Eye className="w-3 h-3" /> },
}

function TierBadge({ tier }: { tier: string }) {
  const style = TIER_STYLES[tier]
  if (!style) return null
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium border ${style.bg} ${style.text}`}>
      {style.icon}
      {tier}
    </span>
  )
}

function PctBar({ pct }: { pct: number }) {
  const remaining = Math.max(0, Math.min(100, pct))
  const eliminated = 100 - remaining
  const color = remaining > 80 ? 'bg-red-500' : remaining > 40 ? 'bg-amber-500' : remaining > 10 ? 'bg-cyan-500' : 'bg-green-500'
  return (
    <div className="flex items-center gap-2 min-w-[120px]">
      <div className="flex-1 h-1.5 bg-bg-surface rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${eliminated}%` }} />
      </div>
      <span className="text-xs font-mono text-text-muted whitespace-nowrap">{remaining.toFixed(0)}%</span>
    </div>
  )
}

export default function Gaps() {
  const [search, setSearch] = useState('')
  const [tierFilter, setTierFilter] = useState('')
  const [expandedGap, setExpandedGap] = useState<string | null>(null)
  const [evidenceData, setEvidenceData] = useState<Record<string, any>>({})

  const { data: gaps, isLoading } = useGaps(new URLSearchParams())

  const filtered = gaps?.filter((g: any) => {
    if (tierFilter && g.tier !== tierFilter) return false
    if (!search) return true
    const s = search.toLowerCase()
    return (
      g.gap_id?.toLowerCase().includes(s) ||
      g.gap_statement?.toLowerCase().includes(s) ||
      g.gap_type?.toLowerCase().includes(s)
    )
  })

  // Fetch evidence when gap is expanded
  useEffect(() => {
    if (expandedGap && !evidenceData[expandedGap]) {
      fetch(`/api/gaps/${expandedGap}/evidence`)
        .then(res => res.ok ? res.json() : null)
        .then(data => {
          if (data) setEvidenceData(prev => ({ ...prev, [expandedGap]: data }))
        })
        .catch(() => {})
    }
  }, [expandedGap])

  if (isLoading) return <LoadingSpinner />

  // Tier stats
  const tierCounts = gaps?.reduce((acc: Record<string, number>, g: any) => {
    const tier = g.tier || 'Unclassified'
    acc[tier] = (acc[tier] || 0) + 1
    return acc
  }, {} as Record<string, number>) || {}

  // Sort: Core first, then Supporting, then Niche, then Unclassified
  const tierOrder: Record<string, number> = { Core: 0, Supporting: 1, Niche: 2, Unclassified: 3 }
  const sorted = [...(filtered || [])].sort((a: any, b: any) => {
    const ta = tierOrder[a.tier || 'Unclassified'] ?? 3
    const tb = tierOrder[b.tier || 'Unclassified'] ?? 3
    if (ta !== tb) return ta - tb
    return (a.pct_remaining ?? 100) - (b.pct_remaining ?? 100)
  })

  return (
    <div>
      <Header title="Research Gaps" subtitle={`${gaps?.length ?? 0} gaps tracked | Tier-classified for prioritized analysis`} />

      {/* Tier Summary Bar */}
      <div className="flex gap-3 mb-5 flex-wrap">
        {['Core', 'Supporting', 'Niche', 'Unclassified'].map(tier => {
          const count = tierCounts[tier] || 0
          if (count === 0) return null
          const isActive = tierFilter === tier
          return (
            <button
              key={tier}
              onClick={() => setTierFilter(isActive ? '' : tier)}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs transition-colors ${
                isActive ? 'bg-accent-teal/20 border border-accent-teal/40' : 'glass-card'
              }`}
            >
              <TierBadge tier={tier} />
              <span className="font-semibold">{count}</span>
            </button>
          )
        })}
        <div className="ml-auto flex items-center gap-2 text-xs text-text-muted">
          <BarChart3 className="w-4 h-4" />
          <span>Avg remaining: {gaps?.length ? (gaps.reduce((s: number, g: any) => s + (g.pct_remaining ?? 100), 0) / gaps.length).toFixed(1) : 0}%</span>
        </div>
      </div>

      {/* Search */}
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
      </div>

      {/* Gap Cards */}
      <div className="space-y-2">
        {sorted?.map((gap: any) => {
          const isExpanded = expandedGap === gap.gap_id
          const evidence = evidenceData[gap.gap_id]
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
                  <div className="flex items-center gap-3 mb-1 flex-wrap">
                    <span className="text-xs font-mono text-accent-teal-light">{gap.gap_id}</span>
                    {gap.tier && <TierBadge tier={gap.tier} />}
                    {gap.gap_type && <span className="text-xs text-text-muted px-2 py-0.5 rounded bg-bg-surface">{gap.gap_type}</span>}
                    <CoverageBadge level={gap.gap_state || gap.coverage_level} />
                  </div>
                  <p className="text-sm text-text-secondary truncate">{gap.gap_statement}</p>
                </div>
                <PctBar pct={gap.pct_remaining ?? 100} />
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
                    {gap.tier_justification && (
                      <div>
                        <span className="text-xs text-text-muted font-mono block mb-1">Tier Justification</span>
                        <p className="text-sm text-text-secondary italic">{gap.tier_justification}</p>
                      </div>
                    )}
                    <div className="grid grid-cols-2 gap-3">
                      {gap.paper_assignment && (
                        <div>
                          <span className="text-xs text-text-muted font-mono block mb-1">Paper Assignment</span>
                          <p className="text-sm text-text-secondary">{gap.paper_assignment}</p>
                        </div>
                      )}
                      {gap.methodology_needed && (
                        <div>
                          <span className="text-xs text-text-muted font-mono block mb-1">Methodology</span>
                          <p className="text-sm text-text-secondary">{gap.methodology_needed}</p>
                        </div>
                      )}
                    </div>

                    {/* Evidence & Reasoning */}
                    {evidence && (
                      <div className="mt-2">
                        <span className="text-xs text-text-muted font-mono block mb-2">
                          Evidence Chain ({evidence.evidence?.length || 0} entries, {evidence.reasoning?.length || 0} with full reasoning)
                        </span>
                        <div className="space-y-2">
                          {(evidence.reasoning || evidence.evidence || []).slice(0, 5).map((r: any, i: number) => (
                            <div key={i} className="bg-bg-surface rounded-lg p-3 border border-border/50">
                              <div className="flex items-center gap-2 mb-1">
                                <span className="text-xs font-mono text-accent-teal">{r.paper_id}</span>
                                <span className="text-xs text-accent-gold font-semibold">{r.pct_eliminated}% eliminated</span>
                                {r.confidence?.tier || r.confidence_tier ? (
                                  <span className="text-xs text-text-muted">
                                    Confidence: {r.confidence?.tier || r.confidence_tier}
                                  </span>
                                ) : null}
                              </div>
                              {(r.reasoning || r.aspect_addressed) && (
                                <p className="text-xs text-text-secondary mt-1 whitespace-pre-wrap">
                                  {r.reasoning || r.aspect_addressed}
                                </p>
                              )}
                            </div>
                          ))}
                        </div>
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
