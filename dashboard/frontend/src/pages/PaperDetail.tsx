import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, ExternalLink, ChevronDown, ChevronRight } from 'lucide-react'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import { RelevanceBadge } from '../components/shared/Badge'
import { usePaper } from '../hooks/useData'

export default function PaperDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data, isLoading } = usePaper(id || '')
  const [openSection, setOpenSection] = useState<string>('1_IDENTIFICATION')

  if (isLoading || !data) return <LoadingSpinner />

  const paperId = data.paper_id as string
  const narrativeAssessment = data.narrative_assessment as string | undefined
  const ident = (data['1_IDENTIFICATION'] as Record<string, string>) || {}
  const rel = (data['9_RELEVANCE'] as Record<string, string>) || {}
  const sections = (data._sections as string[]) || []
  const labels = (data._section_labels as Record<string, string>) || {}

  return (
    <div>
      {/* Back button */}
      <button onClick={() => navigate('/papers')} className="flex items-center gap-1.5 text-sm text-text-muted hover:text-text-primary mb-4 transition-colors">
        <ArrowLeft className="w-4 h-4" /> Back to Papers
      </button>

      {/* Header Card */}
      <div className="glass-card p-6 mb-6">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <h2 className="text-lg font-semibold text-accent-teal-light font-mono">{paperId}</h2>
            <p className="text-sm text-text-secondary mt-2 leading-relaxed max-w-3xl">
              {ident.Full_Citation_APA7 || ''}
            </p>
            <div className="flex items-center gap-4 mt-3">
              {ident.Year && <span className="text-xs text-text-muted">Year: {ident.Year}</span>}
              {ident.Journal && <span className="text-xs text-text-muted">Journal: {ident.Journal}</span>}
              {ident.DOI && (
                <a href={`https://doi.org/${ident.DOI}`} target="_blank" rel="noopener noreferrer"
                   className="flex items-center gap-1 text-xs text-accent-teal hover:text-accent-teal-light">
                  DOI <ExternalLink className="w-3 h-3" />
                </a>
              )}
            </div>
          </div>
          <div className="ml-4">
            <RelevanceBadge tier={rel.Relevance_Tier || ''} />
            {rel.Weighted_Score && (
              <p className="text-xs text-text-muted mt-1 text-center">Score: {rel.Weighted_Score}</p>
            )}
          </div>
        </div>
      </div>

      {/* Narrative Assessment */}
      {narrativeAssessment && (
        <div className="glass-card p-5 mb-6 border-l-2 border-accent-gold">
          <h3 className="text-xs font-medium text-accent-gold uppercase tracking-wider mb-2">Narrative Assessment</h3>
          <p className="text-sm text-text-secondary leading-relaxed italic">{narrativeAssessment}</p>
        </div>
      )}

      {/* 12 Sections Accordion */}
      <div className="space-y-2">
        {sections.map((sectionKey: string) => {
          const sectionData = data[sectionKey] as Record<string, unknown> | undefined
          if (!sectionData || typeof sectionData !== 'object') return null
          const isOpen = openSection === sectionKey
          const label = labels[sectionKey] || sectionKey

          return (
            <div key={sectionKey} className="glass-card overflow-hidden">
              <button
                onClick={() => setOpenSection(isOpen ? '' : sectionKey)}
                className="w-full flex items-center justify-between px-5 py-3.5 text-left hover:bg-bg-elevated transition-colors"
              >
                <span className="text-sm font-medium">
                  <span className="text-text-muted mr-2">{sectionKey.split('_')[0]}.</span>
                  {label}
                </span>
                {isOpen ? <ChevronDown className="w-4 h-4 text-text-muted" /> : <ChevronRight className="w-4 h-4 text-text-muted" />}
              </button>
              {isOpen && (
                <div className="px-5 pb-4 border-t border-border">
                  <div className="grid gap-3 mt-3">
                    {Object.entries(sectionData)
                      .filter(([k]) => k !== 'PAPER_ID')
                      .map(([key, value]) => (
                        <div key={key} className="grid grid-cols-[200px_1fr] gap-3">
                          <span className="text-xs text-text-muted font-mono">{key}</span>
                          <span className="text-sm text-text-secondary break-words">{String(value || '—')}</span>
                        </div>
                      ))}
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
