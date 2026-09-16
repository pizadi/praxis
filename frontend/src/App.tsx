import { useEffect, useState } from 'react'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { Spin } from 'antd'

import { getStoredUser, type StoredUser } from './api/client'
import AppLayout from './components/AppLayout'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import PatientsPage from './pages/PatientsPage'
import PatientDetailPage from './pages/PatientDetailPage'
import AppointmentPage from './pages/AppointmentPage'
import SchedulePage from './pages/SchedulePage'
import TodayPaymentsPage from './pages/TodayPaymentsPage'
import TaxonomiesPage from './pages/TaxonomiesPage'
import StatsPage from './pages/StatsPage'
import UsersPage from './pages/UsersPage'
import TrashPage from './pages/TrashPage'
import BackupPage from './pages/BackupPage'
import AuditPage from './pages/AuditPage'

export default function App() {
  const [user, setUser] = useState<StoredUser | null>(getStoredUser())
  const [checked, setChecked] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    setUser(getStoredUser())
    setChecked(true)
  }, [])

  // keep user state in sync on login/logout navigation
  useEffect(() => {
    const handler = () => setUser(getStoredUser())
    window.addEventListener('clinic-auth-changed', handler)
    return () => window.removeEventListener('clinic-auth-changed', handler)
  }, [])

  if (!checked) {
    return (
      <div style={{ display: 'grid', placeItems: 'center', height: '100vh' }}>
        <Spin size="large" />
      </div>
    )
  }

  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage onLogin={() => setUser(getStoredUser())} />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    )
  }

  return (
    <Routes>
      <Route element={<AppLayout user={user} onLogout={() => { setUser(null); navigate('/login') }} />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/patients" element={<PatientsPage />} />
        <Route path="/patients/:id" element={<PatientDetailPage />} />
        <Route path="/appointments/:id" element={<AppointmentPage />} />
        <Route path="/schedule" element={<SchedulePage />} />
        <Route path="/payments" element={<TodayPaymentsPage />} />
        <Route path="/taxonomies" element={<TaxonomiesPage />} />
        <Route path="/stats" element={<StatsPage />} />
        <Route path="/users" element={<UsersPage />} />
        <Route path="/backup" element={<BackupPage />} />
        <Route path="/trash" element={<TrashPage />} />
        <Route path="/audit" element={<AuditPage />} />
      </Route>
      <Route path="/login" element={<Navigate to="/" replace />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
