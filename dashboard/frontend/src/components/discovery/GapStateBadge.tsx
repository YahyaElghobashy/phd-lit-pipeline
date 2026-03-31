import Badge from '../shared/Badge'

const stateVariants: Record<string, 'error' | 'warning' | 'gold' | 'success' | 'muted'> = {
  'Open': 'error',
  'Under Investigation': 'warning',
  'Partially Resolved': 'gold',
  'Resolved': 'success',
}

const stateShort: Record<string, string> = {
  'Open': 'Open',
  'Under Investigation': 'Investigating',
  'Partially Resolved': 'Partial',
  'Resolved': 'Resolved',
}

export default function GapStateBadge({ state }: { state: string }) {
  const variant = stateVariants[state] ?? 'muted'
  const label = stateShort[state] ?? state ?? 'Unknown'
  return <Badge label={label} variant={variant} />
}

export function PctRemainingBar({ pct }: { pct: number }) {
  // Bar shows how much has been eliminated (filled portion = progress toward resolution)
  const filled = 100 - pct
  const color =
    pct < 10 ? 'bg-success' :
    pct < 40 ? 'bg-success/70' :
    pct < 80 ? 'bg-accent-gold' :
    'bg-error/40'

  return (
    <div className="w-full h-1 rounded-full bg-bg-elevated overflow-hidden">
      <div
        className={`h-full rounded-full transition-all duration-500 ${color}`}
        style={{ width: `${Math.max(filled, 2)}%` }}
      />
    </div>
  )
}
