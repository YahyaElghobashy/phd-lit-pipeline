import { useState } from 'react'
import { Search, Sparkles, CheckSquare, Square, RotateCcw, MessageSquare } from 'lucide-react'
import LoadingSpinner from '../shared/LoadingSpinner'
import GapStateBadge, { PctRemainingBar } from './GapStateBadge'
import { useDiscoveryGaps, useCachedQueries } from '../../hooks/useData'
import type { DiscoveryGap } from '../../api/types'

interface GapSelectorProps {
  selectedGapIds: string[]
  onSelectionChange: (ids: string[]) => void
  onGenerateQueries: (force?: boolean) => void
  isGenerating: boolean
}

const GAP_STATE_ORDER = ['Open', 'Under Investigation', 'Partially Resolved', 'Resolved']

export default function GapSelector({
  selectedGapIds,
  onSelectionChange,
  onGenerateQueries,
  isGenerating,
}: GapSelectorProps) {
  const { data: gaps, isLoading } = useDiscoveryGaps()
  const { data: cachedQueries } = useCachedQueries()
  const [search, setSearch] = useState('')
  const [stateFilter, setStateFilter] = useState<string>('')

  const filtered = gaps?.filter((g: DiscoveryGap) => {
    if (stateFilter && g.gap_state !== stateFilter) return false
    if (!search) return true
    const s = search.toLowerCase()
    return (
      g.gap_id?.toLowerCase().includes(s) ||
      g.gap_statement?.toLowerCase().includes(s) ||
      g.gap_type?.toLowerCase().includes(s)
    )
  })

  const sorted = filtered?.sort((a: DiscoveryGap, b: DiscoveryGap) => {
    const ai = GAP_STATE_ORDER.indexOf(a.gap_state)
    const bi = GAP_STATE_ORDER.indexOf(b.gap_state)
    if (ai !== bi) return ai - bi
    return b.pct_remaining - a.pct_remaining
  })

  const toggleGap = (gapId: string) => {
    if (selectedGapIds.includes(gapId)) {
      onSelectionChange(selectedGapIds.filter((id) => id !== gapId))
    } else {
      onSelectionChange([...selectedGapIds, gapId])
    }
  }

  const selectAllOpen = () => {
    const openIds = gaps?.filter((g: DiscoveryGap) => g.gap_state === 'Open').map((g: DiscoveryGap) => g.gap_id) ?? []
    onSelectionChange(openIds)
  }

  const clearSelection = () => onSelectionChange([])

  const stateCounts = gaps?.reduce((acc: Record<string, number>, g: DiscoveryGap) => {
    acc[g.gap_state] = (acc[g.gap_state] || 0) + 1
    return acc
  }, {} as Record<string, number>) ?? {}

  if (isLoading) return <div className="glass-card p-6 flex items-center justify-center"><LoadingSpinner /></div>

  return (
    <div className="glass-card flex flex-col min-h-0 overflow-hidden h-full">
      {/* Header */}
      <div className="px-3 py-2.5 border-b border-border flex-shrink-0">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-xs font-semibold text-text-primary">Research Gaps</h3>
          <span className="text-[10px] text-text-muted">{gaps?.length ?? 0} total</span>
        </div>

        {/* State filter pills */}
        <div className="flex gap-1 mb-2 flex-wrap">
          {GAP_STATE_ORDER.map((state) => {
            const count = stateCounts[state] || 0
            if (!count) return null
            return (
              <button
                key={state}
                onClick={() => setStateFilter(stateFilter === state ? '' : state)}
                className={`text-[10px] px-1.5 py-0.5 rounded transition-colors ${
                  stateFilter === state
                    ? 'bg-accent-teal/20 text-accent-teal'
                    : 'bg-bg-surface text-text-muted hover:text-text-secondary'
                }`}
              >
                {state.split(' ')[0]} ({count})
              </button>
            )
          })}
        </div>

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-text-muted" />
          <input
            type="text"
            placeholder="Filter gaps..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-7 pr-2 py-1.5 rounded-md bg-bg-surface border border-border text-[11px] text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-teal/50 transition-colors"
          />
        </div>
      </div>

      {/* Quick actions */}
      <div className="px-3 py-1.5 border-b border-border flex-shrink-0 flex gap-2 text-[10px]">
        <button onClick={selectAllOpen} className="text-accent-teal hover:text-accent-teal-light">
          Select All Open
        </button>
        <span className="text-border-bright">|</span>
        <button onClick={clearSelection} className="text-text-muted hover:text-text-secondary">
          Clear ({selectedGapIds.length})
        </button>
      </div>

      {/* Scrollable gap list */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {sorted?.map((gap: DiscoveryGap) => {
          const isSelected = selectedGapIds.includes(gap.gap_id)
          const isResolved = gap.gap_state === 'Resolved'
          return (
            <button
              key={gap.gap_id}
              onClick={() => toggleGap(gap.gap_id)}
              className={`w-full text-left px-3 py-2 border-b border-border/50 transition-colors ${
                isSelected ? 'bg-accent-teal/5' : 'hover:bg-bg-elevated'
              } ${isResolved ? 'opacity-40' : ''}`}
            >
              <div className="flex items-start gap-2">
                <div className="mt-0.5 flex-shrink-0">
                  {isSelected ? (
                    <CheckSquare className="w-3.5 h-3.5 text-accent-teal" />
                  ) : (
                    <Square className="w-3.5 h-3.5 text-text-muted/50" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <span className="text-[10px] font-mono text-accent-teal-light">{gap.gap_id}</span>
                    <GapStateBadge state={gap.gap_state} />
                    {cachedQueries?.[gap.gap_id] && (
                      <span className="flex items-center gap-0.5 text-[9px] px-1 py-0.5 rounded bg-accent-teal/10 text-accent-teal">
                        <MessageSquare className="w-2.5 h-2.5" />
                        {cachedQueries[gap.gap_id].queries.length}
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-text-secondary line-clamp-1 leading-snug">{gap.gap_statement}</p>
                  <div className="mt-1 flex items-center gap-1.5">
                    <div className="flex-1">
                      <PctRemainingBar pct={gap.pct_remaining} />
                    </div>
                    <span className="text-[9px] text-text-muted tabular-nums">{Math.round(gap.pct_remaining)}%</span>
                  </div>
                </div>
              </div>
            </button>
          )
        })}
      </div>

      {/* Footer — generate button */}
      <div className="px-3 py-2.5 border-t border-border flex-shrink-0">
        {(() => {
          const cachedCount = selectedGapIds.filter((id) => cachedQueries?.[id]).length
          const newCount = selectedGapIds.length - cachedCount
          return (
            <div className="flex gap-1.5">
              <button
                onClick={() => onGenerateQueries(false)}
                disabled={selectedGapIds.length === 0 || isGenerating}
                className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-accent-teal text-white text-xs font-medium hover:bg-accent-teal/80 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Sparkles className="w-3.5 h-3.5" />
                {isGenerating
                  ? 'Generating...'
                  : cachedCount > 0 && newCount > 0
                  ? `Generate (${newCount} new, ${cachedCount} cached)`
                  : cachedCount > 0 && newCount === 0
                  ? `Load Cached (${cachedCount})`
                  : `Generate Queries (${selectedGapIds.length})`}
              </button>
              {cachedCount > 0 && (
                <button
                  onClick={() => onGenerateQueries(true)}
                  disabled={selectedGapIds.length === 0 || isGenerating}
                  className="flex items-center gap-1 px-2 py-2 rounded-lg bg-bg-surface border border-border text-[10px] text-text-muted hover:text-text-secondary hover:border-accent-teal/30 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  title="Regenerate all (ignore cache)"
                >
                  <RotateCcw className="w-3 h-3" />
                </button>
              )}
            </div>
          )
        })()}
      </div>
    </div>
  )
}
