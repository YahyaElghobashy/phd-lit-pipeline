import { useState, useEffect, useCallback } from 'react'
import { CheckSquare, Square, Plus, Trash2, Save, Search, Loader2 } from 'lucide-react'
import { api } from '../../api/client'
import { showToast } from '../shared/Toast'
import { useCachedQueries } from '../../hooks/useData'
import { useQueryClient } from '@tanstack/react-query'
import type { GapQueries } from '../../api/types'

interface QueryEditorProps {
  /** Queries currently loaded (from generate or cache) */
  queries: GapQueries | null
  /** Called when user updates local queries state in parent */
  onQueriesChange: (queries: GapQueries) => void
  /** Trigger search with selected queries + gap statements */
  onSearch: (selectedQueries: GapQueries) => void
  /** Gap statements for relevance scoring */
  gapStatements: Record<string, string>
  isSearching: boolean
}

interface QueryItem {
  text: string
  selected: boolean
}

type EditorState = Record<string, QueryItem[]>

export default function QueryEditor({
  queries,
  onQueriesChange,
  onSearch,
  gapStatements,
  isSearching,
}: QueryEditorProps) {
  const { data: cachedQueries } = useCachedQueries()
  const queryClient = useQueryClient()
  const [editorState, setEditorState] = useState<EditorState>({})
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)

  // Sync queries prop into editor state
  useEffect(() => {
    if (!queries) {
      setEditorState({})
      return
    }
    const state: EditorState = {}
    for (const [gapId, queryList] of Object.entries(queries)) {
      state[gapId] = queryList.map((text) => ({ text, selected: true }))
    }
    setEditorState(state)
    setDirty(false)
  }, [queries])

  const toggleQuery = (gapId: string, idx: number) => {
    setEditorState((prev) => {
      const items = [...(prev[gapId] || [])]
      items[idx] = { ...items[idx], selected: !items[idx].selected }
      return { ...prev, [gapId]: items }
    })
  }

  const updateQueryText = (gapId: string, idx: number, text: string) => {
    setEditorState((prev) => {
      const items = [...(prev[gapId] || [])]
      items[idx] = { ...items[idx], text }
      return { ...prev, [gapId]: items }
    })
    setDirty(true)
  }

  const addQuery = (gapId: string) => {
    setEditorState((prev) => ({
      ...prev,
      [gapId]: [...(prev[gapId] || []), { text: '', selected: true }],
    }))
    setDirty(true)
  }

  const removeQuery = (gapId: string, idx: number) => {
    setEditorState((prev) => {
      const items = (prev[gapId] || []).filter((_, i) => i !== idx)
      if (items.length === 0) {
        const next = { ...prev }
        delete next[gapId]
        return next
      }
      return { ...prev, [gapId]: items }
    })
    setDirty(true)
  }

  const deleteGapQueries = async (gapId: string) => {
    try {
      await api.deleteQueries(gapId)
      setEditorState((prev) => {
        const next = { ...prev }
        delete next[gapId]
        return next
      })
      // Update parent state
      if (queries) {
        const updated = { ...queries }
        delete updated[gapId]
        onQueriesChange(updated)
      }
      queryClient.invalidateQueries({ queryKey: ['cachedQueries'] })
      showToast(`Queries for ${shortId(gapId)} deleted`, 'info')
    } catch {
      showToast('Failed to delete queries', 'info')
    }
  }

  const saveAll = useCallback(async () => {
    setSaving(true)
    try {
      const updated: GapQueries = {}
      for (const [gapId, items] of Object.entries(editorState)) {
        const texts = items.map((i) => i.text).filter((t) => t.trim())
        if (texts.length > 0) {
          await api.updateQueries(gapId, texts)
          updated[gapId] = texts
        }
      }
      onQueriesChange(updated)
      queryClient.invalidateQueries({ queryKey: ['cachedQueries'] })
      setDirty(false)
      showToast('Queries saved', 'success')
    } catch {
      showToast('Failed to save queries', 'info')
    } finally {
      setSaving(false)
    }
  }, [editorState, onQueriesChange, queryClient])

  const handleSearch = () => {
    // Build queries map with only selected queries
    const selected: GapQueries = {}
    let count = 0
    for (const [gapId, items] of Object.entries(editorState)) {
      const texts = items.filter((i) => i.selected && i.text.trim()).map((i) => i.text)
      if (texts.length > 0) {
        selected[gapId] = texts
        count += texts.length
      }
    }
    if (count === 0) {
      showToast('Select at least one query to search', 'info')
      return
    }
    onSearch(selected)
  }

  const totalQueries = Object.values(editorState).flat().length
  const selectedCount = Object.values(editorState).flat().filter((q) => q.selected && q.text.trim()).length
  const gapIds = Object.keys(editorState)

  if (!queries && gapIds.length === 0) {
    return (
      <div className="glass-card flex flex-col items-center justify-center min-h-0 overflow-hidden h-full">
        <div className="flex flex-col items-center py-12 text-text-muted">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" className="w-6 h-6 mb-2">
            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
          </svg>
          <p className="text-[11px]">Generate queries to edit them here</p>
        </div>
      </div>
    )
  }

  return (
    <div className="glass-card flex flex-col min-h-0 overflow-hidden h-full">
      {/* Header */}
      <div className="px-3 py-2 border-b border-border flex-shrink-0 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-xs font-semibold text-text-primary">Queries</h3>
          <span className="text-[10px] text-text-muted">{selectedCount}/{totalQueries} selected</span>
        </div>
        <div className="flex items-center gap-1.5">
          {dirty && (
            <button
              onClick={saveAll}
              disabled={saving}
              className="flex items-center gap-1 px-2 py-1 rounded-md bg-accent-gold/10 border border-accent-gold/20 text-[10px] text-accent-gold font-medium hover:bg-accent-gold/20 disabled:opacity-40"
            >
              {saving ? <Loader2 className="w-2.5 h-2.5 animate-spin" /> : <Save className="w-2.5 h-2.5" />}
              Save
            </button>
          )}
        </div>
      </div>

      {/* Scrollable query list */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {gapIds.map((gapId) => {
          const items = editorState[gapId] || []
          const isCached = !!cachedQueries?.[gapId]
          return (
            <div key={gapId} className="border-b border-border/50">
              {/* Gap header */}
              <div className="px-3 py-1.5 bg-bg-surface/50 flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <span className="text-[10px] font-mono text-accent-teal-light font-medium">{shortId(gapId)}</span>
                  {isCached && (
                    <span className="text-[9px] px-1 py-0.5 rounded bg-success/10 text-success">cached</span>
                  )}
                  <span className="text-[9px] text-text-muted">{items.length} queries</span>
                </div>
                <button
                  onClick={() => deleteGapQueries(gapId)}
                  className="text-text-muted hover:text-error transition-colors p-0.5"
                  title="Delete all queries for this gap"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>

              {/* Query items */}
              {items.map((item, idx) => (
                <div key={idx} className="flex items-center gap-1.5 px-3 py-1">
                  <button onClick={() => toggleQuery(gapId, idx)} className="flex-shrink-0">
                    {item.selected ? (
                      <CheckSquare className="w-3.5 h-3.5 text-accent-teal" />
                    ) : (
                      <Square className="w-3.5 h-3.5 text-text-muted/50" />
                    )}
                  </button>
                  <input
                    type="text"
                    value={item.text}
                    onChange={(e) => updateQueryText(gapId, idx, e.target.value)}
                    className="flex-1 px-1.5 py-1 rounded bg-bg-surface border border-border text-[11px] text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-teal/50 transition-colors"
                    placeholder="Enter search query..."
                  />
                  <button
                    onClick={() => removeQuery(gapId, idx)}
                    className="flex-shrink-0 text-text-muted hover:text-error transition-colors p-0.5"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              ))}

              {/* Add query button */}
              <button
                onClick={() => addQuery(gapId)}
                className="flex items-center gap-1 px-3 py-1.5 text-[10px] text-accent-teal hover:text-accent-teal-light transition-colors"
              >
                <Plus className="w-3 h-3" />
                Add query
              </button>
            </div>
          )
        })}
      </div>

      {/* Footer — Search button */}
      <div className="px-3 py-2.5 border-t border-border flex-shrink-0 flex gap-2">
        <button
          onClick={handleSearch}
          disabled={isSearching || selectedCount === 0}
          className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-accent-teal text-white text-xs font-medium hover:bg-accent-teal/80 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {isSearching ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Search className="w-3.5 h-3.5" />
          )}
          {isSearching ? 'Searching...' : `Search Selected (${selectedCount})`}
        </button>
      </div>
    </div>
  )
}

function shortId(gapId: string): string {
  return gapId.replace('GAP_NEW_', 'G').replace('GAP_', 'G')
}
