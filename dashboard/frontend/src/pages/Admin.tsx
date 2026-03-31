import { useState, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Settings, Save, RefreshCw, Plus, Trash2, FileText,
  FolderPlus, Database, Columns3, HardDrive, X
} from 'lucide-react'
import Header from '../components/layout/Header'
import { api } from '../api/client'
import { showToast } from '../components/shared/Toast'
import type {
  AdminConfig, PipelineFile, SheetTab, DriveFolder
} from '../api/types'

type TabId = 'config' | 'schema' | 'sheets' | 'files' | 'drive'

const tabs: { id: TabId; label: string; icon: typeof Settings }[] = [
  { id: 'config', label: 'Config', icon: Settings },
  { id: 'schema', label: 'Schema', icon: Columns3 },
  { id: 'sheets', label: 'Sheets', icon: Database },
  { id: 'files', label: 'Files', icon: FileText },
  { id: 'drive', label: 'Drive', icon: HardDrive },
]

export default function Admin() {
  const [activeTab, setActiveTab] = useState<TabId>('config')

  return (
    <div className="flex flex-col h-[calc(100vh-40px)] overflow-hidden">
      <div className="flex-shrink-0">
        <Header
          title="Admin Console"
          subtitle="Configuration, schema, sheets, files & drive management"
        />
      </div>

      {/* Tab bar */}
      <div className="flex items-center gap-1 mb-4 flex-shrink-0">
        {tabs.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium transition-colors ${
              activeTab === id
                ? 'bg-accent-teal/15 text-accent-teal border border-accent-teal/30'
                : 'text-text-muted hover:text-text-primary hover:bg-bg-elevated border border-transparent'
            }`}
          >
            <Icon className="w-3.5 h-3.5" />
            {label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 min-h-0 overflow-y-auto pb-4">
        {activeTab === 'config' && <ConfigTab />}
        {activeTab === 'schema' && <SchemaTab />}
        {activeTab === 'sheets' && <SheetsTab />}
        {activeTab === 'files' && <FilesTab />}
        {activeTab === 'drive' && <DriveTab />}
      </div>
    </div>
  )
}

// ── Tab 1: Config ──────────────────────────────────────────────────────

function ConfigTab() {
  const queryClient = useQueryClient()
  const { data: config, isLoading } = useQuery({
    queryKey: ['adminConfig'],
    queryFn: api.getAdminConfig,
  })
  const [saving, setSaving] = useState(false)
  const [regenerating, setRegenerating] = useState(false)

  // Local editable state
  const [title, setTitle] = useState('')
  const [researcherName, setResearcherName] = useState('')
  const [papers, setPapers] = useState<Array<{ id: string; label: string; focus: string }>>([])
  const [scholars, setScholars] = useState<Array<{ name: string; key: string; context: string }>>([])
  const [theories, setTheories] = useState<string[]>([])
  const [initialized, setInitialized] = useState(false)

  // Initialize from fetched config
  if (config && !initialized && !('error' in config)) {
    setTitle(config.project?.title ?? '')
    setResearcherName(config.project?.researcher_name ?? '')
    setPapers(config.papers ?? [])
    setScholars(config.key_scholars ?? [])
    setTheories(config.theories ?? [])
    setInitialized(true)
  }

  const handleSave = useCallback(async () => {
    setSaving(true)
    try {
      await api.updateAdminConfig({
        project: {
          title,
          researcher_name: researcherName,
          short_title: config?.project?.short_title ?? '',
        },
        papers,
        key_scholars: scholars,
        theories,
      })
      queryClient.invalidateQueries({ queryKey: ['adminConfig'] })
      showToast('Configuration saved', 'success')
    } catch (err) {
      showToast(`Save failed: ${err instanceof Error ? err.message : 'Unknown error'}`, 'info')
    } finally {
      setSaving(false)
    }
  }, [title, researcherName, papers, scholars, theories, config, queryClient])

  const handleRegenerate = useCallback(async () => {
    setRegenerating(true)
    try {
      const result = await api.regenerateFiles()
      if (result.status === 'ok') {
        showToast(`Regenerated: ${result.papers_count} papers, ${result.sections_count} sections`, 'success')
      } else {
        showToast(`Regenerate: ${result.message}`, 'info')
      }
    } catch (err) {
      showToast(`Regenerate failed: ${err instanceof Error ? err.message : 'Unknown error'}`, 'info')
    } finally {
      setRegenerating(false)
    }
  }, [])

  if (isLoading) return <LoadingState />

  return (
    <div className="space-y-4">
      {/* Project info */}
      <div className="glass-card p-4">
        <p className="text-[10px] uppercase tracking-wider text-text-muted mb-3">Project</p>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-[10px] text-text-muted block mb-1">Title</label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full px-2.5 py-1.5 rounded-lg bg-bg-elevated border border-border text-[11px] text-text-primary focus:outline-none focus:border-accent-teal/50"
            />
          </div>
          <div>
            <label className="text-[10px] text-text-muted block mb-1">Researcher Name</label>
            <input
              value={researcherName}
              onChange={(e) => setResearcherName(e.target.value)}
              className="w-full px-2.5 py-1.5 rounded-lg bg-bg-elevated border border-border text-[11px] text-text-primary focus:outline-none focus:border-accent-teal/50"
            />
          </div>
        </div>
      </div>

      {/* Papers */}
      <div className="glass-card p-4">
        <div className="flex items-center justify-between mb-3">
          <p className="text-[10px] uppercase tracking-wider text-text-muted">Papers ({papers.length})</p>
          <button
            onClick={() => setPapers([...papers, { id: '', label: '', focus: '' }])}
            className="flex items-center gap-1 text-[10px] text-accent-teal hover:text-accent-teal-light transition-colors"
          >
            <Plus className="w-3 h-3" /> Add
          </button>
        </div>
        <div className="space-y-2 max-h-[240px] overflow-y-auto">
          {papers.map((p, i) => (
            <div key={i} className="flex items-start gap-2 p-2 rounded-lg bg-bg-elevated/50">
              <div className="flex-1 grid grid-cols-3 gap-2">
                <input
                  value={p.id}
                  onChange={(e) => {
                    const next = [...papers]
                    next[i] = { ...next[i], id: e.target.value }
                    setPapers(next)
                  }}
                  placeholder="ID"
                  className="px-2 py-1 rounded bg-bg-primary border border-border text-[11px] text-text-primary focus:outline-none focus:border-accent-teal/50"
                />
                <input
                  value={p.label}
                  onChange={(e) => {
                    const next = [...papers]
                    next[i] = { ...next[i], label: e.target.value }
                    setPapers(next)
                  }}
                  placeholder="Label"
                  className="px-2 py-1 rounded bg-bg-primary border border-border text-[11px] text-text-primary focus:outline-none focus:border-accent-teal/50"
                />
                <input
                  value={p.focus}
                  onChange={(e) => {
                    const next = [...papers]
                    next[i] = { ...next[i], focus: e.target.value }
                    setPapers(next)
                  }}
                  placeholder="Focus"
                  className="px-2 py-1 rounded bg-bg-primary border border-border text-[11px] text-text-primary focus:outline-none focus:border-accent-teal/50"
                />
              </div>
              <button
                onClick={() => setPapers(papers.filter((_, j) => j !== i))}
                className="text-text-muted hover:text-error transition-colors mt-1"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          ))}
          {papers.length === 0 && (
            <p className="text-[11px] text-text-muted italic py-2">No papers configured</p>
          )}
        </div>
      </div>

      {/* Scholars */}
      <div className="glass-card p-4">
        <div className="flex items-center justify-between mb-3">
          <p className="text-[10px] uppercase tracking-wider text-text-muted">Key Scholars ({scholars.length})</p>
          <button
            onClick={() => setScholars([...scholars, { name: '', key: '', context: '' }])}
            className="flex items-center gap-1 text-[10px] text-accent-teal hover:text-accent-teal-light transition-colors"
          >
            <Plus className="w-3 h-3" /> Add
          </button>
        </div>
        <div className="space-y-2 max-h-[200px] overflow-y-auto">
          {scholars.map((s, i) => (
            <div key={i} className="flex items-start gap-2 p-2 rounded-lg bg-bg-elevated/50">
              <div className="flex-1 grid grid-cols-3 gap-2">
                <input
                  value={s.name}
                  onChange={(e) => {
                    const next = [...scholars]
                    next[i] = { ...next[i], name: e.target.value }
                    setScholars(next)
                  }}
                  placeholder="Name"
                  className="px-2 py-1 rounded bg-bg-primary border border-border text-[11px] text-text-primary focus:outline-none focus:border-accent-teal/50"
                />
                <input
                  value={s.key}
                  onChange={(e) => {
                    const next = [...scholars]
                    next[i] = { ...next[i], key: e.target.value }
                    setScholars(next)
                  }}
                  placeholder="Key"
                  className="px-2 py-1 rounded bg-bg-primary border border-border text-[11px] text-text-primary focus:outline-none focus:border-accent-teal/50"
                />
                <input
                  value={s.context}
                  onChange={(e) => {
                    const next = [...scholars]
                    next[i] = { ...next[i], context: e.target.value }
                    setScholars(next)
                  }}
                  placeholder="Context"
                  className="px-2 py-1 rounded bg-bg-primary border border-border text-[11px] text-text-primary focus:outline-none focus:border-accent-teal/50"
                />
              </div>
              <button
                onClick={() => setScholars(scholars.filter((_, j) => j !== i))}
                className="text-text-muted hover:text-error transition-colors mt-1"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          ))}
          {scholars.length === 0 && (
            <p className="text-[11px] text-text-muted italic py-2">No scholars configured</p>
          )}
        </div>
      </div>

      {/* Theories */}
      <div className="glass-card p-4">
        <div className="flex items-center justify-between mb-3">
          <p className="text-[10px] uppercase tracking-wider text-text-muted">Theories ({theories.length})</p>
          <button
            onClick={() => setTheories([...theories, ''])}
            className="flex items-center gap-1 text-[10px] text-accent-teal hover:text-accent-teal-light transition-colors"
          >
            <Plus className="w-3 h-3" /> Add
          </button>
        </div>
        <div className="flex flex-wrap gap-2">
          {theories.map((t, i) => (
            <div key={i} className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-bg-elevated border border-border">
              <input
                value={t}
                onChange={(e) => {
                  const next = [...theories]
                  next[i] = e.target.value
                  setTheories(next)
                }}
                className="bg-transparent text-[11px] text-text-primary focus:outline-none w-32"
                placeholder="Theory name"
              />
              <button
                onClick={() => setTheories(theories.filter((_, j) => j !== i))}
                className="text-text-muted hover:text-error transition-colors"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          ))}
          {theories.length === 0 && (
            <p className="text-[11px] text-text-muted italic">No theories configured</p>
          )}
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex items-center gap-3">
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-accent-teal text-white text-[11px] font-medium hover:bg-accent-teal/90 transition-colors disabled:opacity-50"
        >
          <Save className="w-3.5 h-3.5" />
          {saving ? 'Saving...' : 'Save Config'}
        </button>
        <button
          onClick={handleRegenerate}
          disabled={regenerating}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-accent-gold/20 text-accent-gold text-[11px] font-medium hover:bg-accent-gold/30 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${regenerating ? 'animate-spin' : ''}`} />
          {regenerating ? 'Regenerating...' : 'Regenerate Files'}
        </button>
      </div>
    </div>
  )
}

