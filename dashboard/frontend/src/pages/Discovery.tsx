import { useState, useCallback, useEffect, useRef } from 'react'
import Header from '../components/layout/Header'
import GapSelector from '../components/discovery/GapSelector'
import QueryEditor from '../components/discovery/QueryEditor'
import SearchResults from '../components/discovery/SearchResults'
import PipelineActions from '../components/discovery/PipelineActions'
import MatrixViewer from '../components/discovery/MatrixViewer'
import { api } from '../api/client'
import type { GapQueries, GapSearchResponse } from '../api/types'
import { useActionStatus, useDiscoveryGaps } from '../hooks/useData'
import { useQueryClient } from '@tanstack/react-query'
import { showToast } from '../components/shared/Toast'

export default function Discovery() {
  const [selectedGapIds, setSelectedGapIds] = useState<string[]>([])
  const [generatedQueries, setGeneratedQueries] = useState<GapQueries | null>(null)
  const [searchResponse, setSearchResponse] = useState<GapSearchResponse | null>(null)
  const [selectedPaperDois, setSelectedPaperDois] = useState<string[]>([])
  const [isGenerating, setIsGenerating] = useState(false)
  const [isSearching, setIsSearching] = useState(false)
  const [genError, setGenError] = useState<string | null>(null)

  const { data: actionStatus } = useActionStatus()
  const { data: gaps } = useDiscoveryGaps()
  const queryClient = useQueryClient()
  const isRunning = actionStatus?.is_running ?? false

  const gapStatements: Record<string, string> = {}
  if (gaps) {
    for (const g of gaps) {
      gapStatements[g.gap_id] = g.gap_statement
    }
  }

  const handleGenerateQueries = useCallback(async (force = false) => {
    if (selectedGapIds.length === 0) {
      showToast('Select at least one gap first', 'info')
      return
    }
    setIsGenerating(true)
    setGenError(null)
    setSearchResponse(null)
    showToast(`${force ? 'Regenerating' : 'Generating'} queries for ${selectedGapIds.length} gap${selectedGapIds.length > 1 ? 's' : ''}...`, 'info')
    try {
      const data = await api.generateQueries(selectedGapIds, force)
      setGeneratedQueries(data.queries)
      queryClient.invalidateQueries({ queryKey: ['cachedQueries'] })
      const totalQ = Object.values(data.queries).flat().length
      const cacheMsg = data.from_cache > 0 ? ` (${data.from_cache} from cache)` : ''
      showToast(`${totalQ} queries for ${data.gap_count} gaps${cacheMsg}`, 'success')
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Query generation failed'
      setGenError(msg)
      showToast(`Error: ${msg}`, 'info')
    } finally {
      setIsGenerating(false)
    }
  }, [selectedGapIds, queryClient])

  const scoringPollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [isScoringBg, setIsScoringBg] = useState(false)

  // Clean up polling on unmount
  useEffect(() => {
    return () => {
      if (scoringPollRef.current) clearInterval(scoringPollRef.current)
    }
  }, [])

  const handleSearch = useCallback(async (selectedQueries: GapQueries) => {
    setIsSearching(true)
    showToast('Searching OpenAlex + Semantic Scholar...', 'info')
    // Stop any existing scoring poll
    if (scoringPollRef.current) {
      clearInterval(scoringPollRef.current)
      scoringPollRef.current = null
    }
    try {
      const relevantStatements: Record<string, string> = {}
      for (const gapId of Object.keys(selectedQueries)) {
        if (gapStatements[gapId]) {
          relevantStatements[gapId] = gapStatements[gapId]
        }
      }
      const response = await api.searchGaps(selectedQueries, relevantStatements)
      setSearchResponse(response)
      showToast(
        `Found ${response.dedup_stats.unique} unique papers — scoring relevance in background...`,
        'success'
      )

      // Start polling for background scoring results
      if ((response as any).scoring_status === 'started') {
        setIsScoringBg(true)
        let pollCount = 0
        scoringPollRef.current = setInterval(async () => {
          pollCount++
          // Safety: stop after 40 polls (~2 minutes)
          if (pollCount > 40) {
            clearInterval(scoringPollRef.current!)
            scoringPollRef.current = null
            setIsScoringBg(false)
            return
          }
          try {
            const status = await api.getScoringStatus()
            if (status.scored_count > 0) {
              setSearchResponse(prev => {
                if (!prev) return prev
                return { ...prev, results: prev.results.map(r => {
                  const doi = (r as any).DOI || (r as any).doi || ''
                  const titleKey = ((r as any).title || '').trim().toLowerCase().slice(0, 80)
                  const key = doi || titleKey
                  const scored = status.scores[key]
                  if (scored) {
                    return { ...r, relevance_score: scored.relevance_score, relevance_reason: scored.relevance_reason }
                  }
                  return r
                })}
              })
            }
            if (!status.is_scoring) {
              clearInterval(scoringPollRef.current!)
              scoringPollRef.current = null
              setIsScoringBg(false)
              if (status.scored_count > 0) {
                showToast(`Relevance scoring complete — ${status.scored_count} papers scored`, 'success')
              }
            }
          } catch {
            clearInterval(scoringPollRef.current!)
            scoringPollRef.current = null
            setIsScoringBg(false)
          }
        }, 3000)
      }
    } catch {
      showToast('Search failed — check connection', 'info')
    } finally {
      setIsSearching(false)
    }
  }, [gapStatements])

  const activeStep =
    searchResponse ? 3 :
    generatedQueries ? 2 :
    selectedGapIds.length > 0 ? 1 :
    0

  return (
    <div className="flex flex-col h-[calc(100vh-40px)] overflow-hidden">
      <div className="flex-shrink-0">
        <Header
          title="Discovery"
          subtitle="Gap-driven paper discovery, extraction & analysis pipeline"
        />
      </div>

      {/* Step indicator */}
      <div className="flex items-center gap-2 mb-3 flex-shrink-0">
        <StepPill step={1} label="Select Gaps" active={activeStep >= 1} />
        <StepConnector active={activeStep >= 2} />
        <StepPill step={2} label="Edit Queries" active={activeStep >= 2} />
        <StepConnector active={activeStep >= 3} />
        <StepPill step={3} label="Search & Score" active={activeStep >= 3} />
        <StepConnector active={isRunning} />
        <StepPill step={4} label="Pipeline" active={isRunning} />
      </div>

      {/* Status banners */}
      {isGenerating && (
        <div className="flex-shrink-0 mb-2 px-3 py-2 rounded-lg bg-accent-teal/10 border border-accent-teal/20 flex items-center gap-2 text-xs text-accent-teal animate-pulse">
          <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" strokeDasharray="32" strokeLinecap="round" /></svg>
          Claude Sonnet is generating search queries for {selectedGapIds.length} gap{selectedGapIds.length > 1 ? 's' : ''}...
        </div>
      )}
      {genError && (
        <div className="flex-shrink-0 mb-2 px-3 py-2 rounded-lg bg-error/10 border border-error/20 text-xs text-error">
          Query generation failed: {genError}
        </div>
      )}
      {isScoringBg && (
        <div className="flex-shrink-0 mb-2 px-3 py-2 rounded-lg bg-accent-gold/10 border border-accent-gold/20 flex items-center gap-2 text-xs text-accent-gold">
          <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" strokeDasharray="32" strokeLinecap="round" /></svg>
          Claude Sonnet is scoring relevance in the background — scores will appear as they arrive...
        </div>
      )}

      {/* Scrollable main content */}
      <div className="flex-1 min-h-0 overflow-y-auto pb-4">
        {/* Top: 3-column panels — fixed height so they don't expand infinitely */}
        <div className="h-[420px] grid grid-cols-[1fr_1.4fr_1.6fr] gap-3 mb-3">
          <GapSelector
            selectedGapIds={selectedGapIds}
            onSelectionChange={(ids) => setSelectedGapIds(ids)}
            onGenerateQueries={handleGenerateQueries}
            isGenerating={isGenerating}
          />
          <QueryEditor
            queries={generatedQueries}
            onQueriesChange={setGeneratedQueries}
            onSearch={handleSearch}
            gapStatements={gapStatements}
            isSearching={isSearching}
          />
          <SearchResults
            searchResponse={searchResponse}
            selectedPaperDois={selectedPaperDois}
            onPaperSelection={setSelectedPaperDois}
            isSearching={isSearching}
            isScoringBg={isScoringBg}
            onAddToVerification={async (papers) => {
              showToast(`Downloading ${papers.length} paper${papers.length > 1 ? 's' : ''} for gap verification...`, 'info')
              try {
                const result = await api.stagePapers(papers, 'verify')
                showToast(
                  `${result.downloaded} PDF${result.downloaded !== 1 ? 's' : ''} downloaded` +
                  (result.download_failed > 0 ? `, ${result.download_failed} failed` : '') +
                  `. ${result.next_step}`,
                  result.downloaded > 0 ? 'success' : 'info'
                )
              } catch {
                showToast('Failed to stage papers', 'info')
              }
            }}
            onAddToPaperList={async (papers) => {
              showToast(`Downloading ${papers.length} paper${papers.length > 1 ? 's' : ''} for extraction...`, 'info')
              try {
                const result = await api.stagePapers(papers, 'extract')
                showToast(
                  `${result.downloaded} PDF${result.downloaded !== 1 ? 's' : ''} downloaded` +
                  (result.download_failed > 0 ? `, ${result.download_failed} failed` : '') +
                  `. ${result.next_step}`,
                  result.downloaded > 0 ? 'success' : 'info'
                )
              } catch {
                showToast('Failed to stage papers', 'info')
              }
            }}
          />
        </div>

        {/* Pipeline Actions (with embedded terminal) */}
        <div className="mb-3">
          <PipelineActions selectedPaperCount={selectedPaperDois.length} />
        </div>

        {/* Matrix */}
        <div className="mb-4">
          <MatrixViewer />
        </div>
      </div>
    </div>
  )
}

function StepPill({ step, label, active }: { step: number; label: string; active: boolean }) {
  return (
    <div className={`flex items-center gap-1.5 px-2 py-1 rounded-full text-[11px] transition-colors ${
      active
        ? 'bg-accent-teal/15 text-accent-teal border border-accent-teal/30'
        : 'bg-bg-surface text-text-muted border border-border'
    }`}>
      <span className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] font-semibold ${
        active ? 'bg-accent-teal text-white' : 'bg-bg-elevated text-text-muted'
      }`}>
        {step}
      </span>
      <span className="font-medium">{label}</span>
    </div>
  )
}

function StepConnector({ active }: { active: boolean }) {
  return (
    <div className={`w-4 h-px transition-colors ${active ? 'bg-accent-teal/40' : 'bg-border'}`} />
  )
}
