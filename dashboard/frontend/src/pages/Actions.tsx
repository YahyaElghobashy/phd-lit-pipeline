import { useState, useEffect } from 'react'
import { Play, Square, FileText, RotateCcw, AlertTriangle, Info, Loader2, CheckCircle } from 'lucide-react'
import Header from '../components/layout/Header'
import TerminalPanel from '../components/terminal/TerminalPanel'
import { useActionStatus } from '../hooks/useData'
import { api } from '../api/client'

interface FlagConfig {
  key: string
  label: string
  type: 'toggle' | 'text'
  placeholder?: string
  hint?: string
}

interface ActionConfig {
  id: string
  title: string
  description: string
  tooltip: string
  icon: React.ReactNode
  commandType: string
  flags: FlagConfig[]
}

const ACTIONS: ActionConfig[] = [
  {
    id: 'extraction',
    title: 'Extraction Pipeline',
    description: 'Run full PDF extraction with Claude Opus 4.6',
    tooltip: 'Reads PDFs from "Literature Review/" subfolders, sends each to Claude Opus 4.6 for deep 12-section extraction (identification, methodology, findings, relevance, etc.), saves structured JSON, and populates the Google Sheet. Each paper takes ~2–4 minutes. Use "Dry Run" to preview which papers would be processed without actually running.',
    icon: <FileText className="w-5 h-5" />,
    commandType: 'extraction',
    flags: [
      { key: 'dry_run', label: 'Dry Run', type: 'toggle', hint: 'Preview which papers will be processed without running extraction' },
      { key: 'skip_sheets', label: 'Skip Sheets', type: 'toggle', hint: 'Extract and save JSON locally, but don\'t write to Google Sheets' },
      { key: 'paper', label: 'Single Paper', type: 'text', placeholder: 'Paper filename...', hint: 'Process only this specific paper filename' },
      { key: 'reprocess', label: 'Reprocess', type: 'text', placeholder: 'Paper to reprocess...', hint: 'Force re-extraction of a previously processed paper' },
    ],
  },
  {
    id: 'gap_analysis',
    title: 'Gap Analyzer',
    description: 'Run gap coverage analysis across all papers',
    tooltip: 'Evaluates each extracted paper against all 100+ research gaps in the GAP_TRACKER. Claude Opus 4.6 determines whether each paper\'s findings address a gap (NOT ADDRESSED → DIRECTLY TACKLED). Updates the GAP_TRACKER and GAP_COVERAGE_MAP tabs in the Google Sheet. Can take 15–30 min for the full corpus.',
    icon: <AlertTriangle className="w-5 h-5" />,
    commandType: 'gap_analysis',
    flags: [
      { key: 'paper', label: 'Single Paper', type: 'text', placeholder: 'Paper filename...', hint: 'Analyze coverage for only this paper against all gaps' },
    ],
  },
  {
    id: 'backfill',
    title: 'Backfill Tasks',
    description: 'Backfill summaries or abstracts for existing papers',
    tooltip: 'Fills in missing fields for papers already extracted. "Backfill Summary" generates the Literature_Review_Summary paragraph for papers that don\'t have one. "Backfill Abstracts" fetches/generates abstracts for papers missing them. Useful after updating the extraction schema.',
    icon: <RotateCcw className="w-5 h-5" />,
    commandType: 'extraction',
    flags: [
      { key: 'backfill_summary', label: 'Backfill Summary', type: 'toggle', hint: 'Generate Literature Review Summary for papers missing one' },
      { key: 'backfill_abstracts', label: 'Backfill Abstracts', type: 'toggle', hint: 'Fetch or generate abstracts for papers missing them' },
    ],
  },
]