// ── Tab 2: Schema ──────────────────────────────────────────────────────

function SchemaTab() {
  const queryClient = useQueryClient()
  const { data: config, isLoading } = useQuery({
    queryKey: ['adminConfig'],
    queryFn: api.getAdminConfig,
  })
  const [sections, setSections] = useState<AdminConfig['custom_sections']>([])
  const [initialized, setInitialized] = useState(false)
  const [saving, setSaving] = useState(false)

  if (config && !initialized && !('error' in config)) {
    setSections(config.custom_sections ?? [])
    setInitialized(true)
  }

  const handleSave = useCallback(async () => {
    setSaving(true)
    try {
      await api.updateAdminConfig({ custom_sections: sections })
      queryClient.invalidateQueries({ queryKey: ['adminConfig'] })
      showToast('Schema saved', 'success')
    } catch (err) {
      showToast(`Save failed: ${err instanceof Error ? err.message : 'Unknown error'}`, 'info')
    } finally {
      setSaving(false)
    }
  }, [sections, queryClient])

  const addSection = () => {
    setSections([...(sections ?? []), { id: '', label: '', columns: [] }])
  }

  const removeSection = (index: number) => {
    setSections((sections ?? []).filter((_, i) => i !== index))
  }

  const updateSection = (index: number, field: string, value: string) => {
    const next = [...(sections ?? [])]
    next[index] = { ...next[index], [field]: value }
    setSections(next)
  }

  const addColumn = (sectionIndex: number) => {
    const next = [...(sections ?? [])]
    const cols = [...(next[sectionIndex].columns ?? []), { name: '', type: 'text' }]
    next[sectionIndex] = { ...next[sectionIndex], columns: cols }
    setSections(next)
  }

  const removeColumn = (sectionIndex: number, colIndex: number) => {
    const next = [...(sections ?? [])]
    const cols = (next[sectionIndex].columns ?? []).filter((_, i) => i !== colIndex)
    next[sectionIndex] = { ...next[sectionIndex], columns: cols }
    setSections(next)
  }

  if (isLoading) return <LoadingState />

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-[10px] uppercase tracking-wider text-text-muted">
          Custom Sections ({(sections ?? []).length})
        </p>
        <button
          onClick={addSection}
          className="flex items-center gap-1 text-[10px] text-accent-teal hover:text-accent-teal-light transition-colors"
        >
          <Plus className="w-3 h-3" /> Add Section
        </button>
      </div>

      {(sections ?? []).map((section, si) => (
        <div key={si} className="glass-card p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3">
              <input
                value={section.id}
                onChange={(e) => updateSection(si, 'id', e.target.value)}
                placeholder="Section ID"
                className="px-2 py-1 rounded bg-bg-elevated border border-border text-[11px] text-text-primary font-mono focus:outline-none focus:border-accent-teal/50 w-32"
              />
              <input
                value={section.label}
                onChange={(e) => updateSection(si, 'label', e.target.value)}
                placeholder="Section Label"
                className="px-2 py-1 rounded bg-bg-elevated border border-border text-[11px] text-text-primary focus:outline-none focus:border-accent-teal/50 w-48"
              />
            </div>
            <button
              onClick={() => removeSection(si)}
              className="text-text-muted hover:text-error transition-colors"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <p className="text-[10px] text-text-muted">Columns ({(section.columns ?? []).length})</p>
              <button
                onClick={() => addColumn(si)}
                className="text-[10px] text-accent-teal hover:text-accent-teal-light transition-colors"
              >
                + Column
              </button>
            </div>
            {(section.columns ?? []).map((col, ci) => (
              <div key={ci} className="flex items-center gap-2">
                <input
                  value={col.name}
                  onChange={(e) => {
                    const next = [...(sections ?? [])]
                    const cols = [...(next[si].columns ?? [])]
                    cols[ci] = { ...cols[ci], name: e.target.value }
                    next[si] = { ...next[si], columns: cols }
                    setSections(next)
                  }}
                  placeholder="Column name"
                  className="flex-1 px-2 py-1 rounded bg-bg-primary border border-border text-[11px] text-text-primary focus:outline-none focus:border-accent-teal/50"
                />
                <select
                  value={col.type ?? 'text'}
                  onChange={(e) => {
                    const next = [...(sections ?? [])]
                    const cols = [...(next[si].columns ?? [])]
                    cols[ci] = { ...cols[ci], type: e.target.value }
                    next[si] = { ...next[si], columns: cols }
                    setSections(next)
                  }}
                  className="px-2 py-1 rounded bg-bg-primary border border-border text-[11px] text-text-primary focus:outline-none w-24"
                >
                  <option value="text">Text</option>
                  <option value="number">Number</option>
                  <option value="select">Select</option>
                  <option value="boolean">Boolean</option>
                </select>
                <button
                  onClick={() => removeColumn(si, ci)}
                  className="text-text-muted hover:text-error transition-colors"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            ))}
          </div>
        </div>
      ))}

      {(sections ?? []).length === 0 && (
        <div className="glass-card p-6 text-center">
          <p className="text-[11px] text-text-muted">No custom sections defined</p>
        </div>
      )}

      <button
        onClick={handleSave}
        disabled={saving}
        className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-accent-teal text-white text-[11px] font-medium hover:bg-accent-teal/90 transition-colors disabled:opacity-50"
      >
        <Save className="w-3.5 h-3.5" />
        {saving ? 'Saving...' : 'Save Schema'}
      </button>
    </div>
  )
}

