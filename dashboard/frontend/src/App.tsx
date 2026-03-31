import { Routes, Route, Navigate } from 'react-router-dom'
import Sidebar from './components/layout/Sidebar'
import ToastContainer from './components/shared/Toast'
import Dashboard from './pages/Dashboard'
import Papers from './pages/Papers'
import PaperDetail from './pages/PaperDetail'
import Gaps from './pages/Gaps'
import Runs from './pages/Runs'
import Actions from './pages/Actions'
import Discovery from './pages/Discovery'
import Admin from './pages/Admin'

export default function App() {
  return (
    <div className="flex min-h-screen bg-bg-primary text-text-primary">
      <Sidebar />
      <main className="flex-1 ml-60 p-8 max-w-[1400px]">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/papers" element={<Papers />} />
          <Route path="/papers/:id" element={<PaperDetail />} />
          <Route path="/gaps" element={<Gaps />} />
          <Route path="/runs" element={<Runs />} />
          <Route path="/actions" element={<Actions />} />
          <Route path="/discovery" element={<Discovery />} />
          <Route path="/admin" element={<Admin />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      <ToastContainer />
    </div>
  )
}
