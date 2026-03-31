import { FileText, AlertTriangle, CheckCircle, XCircle } from 'lucide-react'
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import Header from '../components/layout/Header'
import StatCard from '../components/dashboard/StatCard'
import LoadingSpinner from '../components/shared/LoadingSpinner'
import { useOverview } from '../hooks/useData'

const TERRACOTTA = '#C4704B'
const COLORS = ['#C4704B', '#9A7B4F', '#7B9E87', '#8C7A68', '#A85835', '#BF5540']
const COVERAGE_COLORS: Record<string, string> = {
  'DIRECTLY TACKLED': '#5B8C5A',
  'SUBSTANTIALLY COVERED': '#7B9E87',
  'PARTIALLY ADDRESSED': '#C4944B',
  'NOT ADDRESSED': '#BF5540',
}

export default function Dashboard() {
  const { data, isLoading } = useOverview()

  if (isLoading || !data) return <LoadingSpinner />

  const relevanceData = Object.entries(data.by_relevance).map(([name, value]) => ({ name, value }))
  const themeData = Object.entries(data.by_theme)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(([name, value]) => ({ name: name.length > 25 ? name.slice(0, 22) + '...' : name, value }))
  const coverageData = Object.entries(data.gaps_by_coverage).map(([name, value]) => ({ name, value }))

  const formatDuration = (s: number) => s >= 60 ? `${Math.round(s / 60)}m` : `${Math.round(s)}s`

  return (
    <div>
      <Header title="Dashboard" subtitle="Literature extraction pipeline overview" />

      {/* Stat Cards */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <StatCard
          label="Total Papers"
          value={data.total_papers}
          icon={<FileText className="w-6 h-6" />}
          color="text-accent-teal"
          subtitle={`Avg ${formatDuration(data.avg_duration_seconds)}/paper`}
        />
        <StatCard
          label="Completed"
          value={data.completed}
          icon={<CheckCircle className="w-6 h-6" />}
          color="text-success"
        />
        <StatCard
          label="Failed"
          value={data.failed}
          icon={<XCircle className="w-6 h-6" />}
          color="text-error"
        />
        <StatCard
          label="Research Gaps"
          value={data.total_gaps}
          icon={<AlertTriangle className="w-6 h-6" />}
          color="text-accent-gold"
          subtitle={`${data.gaps_by_coverage['DIRECTLY TACKLED'] || 0} directly tackled`}
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        {/* Relevance Distribution */}
        <div className="glass-card p-5">
          <h3 className="text-sm font-medium text-text-secondary mb-4">Papers by Relevance</h3>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie
                data={relevanceData}
                cx="50%" cy="50%"
                innerRadius={55} outerRadius={85}
                paddingAngle={3}
                dataKey="value"
                stroke="none"
              >
                {relevanceData.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{ background: '#FFFFFF', border: '1px solid rgba(140,120,95,0.2)', borderRadius: 8, fontSize: 12 }}
                itemStyle={{ color: '#2D2117' }}
              />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex flex-wrap gap-3 justify-center mt-2">
            {relevanceData.map((d, i) => (
              <div key={d.name} className="flex items-center gap-1.5 text-xs text-text-muted">
                <div className="w-2.5 h-2.5 rounded-sm" style={{ background: COLORS[i % COLORS.length] }} />
                {d.name} ({d.value})
              </div>
            ))}
          </div>
        </div>

        {/* Theme Distribution */}
        <div className="glass-card p-5">
          <h3 className="text-sm font-medium text-text-secondary mb-4">Papers by Theme</h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={themeData} layout="vertical" margin={{ left: 10, right: 20 }}>
              <XAxis type="number" tick={{ fill: '#8C7A68', fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="name" tick={{ fill: '#5C4B3A', fontSize: 11 }} width={140} axisLine={false} tickLine={false} />
              <Tooltip
                contentStyle={{ background: '#FFFFFF', border: '1px solid rgba(140,120,95,0.2)', borderRadius: 8, fontSize: 12 }}
                itemStyle={{ color: '#2D2117' }}
              />
              <Bar dataKey="value" fill={TERRACOTTA} radius={[0, 4, 4, 0]} barSize={14} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Gap Coverage */}
      <div className="glass-card p-5">
        <h3 className="text-sm font-medium text-text-secondary mb-4">Gap Coverage Distribution</h3>
        <div className="flex items-center gap-6">
          <div className="w-48">
            <ResponsiveContainer width="100%" height={160}>
              <PieChart>
                <Pie
                  data={coverageData}
                  cx="50%" cy="50%"
                  innerRadius={40} outerRadius={65}
                  paddingAngle={2}
                  dataKey="value"
                  stroke="none"
                >
                  {coverageData.map((d) => (
                    <Cell key={d.name} fill={COVERAGE_COLORS[d.name] || '#8C7A68'} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="flex-1 grid grid-cols-2 gap-3">
            {coverageData.map((d) => (
              <div key={d.name} className="flex items-center justify-between px-3 py-2 rounded-lg bg-bg-elevated">
                <div className="flex items-center gap-2">
                  <div className="w-2.5 h-2.5 rounded-sm" style={{ background: COVERAGE_COLORS[d.name] || '#8C7A68' }} />
                  <span className="text-xs text-text-secondary">{d.name}</span>
                </div>
                <span className="text-sm font-semibold">{d.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
