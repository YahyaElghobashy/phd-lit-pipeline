import { useState, useEffect, useRef } from 'react'
import { Search, ExternalLink, Users, Award, BookOpen, ArrowRight, CheckSquare, Square, Star, ShieldCheck, Library, Loader2, Sparkles, Filter } from 'lucide-react'
import { api } from '../../api/client'
import type { SearchResult, GapSearchResponse } from '../../api/types'

interface SearchResultsProps {
  searchResponse: GapSearchResponse | null
  selectedPaperDois: string[]
  onPaperSelection: (dois: string[]) => void
  isSearching: boolean
  isScoringBg?: boolean
  onAddToVerification?: (papers: Record<string, any>[]) => void
  onAddToPaperList?: (papers: Record<string, any>[]) => void
}

export default function SearchResults({
  searchResponse,
  selectedPaperDois,
  onPaperSelection,
  isSearching,
  isScoringBg = false,
  onAddToVerification,
  onAddToPaperList,
}: SearchResultsProps) {
  const [adhocQuery, setAdhocQuery] = useState('')
  const [adhocResults, setAdhocResults] = useState<SearchResult[]>([])
  const [adhocSearched, setAdhocSearched] = useState(false)
  const [isAdhocSearching, setIsAdhocSearching] = useState(false)
  const [tab, setTab] = useState<'results' | 'adhoc'>('results')
  const [filterMode, setFilterMode] = useState<'all' | 'relevant' | 'new'>('all')
  const inputRef = useRef<HTMLInputElement>(null)

  // Auto-focus ad-hoc input when switching tabs
  useEffect(() => {
    if (tab === 'adhoc' && inputRef.current) {
      inputRef.current.focus()
    }
  }, [tab])

  const handleAdhocSearch = async () => {
    if (!adhocQuery.trim()) return
    setIsAdhocSearching(true)
    setAdhocSearched(true)
    try {
      const data = await api.discoverSearch(adhocQuery, { max_results: 25 })
      setAdhocResults(data.papers || [])
    } catch {
      setAdhocResults([])
    } finally {
      setIsAdhocSearching(false)
    }
  }

  const togglePaper = (paper: Record<string, any>) => {
    const doi = paper.doi || paper.DOI || ''
    if (!doi) return
    if (selectedPaperDois.includes(doi)) {
      onPaperSelection(selectedPaperDois.filter((d) => d !== doi))
    } else {
      onPaperSelection([...selectedPaperDois, doi])
    }
  }

  const getSelectedPapers = (): Record<string, any>[] => {
    const all = tab === 'results' ? (searchResponse?.results || []) : adhocResults
    return all.filter(r => {
      const doi = (r as any).doi || (r as any).DOI || ''
      return selectedPaperDois.includes(doi)
    })
  }

  // Filter results
  const getFilteredResults = (results: any[]): any[] => {
    if (filterMode === 'relevant') {
      return results.filter(r => (r.relevance_score ?? 0) >= 5)
    }
    if (filterMode === 'new') {
      return results.filter(r => !(r as any).is_known)
    }
    return results
  }

  const selectedCount = selectedPaperDois.length
  const allResults = searchResponse?.results || []
  const scoredCount = allResults.filter(r => r.relevance_score !== undefined && r.relevance_score !== null && r.relevance_score > 0).length

  return (
    <div className="glass-card flex flex-col min-h-0 overflow-hidden h-full">
      {/* Tab bar */}
      <div className="flex border-b border-border flex-shrink-0">
        <button
          onClick={() => setTab('results')}
          className={`flex-1 px-3 py-2 text-[11px] font-medium transition-colors ${
            tab === 'results'
              ? 'text-accent-teal border-b-2 border-accent-teal'
              : 'text-text-muted hover:text-text-secondary'
          }`}
        >
          Results {searchResponse ? `(${searchResponse.dedup_stats.unique})` : ''}
        </button>
        <button
          onClick={() => setTab('adhoc')}
          className={`flex-1 px-3 py-2 text-[11px] font-medium transition-colors ${
            tab === 'adhoc'
              ? 'text-accent-teal border-b-2 border-accent-teal'
              : 'text-text-muted hover:text-text-secondary'
          }`}
        >
          Ad-hoc Search
        </button>
      </div>

      {tab === 'results' ? (
        <>
          {/* Status bar with live updates */}
          {searchResponse && (
            <div className="px-3 py-1.5 border-b border-border flex-shrink-0 space-y-1">
              <div className="flex items-center gap-2 text-[10px]">
                <span className="text-text-muted">
                  Found <span className="font-semibold text-text-primary">{searchResponse.dedup_stats.total_found}</span>
                </span>
                <ArrowRight className="w-2.5 h-2.5 text-text-muted" />
                <span className="text-warning">{searchResponse.dedup_stats.duplicates_removed} dupes</span>
                <ArrowRight className="w-2.5 h-2.5 text-text-muted" />
                <span className="text-success font-semibold">{searchResponse.dedup_stats.unique} new</span>
                {searchResponse.dedup_stats.already_known > 0 && (
                  <span className="text-text-muted">({searchResponse.dedup_stats.already_known} known)</span>
                )}
                <span className="ms-auto" />
                {isScoringBg && (
                  <span className="flex items-center gap-1 text-accent-gold animate-pulse">
                    <Loader2 className="w-2.5 h-2.5 animate-spin" />
                    Scoring...
                  </span>
                )}
                {!isScoringBg && scoredCount > 0 && (
                  <span className="flex items-center gap-1 text-success">
                    <Sparkles className="w-2.5 h-2.5" />
                    {scoredCount} scored
                  </span>
                )}
              </div>

              {/* Filter chips + actions */}
              <div className="flex items-center gap-1.5">
                <Filter className="w-2.5 h-2.5 text-text-muted" />
                {(['all', 'relevant', 'new'] as const).map(mode => (
                  <button
                    key={mode}
                    onClick={() => setFilterMode(mode)}
                    className={`px-1.5 py-0.5 rounded text-[9px] font-medium transition-colors ${
                      filterMode === mode
                        ? 'bg-accent-teal/15 text-accent-teal border border-accent-teal/30'
                        : 'bg-bg-surface text-text-muted border border-border hover:border-text-muted/30'
                    }`}
                  >
                    {mode === 'all' ? 'All' : mode === 'relevant' ? 'Relevant (5+)' : 'New only'}
                  </button>
                ))}

                {selectedCount > 0 && (
                  <div className="ms-auto flex items-center gap-1">
                    <span className="text-[9px] text-accent-teal font-semibold">{selectedCount} selected</span>
                    {onAddToVerification && (
                      <button
                        onClick={() => onAddToVerification(getSelectedPapers())}
                        className="flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[9px] font-medium bg-success/15 text-success border border-success/30 hover:bg-success/25 transition-colors"
                        title="Add selected papers as gap verification evidence"
                      >
                        <ShieldCheck className="w-2.5 h-2.5" />
                        Verify Gaps
                      </button>
                    )}
                    {onAddToPaperList && (
                      <button
                        onClick={() => onAddToPaperList(getSelectedPapers())}
                        className="flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[9px] font-medium bg-accent-teal/15 text-accent-teal border border-accent-teal/30 hover:bg-accent-teal/25 transition-colors"
                        title="Add selected papers to extraction pipeline"
                      >
                        <Library className="w-2.5 h-2.5" />
                        Add to Pipeline
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Results */}
          <div className="flex-1 min-h-0 overflow-y-auto">
            {isSearching && (
              <div className="flex flex-col items-center justify-center py-12 text-text-muted">
                <div className="w-5 h-5 border-2 border-accent-teal/30 border-t-accent-teal rounded-full animate-spin mb-2" />
                <p className="text-[11px]">Searching OpenAlex + Semantic Scholar...</p>
                <p className="text-[9px] mt-1 text-text-muted">Results appear instantly, scores follow</p>
              </div>
            )}
            {!searchResponse && !isSearching && (
              <EmptyState icon="search" text="Use Query Editor to search for papers" />
            )}
            {searchResponse && !isSearching && searchResponse.results.length === 0 && (
              <EmptyState icon="book" text="No results found" />
            )}
            {!isSearching && searchResponse && getFilteredResults(
              [...searchResponse.results].sort((a, b) => {
                if ((a as any).is_known !== (b as any).is_known) {
                  return (a as any).is_known ? 1 : -1
                }
                return (b.relevance_score ?? -1) - (a.relevance_score ?? -1)
              })
            ).map((r, i) => (
              <PaperCard
                key={`${(r as any).doi || (r as any).DOI || i}`}
                result={r}
                isSelected={selectedPaperDois.includes((r as any).doi || (r as any).DOI || '')}
                isKnown={(r as any).is_known ?? false}
                isScoringBg={isScoringBg && (r.relevance_score === undefined || r.relevance_score === null)}
                onToggle={() => togglePaper(r)}
              />
            ))}
          </div>
        </>
      ) : (
        <>
          <div className="px-3 py-2 border-b border-border flex-shrink-0">
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-text-muted" />
                <input
                  ref={inputRef}
                  type="text"
                  placeholder="e.g., your research topic keywords..."
                  value={adhocQuery}
                  onChange={(e) => setAdhocQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleAdhocSearch()}
                  className="w-full pl-7 pr-2 py-1.5 rounded-md bg-bg-surface border border-border text-[11px] text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-teal/50"
                />
              </div>
              <button
                onClick={handleAdhocSearch}
                disabled={isAdhocSearching || !adhocQuery.trim()}
                className="flex items-center gap-1 px-2.5 py-1.5 rounded-md bg-accent-teal text-white text-[10px] font-medium hover:bg-accent-teal/80 disabled:opacity-40"
              >
                {isAdhocSearching ? (
                  <><Loader2 className="w-3 h-3 animate-spin" /> Searching...</>
                ) : 'Search'}
              </button>
            </div>
            <p className="text-[9px] text-text-muted mt-1">
              Searches OpenAlex with governance concept filter. Results not scored for relevance.
            </p>
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto">
            {isAdhocSearching && (
              <div className="flex flex-col items-center justify-center py-12 text-text-muted">
                <div className="w-5 h-5 border-2 border-accent-teal/30 border-t-accent-teal rounded-full animate-spin mb-2" />
                <p className="text-[11px]">Searching OpenAlex...</p>
              </div>
            )}
            {adhocSearched && adhocResults.length === 0 && !isAdhocSearching && (
              <EmptyState icon="book" text="No results found" />
            )}
            {!isAdhocSearching && adhocResults.map((r, i) => (
              <PaperCard
                key={`adhoc-${(r as any).doi || (r as any).DOI || i}`}
                result={r}
                isSelected={selectedPaperDois.includes((r as any).doi || (r as any).DOI || '')}
                isKnown={false}
                isScoringBg={false}
                onToggle={() => togglePaper(r)}
              />
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function EmptyState({ icon, text }: { icon: string; text: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-text-muted">
      {icon === 'search' && <Search className="w-6 h-6 mb-2" />}
      {icon === 'book' && <BookOpen className="w-6 h-6 mb-2" />}
      <p className="text-[11px]">{text}</p>
    </div>
  )
}

/** Normalize paper fields — backend may use DOI/Authors/Year (uppercase) or doi/authors/year */
function norm(r: Record<string, any>) {
  const doi = r.doi || r.DOI || ''
  const authorsRaw = r.authors || r.Authors || ''
  const authors: string[] = Array.isArray(authorsRaw)
    ? authorsRaw
    : typeof authorsRaw === 'string' && authorsRaw
    ? authorsRaw.split(';').map((a: string) => a.trim()).filter(Boolean)
    : []
  const year = r.year || r.Year || ''
  const citations = r.citation_count ?? r.Citation_Count ?? 0
  const isOA = r.is_open_access ?? r.is_oa ?? false
  const abstract = r.abstract || ''
  const title = r.title || ''
  const journal = r.journal || r.Journal || ''
  return { doi, authors, year: String(year), citations: Number(citations), isOA, abstract, title, journal }
}

function PaperCard({
  result: r,
  isSelected,
  isKnown,
  isScoringBg,
  onToggle,
}: {
  result: Record<string, any>
  isSelected: boolean
  isKnown: boolean
  isScoringBg: boolean
  onToggle: () => void
}) {
  const [expanded, setExpanded] = useState(false)
  const n = norm(r)
  const score = r.relevance_score ?? null
  const hasScore = score !== null && score > 0
  const scoreColor =
    !hasScore ? '' :
    score >= 7 ? 'bg-success/20 text-success border-success/30' :
    score >= 5 ? 'bg-accent-gold/20 text-accent-gold border-accent-gold/30' :
    'bg-error/20 text-error border-error/30'

  return (
    <div className={`px-3 py-2 border-b border-border/50 transition-colors ${isKnown ? 'opacity-40' : ''} ${isSelected ? 'bg-accent-teal/5' : 'hover:bg-bg-elevated'}`}>
      <div className="flex items-start gap-2">
        <button onClick={onToggle} className="mt-0.5 flex-shrink-0">
          {isSelected ? <CheckSquare className="w-3.5 h-3.5 text-accent-teal" /> : <Square className="w-3.5 h-3.5 text-text-muted/50" />}
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            {hasScore && (
              <span className={`flex items-center gap-0.5 px-1 py-0.5 rounded text-[9px] font-semibold border ${scoreColor}`}>
                <Star className="w-2.5 h-2.5" />
                {score}/10
              </span>
            )}
            {isScoringBg && !hasScore && (
              <span className="flex items-center gap-0.5 px-1 py-0.5 rounded text-[9px] font-medium border border-accent-gold/20 bg-accent-gold/10 text-accent-gold">
                <Loader2 className="w-2.5 h-2.5 animate-spin" />
              </span>
            )}
            <h4
              className="text-[11px] font-medium text-text-primary leading-snug line-clamp-1 cursor-pointer"
              onClick={() => setExpanded(!expanded)}
            >
              {n.title}
            </h4>
          </div>
          <div className="flex items-center gap-2 mt-0.5 text-[9px] text-text-muted flex-wrap">
            {n.authors.length > 0 && (
              <span className="flex items-center gap-0.5">
                <Users className="w-2.5 h-2.5" />
                {n.authors.slice(0, 2).join(', ')}{n.authors.length > 2 ? ` +${n.authors.length - 2}` : ''}
              </span>
            )}
            {n.year && <span>{n.year}</span>}
            {n.citations > 0 && (
              <span className="flex items-center gap-0.5"><Award className="w-2.5 h-2.5" />{n.citations}</span>
            )}
            {n.isOA && <span className="text-success font-semibold">OA</span>}
            {isKnown && <span className="text-warning font-medium">In library</span>}
            {r.source_gap_id && (
              <span className="font-mono text-accent-teal-light">{r.source_gap_id.replace('GAP_NEW_', 'G')}</span>
            )}
            {r.Extracted_By && r.Extracted_By.includes('Semantic') && (
              <span className="text-[8px] px-1 py-0 rounded bg-purple-500/10 text-purple-400 border border-purple-500/20">S2</span>
            )}
          </div>
          {/* Expanded: relevance reason + abstract + journal */}
          {expanded && (
            <div className="mt-1.5 space-y-1">
              {r.relevance_reason && (
                <p className="text-[10px] text-accent-teal/80 italic">{r.relevance_reason}</p>
              )}
              {n.journal && (
                <p className="text-[10px] text-text-muted"><span className="font-medium">Journal:</span> {n.journal}</p>
              )}
              {n.abstract && (
                <p className="text-[10px] text-text-muted line-clamp-3">{n.abstract}</p>
              )}
            </div>
          )}
        </div>
        {n.doi && (
          <a href={`https://doi.org/${n.doi}`} target="_blank" rel="noopener noreferrer" className="text-accent-teal hover:text-accent-teal-light flex-shrink-0" onClick={(e) => e.stopPropagation()}>
            <ExternalLink className="w-3 h-3" />
          </a>
        )}
      </div>
    </div>
  )
}
