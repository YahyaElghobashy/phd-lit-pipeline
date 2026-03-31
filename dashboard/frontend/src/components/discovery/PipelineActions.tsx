import { useState, useEffect } from 'react'
import { Play, FileText, Microscope, Loader2, Terminal, AlertCircle, ChevronDown, ChevronUp } from 'lucide-react'
import { api } from '../../api/client'
import { showToast } from '../shared/Toast'
import { useActionStatus } from '../../hooks/useData'
import TerminalPanel from '../terminal/TerminalPanel'

interface PipelineActionsProps {
  selectedPaperCount: number
}

type ActionType = 'full' | 'analyze'

export default function PipelineActions({ selectedPaperCount }: PipelineActionsProps) {
  const { data: actionStatus } = useActionStatus()
  const [lastAction, setLastAction] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showTerminal, setShowTerminal] = useState(false)
  const isRunning = actionStatus?.is_running ?? false

  // Auto-expand terminal when pipeline starts
  useEffect(() => {
    if (isRunning && !showTerminal) {
      setShowTerminal(true)
    }
  }, [isRunning])

  const runAction = async (action: ActionType, flags?: Record<string, unknown>) => {
    setError(null)
    showToast(`Starting ${action === 'full' ? 'full pipeline' : 'gap analysis'}...`, 'info')
    try {
      const result = await api.runDiscoveryPipeline(action, flags)
      setLastAction(action)
      showToast(`Pipeline started (PID ${result.pid})`, 'success')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to start'
      setError(msg)
      showToast(`Error: ${msg}`, 'info')
    }
  }

  const elapsed = actionStatus?.elapsed_seconds ?? 0
  const elapsedStr = elapsed > 0 ? `${Math.floor(elapsed / 60)}m ${Math.round(elapsed % 60)}s` : ''

  return (
    <div className="glass-card">
      <div className="px-3 py-2 flex items-center justify-between">
        <h3 className="text-xs font-semibold text-text-primary">Pipeline</h3>
        <div className="flex items-center gap-2">
          {isRunning && (
            <div className="flex items-center gap-1.5 text-[10px]">
              <Loader2 className="w-3 h-3 text-accent-teal animate-spin" />
              <span className="text-accent-teal font-medium">Running</span>
              {elapsedStr && <span className="text-text-muted">{elapsedStr}</span>}
            </div>
          )}
          {error && (
            <div className="flex items-center gap-1 text-[10px] text-error">
              <AlertCircle className="w-3 h-3" />{error}
            </div>
          )}
        </div>
      </div>

      <div className="px-3 pb-2.5 flex gap-2">
        <ActionBtn
          icon={<Play className="w-3.5 h-3.5" />}
          label="Full Pipeline"
          onClick={() => runAction('full', { gap_limit: 5 })}
          disabled={isRunning}
          active={isRunning && lastAction === 'full'}
          primary
        />
        <ActionBtn
          icon={<FileText className="w-3.5 h-3.5" />}
          label="Dry Run"
          onClick={() => runAction('full', { gap_limit: 5, dry_run: true })}
          disabled={isRunning}
        />
        <ActionBtn
          icon={<Microscope className="w-3.5 h-3.5" />}
          label="Gap Analysis"
          onClick={() => runAction('analyze')}
          disabled={isRunning}
          active={isRunning && lastAction === 'analyze'}
        />
        <button
          onClick={() => setShowTerminal(!showTerminal)}
          className={`flex items-center gap-1.5 px-3 py-2 rounded-lg border text-xs font-medium transition-colors ${
            showTerminal
              ? 'bg-accent-teal/10 border-accent-teal/30 text-accent-teal'
              : 'bg-bg-surface border-border text-text-secondary hover:border-accent-teal/30 hover:bg-bg-elevated'
          }`}
        >
          <Terminal className="w-3.5 h-3.5" />
          Terminal
          {showTerminal ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        </button>
      </div>

      {/* Collapsible terminal */}
      {showTerminal && (
        <div className="border-t border-border">
          <TerminalPanel className="h-[300px]" />
        </div>
      )}
    </div>
  )
}

function ActionBtn({
  icon, label, onClick, disabled, active, primary,
}: {
  icon: React.ReactNode; label: string; onClick: () => void; disabled: boolean; active?: boolean; primary?: boolean
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`flex items-center gap-1.5 px-3 py-2 rounded-lg border text-xs font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
        active
          ? 'bg-accent-teal/10 border-accent-teal/30 text-accent-teal'
          : primary
          ? 'bg-accent-teal/5 border-accent-teal/20 text-accent-teal hover:bg-accent-teal/10'
          : 'bg-bg-surface border-border text-text-secondary hover:bg-bg-elevated'
      }`}
    >
      {active ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : icon}
      {label}
    </button>
  )
}
