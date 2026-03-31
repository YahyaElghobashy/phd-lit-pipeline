export interface Overview {
  total_papers: number
  completed: number
  failed: number
  in_progress: number
  total_gaps: number
  by_status: Record<string, number>
  by_theme: Record<string, number>
  by_relevance: Record<string, number>
  gaps_by_coverage: Record<string, number>
  avg_duration_seconds: number
  last_run: string | null
}

export interface PaperSummary {
  paper_id: string
  status: string
  original_filename: string
  started_at: string | null
  completed_at: string | null
  duration_seconds: number | null
  error: string | null
  retry_count: number
  year: number | null
  journal: string
  doi: string
  theme: string
  paper_assignment: string
  relevance_tier: string
  weighted_score: number | string
}

export interface ExtractionDetail {
  paper_id: string
  _sections: string[]
  _section_labels: Record<string, string>
  [key: string]: unknown
}

export interface GapEntry {
  gap_id: string
  gap_type: string
  gap_statement: string
  severity: string | number
  feasibility: string | number
  novelty: string | number
  priority_score: string | number
  coverage_level: string
  covering_paper_ids?: string
  coverage_notes?: string
  paper_assignment: string
  potential_hypothesis?: string
  variables_needed?: string
  methodology_needed?: string
  status: string
  [key: string]: unknown
}

export interface RunSummary {
  run_id: string
  filename: string
  timestamp: string
  started_at: string | null
  finished_at: string | null
  duration_seconds: number | null
  total_duration: number | null
  total_queued: number
  completed: number
  failed: number
  skipped: number
  args: Record<string, unknown>
}

export interface RunDetail extends RunSummary {
  papers: Array<{
    filename: string
    subfolder: string
    paper_id: string | null
    status: string
    failure_stage?: string
    failure_reason?: string
    duration: number | null
    duration_seconds: number | null
    relevance_tier?: string
    theme?: string
  }>
}

export interface ActionStatus {
  is_running: boolean
  pid: number | null
  command: string | null
  started_at: number | null
  elapsed_seconds: number
}

export interface SearchResult {
  title: string
  authors: string[]
  year: number
  journal: string
  doi: string
  citation_count: number
  is_open_access: boolean
  oa_pdf_url: string | null
  abstract: string
  relevance_score?: number
  relevance_reason?: string
}

export interface SearchResponse {
  query: string
  count: number
  papers: SearchResult[]
}

// ── Discovery Pipeline Types ─────────────────────────────────────────

export interface DiscoveryGap {
  gap_id: string
  gap_statement: string
  gap_type: string
  severity: number | string
  pct_remaining: number
  gap_state: 'Open' | 'Under Investigation' | 'Partially Resolved' | 'Resolved'
  coverage_level: string
  paper_assignment: string
}

export interface GapQueries {
  [gap_id: string]: string[]
}

export interface GapSearchResponse {
  results: (SearchResult & { source_gap_id?: string; is_known?: boolean })[]
  dedup_stats: {
    total_found: number
    duplicates_removed: number
    unique: number
    already_known: number
  }
}

export interface MatrixEntry {
  gap_id: string
  pct_remaining: number
  gap_state: string
  papers: Record<string, number>
}

export interface MatrixData {
  gaps: MatrixEntry[]
  summary: {
    open: number
    investigating: number
    partial: number
    resolved: number
  }
  paper_ids: string[]
}

export interface EvidenceEntry {
  gap_id: string
  paper_id: string
  pct_eliminated: number
  pct_remaining_before: number
  pct_remaining_after: number
  aspect_addressed: string
  what_still_remains: string
  assessed_by: string
  assessed_at: string
  source: string
}

// ── Query Cache Types ────────────────────────────────────────────────

export interface CachedQueryEntry {
  queries: string[]
  generated_at: string
}

export type CachedQueries = Record<string, CachedQueryEntry>

// ── Scoring & Staging Types ─────────────────────────────────────────

export interface ScoringStatus {
  is_scoring: boolean
  scored_count: number
  request_id: string
  scores: Record<string, { relevance_score: number; relevance_reason: string }>
}

export interface StagePapersResponse {
  status: string
  action: string
  total_papers: number
  dois_count: number
  staged_file: string
  downloaded: number
  download_failed: number
  downloads: Array<{ paper_id: string; title: string; pdf_path: string; source: string }>
  failures: Array<{ paper_id: string; title: string; reason: string }>
  next_step: string
}

// ── Admin Types ─────────────────────────────────────────────────────

export interface AdminConfig {
  project?: {
    title?: string
    short_title?: string
    researcher_name?: string
  }
  papers?: Array<{ id: string; label: string; focus: string }>
  key_scholars?: Array<{ name: string; key: string; context: string }>
  theories?: string[]
  custom_sections?: Array<{
    id: string
    label: string
    columns?: Array<{ name: string; type?: string; options?: string[] }>
  }>
  research_context?: {
    summary?: string
    critical_note?: string
    databases?: Array<{ name: string; purpose: string }>
  }
  google_sheets?: {
    spreadsheet_id?: string
    auto_spreadsheet_id?: string
  }
  [key: string]: unknown
}

export interface RegenerateResult {
  status: string
  message: string
  project_title?: string
  papers_count?: number
  sections_count?: number
}

export interface PipelineFile {
  path: string
  category: string
  name: string
  size_bytes: number
  modified: string
}

export interface SheetTab {
  title: string
  row_count: number
  col_count: number
  error?: string
}

export interface DriveFolder {
  id: string
  name: string
  created: string
  modified: string
  error?: string
}

export interface CreateFolderResult {
  status: string
  project_name?: string
  folders_created?: number
  folders?: Array<{ name: string; id: string; type: string }>
  message?: string
}
