import { useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { useRefreshAll } from '../../hooks/useData'

interface HeaderProps {
  title: string
  subtitle?: string
}

export default function Header({ title, subtitle }: HeaderProps) {
  const refreshAll = useRefreshAll()
  const [spinning, setSpinning] = useState(false)

  const handleRefresh = () => {
    refreshAll()
    setSpinning(true)
    setTimeout(() => setSpinning(false), 800)
  }

  return (
    <header className="flex items-start justify-between mb-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle && (
          <p className="text-sm text-text-secondary mt-1">{subtitle}</p>
        )}
      </div>
      <button
        onClick={handleRefresh}
        title="Refresh all data"
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-text-muted hover:text-text-primary hover:bg-bg-elevated transition-colors"
      >
        <RefreshCw className={`w-3.5 h-3.5 ${spinning ? 'animate-spin' : ''}`} />
        Refresh
      </button>
    </header>
  )
}
