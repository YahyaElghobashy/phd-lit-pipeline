interface BadgeProps {
  label: string
  variant?: 'teal' | 'gold' | 'success' | 'warning' | 'error' | 'muted'
}

const variants: Record<string, string> = {
  teal: 'bg-accent-teal/10 text-accent-teal border border-accent-teal/20',
  gold: 'bg-accent-gold/10 text-accent-gold border border-accent-gold/20',
  success: 'bg-success/10 text-success border border-success/20',
  warning: 'bg-warning/10 text-warning border border-warning/20',
  error: 'bg-error/10 text-error border border-error/20',
  muted: 'bg-bg-elevated text-text-muted border border-border',
}

export default function Badge({ label, variant = 'muted' }: BadgeProps) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium ${variants[variant]}`}>
      {label}
    </span>
  )
}

export function CoverageBadge({ level }: { level: string }) {
  const v = level.toUpperCase()
  if (v.includes('DIRECTLY')) return <Badge label={level} variant="success" />
  if (v.includes('SUBSTANTIALLY')) return <Badge label={level} variant="teal" />
  if (v.includes('PARTIALLY')) return <Badge label={level} variant="warning" />
  return <Badge label={level} variant="error" />
}

export function StatusBadge({ status }: { status: string }) {
  if (status === 'complete') return <Badge label="Complete" variant="success" />
  if (status.includes('failed')) return <Badge label="Failed" variant="error" />
  if (status === 'extracting' || status === 'populating') return <Badge label={status} variant="warning" />
  return <Badge label={status} variant="muted" />
}

export function RelevanceBadge({ tier }: { tier: string }) {
  if (tier.toLowerCase().includes('essential')) return <Badge label={tier} variant="gold" />
  if (tier.toLowerCase().includes('highly')) return <Badge label={tier} variant="teal" />
  if (tier.toLowerCase().includes('moderate')) return <Badge label={tier} variant="warning" />
  return <Badge label={tier || 'N/A'} variant="muted" />
}