// ── Tab 3: Sheets ──────────────────────────────────────────────────────

function SheetsTab() {
  const { data: sheets, isLoading, refetch } = useQuery({
    queryKey: ['adminSheets'],
    queryFn: api.getSheets,
  })
  const [rebuilding, setRebuilding] = useState(false)

  const handleRebuild = useCallback(async () => {
    setRebuilding(true)
    showToast('Rebuilding sheet structure...', 'info')
    try {
      const result = await api.rebuildSheets()
      showToast(result.message || 'Sheets rebuilt', 'success')
      refetch()
    } catch (err) {
      showToast(`Rebuild failed: ${err instanceof Error ? err.message : 'Unknown error'}`, 'info')
    } finally {
      setRebuilding(false)
    }
  }, [refetch])

  if (isLoading) return <LoadingState />

  const hasError = sheets && sheets.length > 0 && 'error' in sheets[0]

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-[10px] uppercase tracking-wider text-text-muted">
          Google Sheets Tabs ({hasError ? '?' : sheets?.length ?? 0})
        </p>
        <button
          onClick={handleRebuild}
          disabled={rebuilding}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-accent-gold/20 text-accent-gold text-[10px] font-medium hover:bg-accent-gold/30 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3 h-3 ${rebuilding ? 'animate-spin' : ''}`} />
          {rebuilding ? 'Rebuilding...' : 'Rebuild'}
        </button>
      </div>

      {hasError ? (
        <div className="glass-card p-4">
          <p className="text-[11px] text-error">{(sheets![0] as SheetTab).error}</p>
        </div>
      ) : (
        <div className="glass-card overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left text-[10px] text-text-muted uppercase tracking-wider px-4 py-2.5">Tab Name</th>
                <th className="text-right text-[10px] text-text-muted uppercase tracking-wider px-4 py-2.5">Rows</th>
                <th className="text-right text-[10px] text-text-muted uppercase tracking-wider px-4 py-2.5">Columns</th>
              </tr>
            </thead>
            <tbody>
              {(sheets ?? []).map((tab, i) => (
                <tr key={i} className="border-b border-border/50 hover:bg-bg-elevated/30 transition-colors">
                  <td className="px-4 py-2 text-[11px] text-text-primary font-medium">{tab.title}</td>
                  <td className="px-4 py-2 text-[11px] text-text-secondary text-right font-mono">{tab.row_count}</td>
                  <td className="px-4 py-2 text-[11px] text-text-secondary text-right font-mono">{tab.col_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ── Tab 4: Files ───────────────────────────────────────────────────────

function FilesTab() {
  const { data: files, isLoading, refetch } = useQuery({
    queryKey: ['adminFiles'],
    queryFn: api.getFiles,
  })
  const [deleting, setDeleting] = useState<string | null>(null)

  const handleDelete = useCallback(async (path: string) => {
    if (!confirm(`Delete ${path}?`)) return
    setDeleting(path)
    try {
      await api.deleteFile(path)
      showToast(`Deleted: ${path}`, 'success')
      refetch()
    } catch (err) {
      showToast(`Delete failed: ${err instanceof Error ? err.message : 'Unknown error'}`, 'info')
    } finally {
      setDeleting(null)
    }
  }, [refetch])

  if (isLoading) return <LoadingState />

  // Group by category
  const grouped: Record<string, PipelineFile[]> = {}
  for (const file of files ?? []) {
    if (!grouped[file.category]) grouped[file.category] = []
    grouped[file.category].push(file)
  }

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  return (
    <div className="space-y-4">
      <p className="text-[10px] uppercase tracking-wider text-text-muted">
        Local Files ({(files ?? []).length})
      </p>

      {Object.keys(grouped).length === 0 && (
        <div className="glass-card p-6 text-center">
          <p className="text-[11px] text-text-muted">No local files found</p>
        </div>
      )}

      {Object.entries(grouped).map(([category, categoryFiles]) => (
        <div key={category} className="glass-card p-4">
          <p className="text-[10px] uppercase tracking-wider text-accent-teal mb-3">
            {category} ({categoryFiles.length})
          </p>
          <div className="space-y-1">
            {categoryFiles.map((file, i) => (
              <div
                key={i}
                className="flex items-center justify-between px-3 py-1.5 rounded-lg hover:bg-bg-elevated/50 transition-colors group"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <FileText className="w-3.5 h-3.5 text-text-muted shrink-0" />
                  <span className="text-[11px] text-text-primary truncate">{file.name}</span>
                  <span className="text-[10px] text-text-muted font-mono shrink-0">{formatSize(file.size_bytes)}</span>
                </div>
                <button
                  onClick={() => handleDelete(file.path)}
                  disabled={deleting === file.path}
                  className="opacity-0 group-hover:opacity-100 text-text-muted hover:text-error transition-all"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Tab 5: Drive ───────────────────────────────────────────────────────

function DriveTab() {
  const { data: folders, isLoading, refetch } = useQuery({
    queryKey: ['adminDriveFolders'],
    queryFn: api.getDriveFolders,
  })
  const [creating, setCreating] = useState(false)
  const [projectName, setProjectName] = useState('')

  const handleCreate = useCallback(async () => {
    if (!projectName.trim()) {
      showToast('Enter a project name', 'info')
      return
    }
    setCreating(true)
    try {
      const result = await api.createDriveFolders(projectName.trim())
      if (result.status === 'ok') {
        showToast(`Created ${result.folders_created} folders for "${result.project_name}"`, 'success')
        setProjectName('')
        refetch()
      } else {
        showToast(`Error: ${result.message}`, 'info')
      }
    } catch (err) {
      showToast(`Create failed: ${err instanceof Error ? err.message : 'Unknown error'}`, 'info')
    } finally {
      setCreating(false)
    }
  }, [projectName, refetch])

  if (isLoading) return <LoadingState />

  const hasError = folders && folders.length > 0 && 'error' in folders[0]

  return (
    <div className="space-y-4">
      {/* Create folder */}
      <div className="glass-card p-4">
        <p className="text-[10px] uppercase tracking-wider text-text-muted mb-3">Create Folder Structure</p>
        <div className="flex items-center gap-2">
          <input
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            placeholder="Project name"
            className="flex-1 px-2.5 py-1.5 rounded-lg bg-bg-elevated border border-border text-[11px] text-text-primary focus:outline-none focus:border-accent-teal/50"
            onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
          />
          <button
            onClick={handleCreate}
            disabled={creating}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-accent-teal text-white text-[10px] font-medium hover:bg-accent-teal/90 transition-colors disabled:opacity-50"
          >
            <FolderPlus className="w-3 h-3" />
            {creating ? 'Creating...' : 'Create'}
          </button>
        </div>
      </div>

      {/* Folder list */}
      <div className="glass-card p-4">
        <p className="text-[10px] uppercase tracking-wider text-text-muted mb-3">
          Drive Folders ({hasError ? '?' : (folders ?? []).length})
        </p>

        {hasError ? (
          <p className="text-[11px] text-error">{(folders![0] as DriveFolder).error}</p>
        ) : (folders ?? []).length === 0 ? (
          <p className="text-[11px] text-text-muted italic">No folders found</p>
        ) : (
          <div className="space-y-1">
            {(folders ?? []).map((folder, i) => (
              <div
                key={i}
                className="flex items-center justify-between px-3 py-2 rounded-lg hover:bg-bg-elevated/50 transition-colors"
              >
                <div className="flex items-center gap-2">
                  <HardDrive className="w-3.5 h-3.5 text-accent-gold" />
                  <span className="text-[11px] text-text-primary">{folder.name}</span>
                </div>
                <span className="text-[10px] text-text-muted font-mono">
                  {folder.modified ? new Date(folder.modified).toLocaleDateString() : ''}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Shared ──────────────────────────────────────────────────────────────

function LoadingState() {
  return (
    <div className="flex items-center justify-center py-12">
      <RefreshCw className="w-5 h-5 text-text-muted animate-spin" />
    </div>
  )
}
