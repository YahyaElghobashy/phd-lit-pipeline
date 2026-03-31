import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard, FileText, AlertTriangle, Clock,
  Play, Search, GraduationCap, ExternalLink, FolderOpen, Sheet, Settings
} from 'lucide-react'
import { useActionStatus } from '../../hooks/useData'
import { api } from '../../api/client'
import { EXTERNAL_LINKS } from '../../config'

const navItems = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/papers', label: 'Papers', icon: FileText },
  { to: '/gaps', label: 'Gap Tracker', icon: AlertTriangle },
  { to: '/runs', label: 'Run History', icon: Clock },
  { to: '/actions', label: 'Actions', icon: Play },
  { to: '/discovery', label: 'Discovery', icon: Search },
  { to: '/admin', label: 'Admin', icon: Settings },
]

export default function Sidebar() {
  const { data: status } = useActionStatus()
  const isRunning = status?.is_running ?? false
  const [researcherName, setResearcherName] = useState('Dr. Yara Aboubakr')

  useEffect(() => {
    api.getAdminConfig()
      .then((cfg) => {
        const name = cfg?.project?.researcher_name
        if (name) setResearcherName(name)
      })
      .catch(() => { /* fallback to default */ })
  }, [])

  return (
    <aside className="fixed inset-y-0 left-0 w-60 bg-bg-surface border-r border-border flex flex-col z-50">
      {/* Branding */}
      <div className="p-5 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-accent-teal/20 flex items-center justify-center">
            <GraduationCap className="w-5 h-5 text-accent-teal" />
          </div>
          <div>
            <h1 className="text-sm font-semibold text-text-primary">PhD Pipeline</h1>
            <p className="text-xs text-accent-gold">{researcherName}</p>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 px-3 space-y-1">
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                isActive
                  ? 'bg-accent-teal/15 text-accent-teal-light font-medium'
                  : 'text-text-secondary hover:text-text-primary hover:bg-bg-elevated'
              }`
            }
          >
            <Icon className="w-4.5 h-4.5" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* External Resources */}
      {EXTERNAL_LINKS.filter(l => l.enabled).length > 0 && (
        <div className="px-3 pb-3">
          <p className="text-[10px] uppercase tracking-wider text-text-muted px-3 mb-2">Resources</p>
          {EXTERNAL_LINKS.filter(l => l.enabled).map((link) => {
            const IconMap = { Sheet, FolderOpen, ExternalLink }
            const Icon = IconMap[link.icon] || ExternalLink
            return (
              <a
                key={link.url}
                href={link.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-text-secondary hover:text-text-primary hover:bg-bg-elevated transition-colors"
              >
                <Icon className="w-4 h-4" />
                <span className="flex-1">{link.label}</span>
                <ExternalLink className="w-3 h-3 text-text-muted" />
              </a>
            )
          })}
        </div>
      )}

      {/* Pipeline Status */}
      <div className="p-4 border-t border-border">
        <div className="flex items-center gap-2.5">
          <div className={`w-2.5 h-2.5 rounded-full ${
            isRunning
              ? 'bg-warning animate-pulse'
              : 'bg-success'
          }`} />
          <span className="text-xs text-text-muted">
            {isRunning ? 'Pipeline running...' : 'Pipeline idle'}
          </span>
        </div>
        {isRunning && status?.command && (
          <p className="text-xs text-text-muted mt-1 truncate font-mono">
            {status.command}
          </p>
        )}
      </div>
    </aside>
  )
}
