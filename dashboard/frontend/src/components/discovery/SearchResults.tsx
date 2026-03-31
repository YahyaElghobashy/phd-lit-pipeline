import { useState } from 'react'
import { Search, ExternalLink, Users, Award, BookOpen, ArrowRight, CheckSquare, Square, Star } from 'lucide-react'
import { api } from '../../api/client'
import { showToast } from '../shared/Toast'
import type { SearchResult, GapQueries, GapSearchResponse } from '../../api/types'

interface SearchResultsProps {
  searchResponse: GapSearchResponse | null
  selectedPaperDois: string[]
  onPaperSelection: (dois: string[]) => void
  isSearching: boolean
}

export default function SearchResults({
  searchResponse,
  selectedPaperDois,
  onPaperSelection,
  isSearching,
}: SearchResultsProps) {
  const [adhocQuery, setAdhocQuery] = useState('')
  const [adhocResults, setAdhocResults] = useState<SearchResult[]>([])
  const [adhocSearched, setAdhocSearched] = useState(false)
  const [isAdhocSearching, setIsAdhocSearching] = useState(false)
  const [tab, setTab] = useState<'results' | 'adhoc'>('results')

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
          {/* Dedup stats */}
          {searchResponse && (
            <div className="px-3 py-1.5 border-b border-border flex-shrink-0 flex items-center gap-2 text-[10px]">
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
            </div>
          )}

          {/* Results */}
          <div className="flex-1 min-h-0 overflow-y-auto">
            {isSearching && (
              <div className="flex flex-col items-center justify-center py-12 text-text-muted">
                <div className="w-5 h-5 border-2 border-accent-teal/30 border-t-accent-teal rounded-full animate-spin mb-2" />
                <p className="text-[11px]">Searching OpenAlex + AI relevance scoring...</p>
              </div>
            )}
            {!searchResponse && !isSearching && (
              <EmptyState icon="search" text="Use Query Editor to search for papers" />
            )}
            {searchResponse && !isSearching && searchResponse.results.length === 0 && (
              <EmptyState icon="book" text="No results found" />
            )}
            {!isSearching && searchResponse?.results
              .sort((a, b) => {
                // Sort: relevance score desc, then is_known last
                if ((a as any).is_known !== (b as any).is_known) {
                  return (a as any).is_known ? 1 : -1
                }
                return (b.relevance_score ?? 0) - (a.relevance_score ?? 0)
              })
              .map((r, i) => (
              <PaperCard
                key={`${r.doi || i}`}
                result={r}
                isSelected={selectedPaperDois.includes(r.doi || r.DOI || '')}
                isKnown={(r as any).is_known ?? false}
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
                  type="text"
                  placeholder="e.g., board gender diversity corporate governance..."
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
                {isAdhocSearching ? 'Searching...' : 'Search'}
              </button>
            </div>
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto">
            {adhocSearched && adhocResults.length === 0 && !isAdhocSearching && (
              <EmptyState icon="book" text="No results found" />
            )}
            {adhocResults.map((r, i) => (
              <PaperCard
                key={`adhoc-${r.doi || i}`}
                result={r}
                isSelected={selectedPaperDois.includes(r.doi || r.DOI || '')}
                isKnown={false}
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
      {icon === 'sparkles' && <SparklesIcon />}
      {icon === 'search' && <Search className="w-6 h-6 mb-2" />}
      {icon === 'book' && <BookOpen className="w-6 h-6 mb-2" />}
      <p className="text-[11px]">{text}</p>
    </div>
  )
}

function SparklesIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" className="w-6 h-6 mb-2">
      <path d="M12 3l1.912 5.813a2 2 0 0 0 1.275 1.275L21 12l-5.813 1.912a2 2 0 0 0-1.275 1.275L12 21l-1.912-5.813a2 2 0 0 0-1.275-1.275L3 12l5.813-1.912a2 2 0 0 0 1.275-1.275L12 3z" />
    </svg>
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
  return { doi, authors, year: String(year), citations: Number(citations), isOA, abstract, title }
}

function PaperCard({
  result: r,
  isSelected,
  isKnown,
  onToggle,
}: {
  result: Record<string, any>
  isSelected: boolean
  isKnown: boolean
  onToggle: () => void
}) {
  const [expanded, setExpanded] = useState(false)
  const n = norm(r)
  const score = r.relevance_score ?? null
  const scoreColor =
    score === null ? '' :
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
            {score !== null && (
              <span className={`flex items-center gap-0.5 px-1 py-0.5 rounded text-[9px] font-semibold border ${scoreColor}`}>
                <Star className="w-2.5 h-2.5" />
                {score}/10
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
            {isKnown && <span className="text-warning font-medium">Already in library</span>}
            {r.source_gap_id && (
              <span className="font-mono text-accent-teal-light">{r.source_gap_id.replace('GAP_NEW_', 'G')}</span>
            )}
          </div>
          {/* Expanded: relevance reason + abstract */}
          {expanded && (
            <div className="mt-1.5 space-y-1">
              {r.relevance_reason && (
                <p className="text-[10px] text-accent-teal/80 italic">{r.relevance_reason}</p>
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
