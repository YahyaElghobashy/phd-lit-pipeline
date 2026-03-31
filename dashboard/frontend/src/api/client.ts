const BASE = ''  // Vite proxy handles /api -> backend

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

export const api = {
  getOverview: () => fetchJSON<import('./types').Overview>('/api/overview'),
  getPapers: (params?: URLSearchParams) =>
    fetchJSON<import('./types').PaperSummary[]>(`/api/papers${params ? `?${params}` : ''}`),
  getPaper: (id: string) => fetchJSON<import('./types').ExtractionDetail>(`/api/papers/${id}`),
  getExtractions: () => fetchJSON<any[]>('/api/extractions'),
  getGaps: (params?: URLSearchParams) =>
    fetchJSON<import('./types').GapEntry[]>(`/api/gaps${params ? `?${params}` : ''}`),
  getRuns: () => fetchJSON<import('./types').RunSummary[]>('/api/runs'),
  getRun: (id: string) => fetchJSON<import('./types').RunDetail>(`/api/runs/${id}`),
  getActionStatus: () => fetchJSON<import('./types').ActionStatus>('/api/actions/status'),
  runAction: (command: string, flags: Record<string, unknown>) =>
    fetchJSON<{ pid: number; command: string }>('/api/actions/run', {
      method: 'POST',
      body: JSON.stringify({ command, flags }),
    }),
  cancelAction: () => fetchJSON<{ message: string }>('/api/actions/cancel', { method: 'POST' }),
  discoverSearch: (query: string, options?: Record<string, unknown>) =>
    fetchJSON<import('./types').SearchResponse>('/api/discover/search', {
      method: 'POST',
      body: JSON.stringify({ query, ...options }),
    }),

  // ── Discovery Pipeline ─────────────────────────────────────────
  getDiscoveryGaps: () =>
    fetchJSON<import('./types').DiscoveryGap[]>('/api/discover/gaps'),

  generateQueries: (gapIds: string[], force = false) =>
    fetchJSON<{ queries: import('./types').GapQueries; gap_count: number; from_cache: number; newly_generated: number }>('/api/discover/generate-queries', {
      method: 'POST',
      body: JSON.stringify({ gap_ids: gapIds, force }),
    }),

  searchGaps: (queries: import('./types').GapQueries, gapStatements?: Record<string, string>, options?: Record<string, unknown>) =>
    fetchJSON<import('./types').GapSearchResponse>('/api/discover/search-gaps', {
      method: 'POST',
      body: JSON.stringify({ queries, gap_statements: gapStatements ?? {}, ...options }),
    }),

  getScoringStatus: () =>
    fetchJSON<import('./types').ScoringStatus>('/api/discover/scoring-status'),

  runDiscoveryPipeline: (action: string, flags?: Record<string, unknown>) =>
    fetchJSON<{ pid: number; command: string }>('/api/discover/run-pipeline', {
      method: 'POST',
      body: JSON.stringify({ action, ...flags }),
    }),

  getMatrix: () =>
    fetchJSON<import('./types').MatrixData>('/api/discover/matrix'),

  getEvidence: (gapId: string) =>
    fetchJSON<import('./types').EvidenceEntry[]>(`/api/discover/evidence/${gapId}`),

  // ── Query Cache ─────────────────────────────────────────────────────
  getCachedQueries: () =>
    fetchJSON<import('./types').CachedQueries>('/api/discover/cached-queries'),

  updateQueries: (gapId: string, queries: string[]) =>
    fetchJSON<{ gap_id: string; status: string }>(`/api/discover/queries/${gapId}`, {
      method: 'PUT',
      body: JSON.stringify({ queries }),
    }),

  deleteQueries: (gapId: string) =>
    fetchJSON<{ gap_id: string; status: string }>(`/api/discover/queries/${gapId}`, {
      method: 'DELETE',
    }),

  stagePapers: (papers: Record<string, unknown>[], action: 'extract' | 'verify') =>
    fetchJSON<import('./types').StagePapersResponse>('/api/discover/stage-papers', {
      method: 'POST',
      body: JSON.stringify({ papers, action }),
    }),

  // ── Admin ─────────────────────────────────────────────────────
  getAdminConfig: () =>
    fetchJSON<import('./types').AdminConfig>('/api/admin/config'),

  updateAdminConfig: (config: Record<string, unknown>) =>
    fetchJSON<import('./types').AdminConfig>('/api/admin/config', {
      method: 'PUT',
      body: JSON.stringify({ config }),
    }),

  regenerateFiles: () =>
    fetchJSON<import('./types').RegenerateResult>('/api/admin/regenerate', {
      method: 'POST',
    }),

  getFiles: () =>
    fetchJSON<import('./types').PipelineFile[]>('/api/admin/files'),

  deleteFile: (path: string) =>
    fetchJSON<{ status: string; path: string }>('/api/admin/files', {
      method: 'DELETE',
      body: JSON.stringify({ path }),
    }),

  getSheets: () =>
    fetchJSON<import('./types').SheetTab[]>('/api/admin/sheets'),

  rebuildSheets: () =>
    fetchJSON<{ status: string; message: string }>('/api/admin/sheets/rebuild', {
      method: 'POST',
    }),

  getDriveFolders: () =>
    fetchJSON<import('./types').DriveFolder[]>('/api/admin/drive/folders'),

  createDriveFolders: (projectName: string) =>
    fetchJSON<import('./types').CreateFolderResult>('/api/admin/drive/folders', {
      method: 'POST',
      body: JSON.stringify({ project_name: projectName }),
    }),
}
