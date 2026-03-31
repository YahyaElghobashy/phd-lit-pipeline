import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'
import { api } from '../api/client'
import { showToast } from '../components/shared/Toast'

/**
 * Smart refresh strategy:
 *
 * 1. ACTION STATUS — polls every 3s (lightweight, 200 bytes). Drives the
 *    "Pipeline Running" indicator + sidebar status dot.
 *
 * 2. OVERVIEW (Dashboard) — polls every 10s when pipeline is running (stats
 *    change as papers complete), every 60s when idle (data rarely changes).
 *
 * 3. PAPERS / GAPS / RUNS — poll every 15s when pipeline is running (new
 *    completions show up), no auto-poll when idle (use manual refresh).
 *
 * 4. PAPER DETAIL / RUN DETAIL — no auto-poll (static once loaded).
 *
 * 5. MANUAL REFRESH — useRefreshAll() invalidates every query instantly.
 *    Exposed via a refresh button in the Header component.
 */

// ---------- Action status (always polling) ----------

export function useActionStatus() {
  return useQuery({
    queryKey: ['actionStatus'],
    queryFn: api.getActionStatus,
    refetchInterval: 3_000,
  })
}

// Helper: is the pipeline currently running?
function usePipelineRunning(): boolean {
  const { data } = useActionStatus()
  return data?.is_running ?? false
}

// ---------- Dashboard overview ----------

export function useOverview() {
  const isRunning = usePipelineRunning()
  return useQuery({
    queryKey: ['overview'],
    queryFn: api.getOverview,
    // Fast polling when running (stats update as papers complete),
    // slow polling when idle (data only changes between runs)
    refetchInterval: isRunning ? 10_000 : 60_000,
  })
}

// ---------- Papers list ----------

export function usePapers(params?: URLSearchParams) {
  const isRunning = usePipelineRunning()
  return useQuery({
    queryKey: ['papers', params?.toString()],
    queryFn: () => api.getPapers(params ?? undefined),
    refetchInterval: isRunning ? 15_000 : false,
  })
}

// ---------- Single paper detail ----------

export function usePaper(id: string) {
  return useQuery({
    queryKey: ['paper', id],
    queryFn: () => api.getPaper(id),
    enabled: !!id,
    // No auto-refresh — extraction data is static once written
  })
}

// ---------- Gaps ----------

export function useGaps(params?: URLSearchParams) {
  const isRunning = usePipelineRunning()
  return useQuery({
    queryKey: ['gaps', params?.toString()],
    queryFn: () => api.getGaps(params ?? undefined),
    refetchInterval: isRunning ? 15_000 : false,
  })
}

// ---------- Runs list ----------

export function useRuns() {
  const isRunning = usePipelineRunning()
  return useQuery({
    queryKey: ['runs'],
    queryFn: api.getRuns,
    refetchInterval: isRunning ? 15_000 : false,
  })
}

// ---------- Single run detail ----------

export function useRun(id: string) {
  return useQuery({
    queryKey: ['run', id],
    queryFn: () => api.getRun(id),
    enabled: !!id,
  })
}

// ---------- Discovery gaps ----------

export function useDiscoveryGaps() {
  return useQuery({
    queryKey: ['discoveryGaps'],
    queryFn: api.getDiscoveryGaps,
  })
}

// ---------- Gap matrix ----------

export function useMatrix() {
  const isRunning = usePipelineRunning()
  return useQuery({
    queryKey: ['matrix'],
    queryFn: api.getMatrix,
    refetchInterval: isRunning ? 15_000 : false,
  })
}

// ---------- Gap evidence ----------

export function useEvidence(gapId: string) {
  return useQuery({
    queryKey: ['evidence', gapId],
    queryFn: () => api.getEvidence(gapId),
    enabled: !!gapId,
  })
}

// ---------- Cached queries ----------

export function useCachedQueries() {
  return useQuery({
    queryKey: ['cachedQueries'],
    queryFn: api.getCachedQueries,
  })
}

// ---------- Manual refresh ----------

export function useRefreshAll() {
  const queryClient = useQueryClient()
  return useCallback(async () => {
    // Snapshot key counts before refresh
    const overviewBefore = queryClient.getQueryData<{ total_papers: number; total_gaps: number; completed: number }>(['overview'])

    await queryClient.invalidateQueries()

    // Compare after refetch settles (small delay for network)
    setTimeout(() => {
      const overviewAfter = queryClient.getQueryData<{ total_papers: number; total_gaps: number; completed: number }>(['overview'])

      const changes: string[] = []
      if (overviewBefore && overviewAfter) {
        const paperDiff = overviewAfter.total_papers - overviewBefore.total_papers
        const gapDiff = overviewAfter.total_gaps - overviewBefore.total_gaps
        const completedDiff = overviewAfter.completed - overviewBefore.completed

        if (paperDiff > 0) changes.push(`${paperDiff} new paper${paperDiff > 1 ? 's' : ''}`)
        if (completedDiff > 0) changes.push(`${completedDiff} newly completed`)
        if (gapDiff > 0) changes.push(`${gapDiff} new gap${gapDiff > 1 ? 's' : ''}`)
      }

      if (changes.length > 0) {
        showToast(`Updated: ${changes.join(', ')}`, 'success')
      } else {
        showToast('Data refreshed — no changes detected', 'info')
      }
    }, 1500)
  }, [queryClient])
}
