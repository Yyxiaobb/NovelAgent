import { Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth/AuthContext'
import { AppShell } from './components/AppShell'
import { AuthPage } from './pages/AuthPage'
import { DashboardPage } from './pages/DashboardPage'
import { ProfilePage } from './pages/ProfilePage'
import { ProjectsPage } from './pages/ProjectsPage'
import { ProjectDetailPage } from './pages/ProjectDetailPage'
import { ChapterDetailPage } from './pages/ChapterDetailPage'
import { OutlineDetailPage } from './pages/OutlineDetailPage'
import { RecycleBinPage } from './pages/RecycleBinPage'
import { SettingsPage } from './pages/SettingsPage'

function ProtectedRoute() {
  const { user, loading } = useAuth()
  if (loading) return <div className="app-loading"><span className="loading-mark">墨</span><p>正在整理工作台…</p></div>
  return user ? <Outlet /> : <Navigate to="/auth" replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/auth" element={<AuthPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="projects" element={<ProjectsPage />} />
          <Route path="projects/:projectId" element={<ProjectDetailPage />} />
          <Route path="projects/:projectId/chapters/:chapterId" element={<ChapterDetailPage />} />
          <Route path="projects/:projectId/chapters/:chapterId/:feature" element={<ChapterDetailPage />} />
          <Route path="projects/:projectId/outline" element={<OutlineDetailPage />} />
          <Route path="projects/:projectId/outline/:feature" element={<OutlineDetailPage />} />
          <Route path="recycle-bin" element={<RecycleBinPage />} />
          <Route path="profile" element={<ProfilePage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