function ActionCard({
  config,
  isRunning,
  onRun,
}: {
  config: ActionConfig
  isRunning: boolean
  onRun: (commandType: string, flags: Record<string, string | boolean>) => void
}) {
  const [flagValues, setFlagValues] = useState<Record<string, string | boolean>>({})

  const handleRun = () => {
    onRun(config.commandType, flagValues)
  }

  return (
    <div className="glass-card p-5 relative">
      <div className="flex items-start gap-3 mb-4">
        <div className="text-accent-teal">{config.icon}</div>
        <div className="flex-1">
          <h3 className="text-sm font-medium">{config.title}</h3>
          <p className="text-xs text-text-muted mt-0.5">{config.description}</p>
        </div>
        {/* Info icon with tooltip */}
        <div className="tooltip-wrapper">
          <Info className="w-4 h-4 text-text-muted cursor-help" />
          <div className="tooltip-content">{config.tooltip}</div>
        </div>
      </div>

      <div className="space-y-2.5 mb-4">
        {config.flags.map((flag) => (
          <div key={flag.key}>
            {flag.type === 'toggle' ? (
              <label className="flex items-center gap-2 cursor-pointer group" title={flag.hint}>
                <input
                  type="checkbox"
                  checked={!!flagValues[flag.key]}
                  onChange={(e) => setFlagValues({ ...flagValues, [flag.key]: e.target.checked })}
                  disabled={isRunning}
                  className="w-4 h-4 rounded border-border bg-bg-surface text-accent-teal focus:ring-accent-teal/50 focus:ring-offset-0 disabled:opacity-50"
                />
                <span className="text-xs text-text-secondary group-hover:text-text-primary transition-colors">{flag.label}</span>
                {flag.hint && <span className="text-[10px] text-text-muted opacity-0 group-hover:opacity-100 transition-opacity ml-auto">{flag.hint}</span>}
              </label>
            ) : (
              <div className="group" title={flag.hint}>
                <input
                  type="text"
                  placeholder={flag.placeholder}
                  value={String(flagValues[flag.key] || '')}
                  onChange={(e) => setFlagValues({ ...flagValues, [flag.key]: e.target.value })}
                  disabled={isRunning}
                  className="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-teal/50 disabled:opacity-50"
                />
              </div>
            )}
          </div>
        ))}
      </div>

      <button
        onClick={handleRun}
        disabled={isRunning}
        className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-accent-teal/15 text-accent-teal text-sm font-medium hover:bg-accent-teal/25 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <Play className="w-4 h-4" />
        Run
      </button>
    </div>
  )
}

type CancelState = 'idle' | 'cancelling' | 'cancelled'

export default function Actions() {
  const { data: status } = useActionStatus()
  const isRunning = status?.is_running ?? false
  const [cancelState, setCancelState] = useState<CancelState>('idle')

  // Reset cancel state when pipeline stops running
  useEffect(() => {
    if (!isRunning && cancelState === 'cancelling') {
      setCancelState('cancelled')
      const timer = setTimeout(() => setCancelState('idle'), 2000)
      return () => clearTimeout(timer)
    }
    if (isRunning && cancelState !== 'idle') {
      // New run started — reset
      setCancelState('idle')
    }
  }, [isRunning, cancelState])

  const handleRun = async (commandType: string, flags: Record<string, string | boolean>) => {
    // Filter out empty string values and false booleans
    const cleanFlags: Record<string, string | boolean> = {}
    for (const [k, v] of Object.entries(flags)) {
      if (v === '' || v === false) continue
      cleanFlags[k] = v
    }
    try {
      await api.runAction(commandType, cleanFlags)
    } catch (err) {
      console.error('Failed to start action:', err)
    }
  }

  const handleCancel = async () => {
    setCancelState('cancelling')
    try {
      await api.cancelAction()
    } catch (err) {
      console.error('Failed to cancel:', err)
      setCancelState('idle')
    }
  }

  return (
    <div>
      <Header title="Actions" subtitle="Trigger pipeline commands and monitor output" />

      {/* Running indicator */}
      {isRunning && status && (
        <div className="glass-card p-4 mb-5 border-l-2 border-warning flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-2.5 h-2.5 rounded-full bg-warning animate-pulse" />
            <div>
              <p className="text-sm font-medium">Pipeline Running</p>
              <p className="text-xs text-text-muted">{status.command} — PID {status.pid}</p>
            </div>
          </div>
          <button
            onClick={handleCancel}
            disabled={cancelState !== 'idle'}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              cancelState === 'cancelled'
                ? 'bg-success/15 text-success'
                : cancelState === 'cancelling'
                ? 'bg-warning/15 text-warning cursor-wait'
                : 'bg-error/15 text-error hover:bg-error/25'
            }`}
          >
            {cancelState === 'cancelling' ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Cancelling...
              </>
            ) : cancelState === 'cancelled' ? (
              <>
                <CheckCircle className="w-4 h-4" />
                Cancelled
              </>
            ) : (
              <>
                <Square className="w-4 h-4" />
                Cancel
              </>
            )}
          </button>
        </div>
      )}

      {/* Action Cards */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        {ACTIONS.map((action) => (
          <ActionCard
            key={action.id}
            config={action}
            isRunning={isRunning}
            onRun={handleRun}
          />
        ))}
      </div>

      {/* Terminal */}
      <TerminalPanel className="h-[500px]" />
    </div>
  )
}
