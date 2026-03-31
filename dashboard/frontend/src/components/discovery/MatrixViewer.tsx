import { useState } from 'react'
import { ChevronDown, ChevronRight, BarChart3, Target, Eye, CheckCircle2 } from 'lucide-react'
import LoadingSpinner from '../shared/LoadingSpinner'
import GapStateBadge, { PctRemainingBar } from './GapStateBadge'
import { useMatrix, useEvidence } from '../../hooks/useData'
import type { EvidenceEntry, MatrixEntry } from '../../api/types'

export default function MatrixViewer() {
  const { data: matrixData, isLoading } = useMatrix()
  const [expandedGap, setExpandedGap] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<'summary' | 'heatmap'>('summary')

  if (isLoading) return <div className="glass-card p-4 flex items-center justify-center"><LoadingSpinner /></div>

  if (!matrixData || matrixData.gaps.length === 0) {
    return (
      <div className="glass-card p-6 text-center">
        <BarChart3 className="w-6 h-6 text-text-muted mx-auto mb-2" />
        <p className="text-[11px] text-text-muted">No gap matrix data yet. Run gap analysis to populate.</p>
      </div>
    )
  }

  const { gaps, summary, paper_ids } = matrixData
  // Only show gaps with activity for summary view
  const activeGaps = gaps.filter(g => Object.keys(g.papers).length > 0)

  return (
    <div className="glass-card flex flex-col min-h-0 overflow-hidden h-full">
      {/* Header */}
      <div className="px-3 py-2 border-b border-border flex-shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h3 className="text-xs font-semibold text-text-primary">Gap Matrix</h3>
            <div className="flex items-center gap-2 text-[10px]">
              <StatChip icon={<Target className="w-3 h-3" />} label="Open" value={summary.open} color="text-error" />
              <StatChip icon={<Eye className="w-3 h-3" />} label="Inv." value={summary.investigating} color="text-warning" />
              <StatChip icon={<BarChart3 className="w-3 h-3" />} label="Part." value={summary.partial} color="text-accent-gold" />
              <StatChip icon={<CheckCircle2 className="w-3 h-3" />} label="Res." value={summary.resolved} color="text-success" />
            </div>
          </div>
          <div className="flex gap-0.5">
            <button
              onClick={() => setViewMode('summary')}
              className={`px-2 py-0.5 rounded text-[10px] transition-colors ${
                viewMode === 'summary' ? 'bg-accent-teal/15 text-accent-teal' : 'text-text-muted hover:text-text-secondary'
              }`}
            >
              List
            </button>
            <button
              onClick={() => setViewMode('heatmap')}
              className={`px-2 py-0.5 rounded text-[10px] transition-colors ${
                viewMode === 'heatmap' ? 'bg-accent-teal/15 text-accent-teal' : 'text-text-muted hover:text-text-secondary'
              }`}
            >
              Heatmap
            </button>
          </div>
        </div>
      </div>

      {/* Content — scrollable */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {viewMode === 'summary' ? (
          <div className="divide-y divide-border/50">
            {activeGaps
              .sort((a, b) => a.pct_remaining - b.pct_remaining)
              .slice(0, 20)
              .map((gap) => (
                <GapRow
                  key={gap.gap_id}
                  gap={gap}
                  isExpanded={expandedGap === gap.gap_id}
                  onToggle={() => setExpandedGap(expandedGap === gap.gap_id ? null : gap.gap_id)}
                />
              ))}
            {activeGaps.length > 20 && (
              <div className="px-3 py-2 text-[10px] text-text-muted text-center">
                Showing top 20 of {activeGaps.length} active gaps
              </div>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[9px]">
              <thead>
                <tr className="bg-bg-surface sticky top-0 z-10">
                  <th className="text-left px-2 py-1.5 text-text-muted font-mono font-normal sticky left-0 bg-bg-surface">Gap</th>
                  <th className="text-center px-1 py-1.5 text-text-muted font-normal">%</th>
                  {paper_ids.slice(0, 15).map((pid) => (
                    <th key={pid} className="text-center px-0.5 py-1.5 text-text-muted font-normal">
                      <span className="inline-block w-[50px] truncate" title={pid}>{pid.split('_')[0]}</span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border/30">
                {activeGaps.slice(0, 30).map((gap) => (
                  <tr key={gap.gap_id} className="hover:bg-bg-elevated/50">
                    <td className="px-2 py-1 font-mono text-accent-teal-light sticky left-0 bg-inherit">{gap.gap_id.replace('GAP_NEW_', 'G')}</td>
                    <td className="text-center px-1 py-1 text-text-muted">{Math.round(gap.pct_remaining)}</td>
                    {paper_ids.slice(0, 15).map((pid) => {
                      const pct = gap.papers[pid] || 0
                      return (
                        <td key={pid} className="text-center px-0.5 py-1">
                          {pct > 0 ? (
                            <span className={`inline-block w-5 h-5 rounded-sm leading-5 text-center font-mono ${
                              pct >= 40 ? 'bg-success/25 text-success' :
                              pct >= 15 ? 'bg-accent-gold/20 text-accent-gold' :
                              'bg-warning/15 text-warning'
                            }`}>
                              {pct}
                            </span>
                          ) : (
                            <span className="text-border">·</span>
                          )}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
            {paper_ids.length > 15 && (
              <div className="px-3 py-1.5 text-[9px] text-text-muted text-center">
                Showing 15 of {paper_ids.length} papers
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function StatChip({ icon, label, value, color }: { icon: React.ReactNode; label: string; value: number; color: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className={color}>{icon}</span>
      <span className="text-text-primary font-semibold tabular-nums">{value}</span>
      <span className="text-text-muted">{label}</span>
    </span>
  )
}

function GapRow({ gap, isExpanded, onToggle }: { gap: MatrixEntry; isExpanded: boolean; onToggle: () => void }) {
  const nonZeroPapers = Object.entries(gap.papers).filter(([, v]) => v > 0)

  return (
    <>
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-bg-elevated/50 transition-colors"
      >
        {isExpanded ? <ChevronDown className="w-3 h-3 text-text-muted" /> : <ChevronRight className="w-3 h-3 text-text-muted" />}
        <span className="text-[10px] font-mono text-accent-teal-light w-14 flex-shrink-0">{gap.gap_id.replace('GAP_NEW_', 'G')}</span>
        <GapStateBadge state={gap.gap_state} />
        <div className="flex-1 mx-2 max-w-[120px]">
          <PctRemainingBar pct={gap.pct_remaining} />
        </div>
        <span className="text-[10px] font-mono text-text-muted tabular-nums w-8 text-right">{Math.round(gap.pct_remaining)}%</span>
        <span className="text-[9px] text-text-muted">{nonZeroPapers.length}p</span>
      </button>

      {isExpanded && <EvidencePanel gapId={gap.gap_id} papers={gap.papers} />}
    </>
  )
}

function EvidencePanel({ gapId, papers }: { gapId: string; papers: Record<string, number> }) {
  const { data: evidence, isLoading } = useEvidence(gapId)

  return (
    <div className="px-3 pb-2 pl-8 bg-bg-surface/30">
      {isLoading ? (
        <div className="py-2"><LoadingSpinner /></div>
      ) : evidence && evidence.length > 0 ? (
        <div className="space-y-1 pt-1">
          {evidence.map((e: EvidenceEntry, i: number) => (
            <div key={i} className="px-2 py-1.5 rounded bg-bg-primary border border-border/50 text-[10px]">
              <div className="flex items-center gap-1.5 mb-0.5">
                <span className="font-mono text-accent-teal">{e.paper_id.split('_').slice(0, 2).join('_')}</span>
                <span className="font-mono text-success">-{e.pct_eliminated}%</span>
                <span className="text-text-muted">({Math.round(e.pct_remaining_before)}→{Math.round(e.pct_remaining_after)}%)</span>
              </div>
              {e.aspect_addressed && <p className="text-text-secondary leading-snug">{e.aspect_addressed}</p>}
            </div>
          ))}
        </div>
      ) : (
        <div className="flex flex-wrap gap-1 py-1">
          {Object.entries(papers)
            .filter(([, v]) => v > 0)
            .sort(([, a], [, b]) => b - a)
            .map(([pid, pct]) => (
              <span key={pid} className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-bg-primary border border-border/50">
                <span className="text-accent-teal">{pid.split('_')[0]}</span>
                <span className="text-success ml-0.5">-{pct}%</span>
              </span>
            ))}
        </div>
      )}
    </div>
  )
}
