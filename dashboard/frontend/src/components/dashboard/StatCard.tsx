import type { ReactNode } from 'react'

interface StatCardProps {
  label: string
  value: number | string
  icon: ReactNode
  color?: string
  subtitle?: string
}

export default function StatCard({ label, value, icon, color = 'text-accent-teal', subtitle }: StatCardProps) {
  return (
    <div className="glass-card p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium text-text-muted uppercase tracking-wider">{label}</p>
          <p className={`stat-value mt-1 ${color}`}>{value}</p>
          {subtitle && <p className="text-xs text-text-muted mt-1">{subtitle}</p>}
        </div>
        <div className={`${color} opacity-50`}>{icon}</div>
      </div>
    </div>
  )
}
