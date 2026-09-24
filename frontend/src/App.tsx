import { Suspense, lazy, useEffect, useState, type ReactNode } from 'react'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { Spin } from 'antd'

import {
  api,
  clearAuth,
  ensureAccessToken,
  getStoredUser,
  storeUser,
  type StoredUser,
} from './api/client'
import AppLayout from './components/AppLayout'
import ErrorBoundary from './components/ErrorBoundary'

// route-level code splitting: antd-heavy pages load on demand instead of
// one monolithic bundle
const LoginPage = lazy(() => import('./pages/LoginPage'))
const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const PatientsPage = lazy(() => import('./pages/PatientsPage'))
const PatientDetailPage = lazy(() => import('./pages/PatientDetailPage'))
const AppointmentPage = lazy(() => import('./pages/AppointmentPage'))
const SchedulePage = lazy(() => import('./pages/SchedulePage'))
const TodayPaymentsPage = lazy(() => import('./pages/TodayPaymentsPage'))
const TaxonomiesPage = lazy(() => import('./pages/TaxonomiesPage'))
const StatsPage = lazy(() => import('./pages/StatsPage'))
const UsersPage = lazy(() => import('./pages/UsersPage'))
const RolesPage = lazy(() => import('./pages/RolesPage'))
const QuestionnairesPage = lazy(() => import('./pages/QuestionnairesPage'))
const QuestionnaireResponsesPage = lazy(() => import('./pages/QuestionnaireResponsesPage'))
const TrashPage = lazy(() => import('./pages/TrashPage'))
const BackupPage = lazy(() => import('./pages/BackupPage'))
const AuditPage = lazy(() => import('./pages/AuditPage'))

const CenteredSpin = () => (
  <div style={{ display: 'grid', placeItems: 'center', height: '100vh' }}>
    <Spin size="large" />
  </div>
)

const Lazy = ({ children }: { children: ReactNode }) => (
  <Suspense fallback={<CenteredSpin />}>
    <ErrorBoundary>{children}</ErrorBoundary>
  </Suspense>
)

export default function App() {
  const [user, setUser] = useState<StoredUser | null>(getStoredUser())
  const [checked, setChecked] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    const cached = getStoredUser()
    if (!cached) {
      setChecked(true)
      return
    }
    ensureAccessToken()
      .then((token) => {
        if (!token) throw new Error('session refresh failed')
        return api.get('/auth/me')
      })
      .then((me) => {
        const fresh: StoredUser = {
          id: me.data.id,
          username: me.data.username,
          full_name: me.data.full_name,
          role_id: me.data.role_id,
          role_name: me.data.role_name,
          permissions: me.data.permissions ?? [],
        }
        storeUser(fresh)
        setUser(fresh)
      })
      .catch(() => {
        clearAuth()
        setUser(null)
      })
      .finally(() => setChecked(true))
  }, [])

  // keep user state in sync on login/logout navigation
  useEffect(() => {
    const handler = () => setUser(getStoredUser())
    window.addEventListener('clinic-auth-changed', handler)
    return () => window.removeEventListener('clinic-auth-changed', handler)
  }, [])

  if (!checked) {
    return <CenteredSpin />
  }

  if (!user) {
    return (
      <Routes>
        <Route
          path="/login"
          element={
            <ErrorBoundary>
              <LoginPage onLogin={() => setUser(getStoredUser())} />
            </ErrorBoundary>
          }
        />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    )
  }

  return (
    <Routes>
      <Route
        element={<AppLayout user={user} onLogout={() => { setUser(null); navigate('/login') }} />}
      >
        <Route path="/" element={<Lazy><DashboardPage /></Lazy>} />
        <Route path="/patients" element={<Lazy><PatientsPage /></Lazy>} />
        <Route path="/patients/:id" element={<Lazy><PatientDetailPage /></Lazy>} />
        <Route path="/appointments/:id" element={<Lazy><AppointmentPage /></Lazy>} />
        <Route path="/schedule" element={<Lazy><SchedulePage /></Lazy>} />
        <Route path="/payments" element={<Lazy><TodayPaymentsPage /></Lazy>} />
        <Route path="/taxonomies" element={<Lazy><TaxonomiesPage /></Lazy>} />
        <Route path="/stats" element={<Lazy><StatsPage /></Lazy>} />
        <Route path="/users" element={<Lazy><UsersPage /></Lazy>} />
        <Route path="/roles" element={<Lazy><RolesPage /></Lazy>} />
        <Route path="/questionnaires" element={<Lazy><QuestionnairesPage /></Lazy>} />
        <Route path="/questionnaire-responses" element={<Lazy><QuestionnaireResponsesPage /></Lazy>} />
        <Route path="/backup" element={<Lazy><BackupPage /></Lazy>} />
        <Route path="/trash" element={<Lazy><TrashPage /></Lazy>} />
        <Route path="/audit" element={<Lazy><AuditPage /></Lazy>} />
      </Route>
      <Route path="/login" element={<Navigate to="/" replace />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
