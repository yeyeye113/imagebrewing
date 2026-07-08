import { Routes, Route, Navigate } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { Layout } from './components/Layout'
import { LogPanel } from './components/LogViewer.tsx'
import { getMessage, getStoredLocale } from '@/lib/i18n'

const HomePage = lazy(() => import('./pages/HomePage'))
const NewProjectPage = lazy(() => import('./pages/NewProjectPage'))
const ProfilePage = lazy(() => import('./pages/ProfilePage'))
const ScoresPage = lazy(() => import('./pages/ScoresPage'))
const ConfigPage = lazy(() => import('./pages/ConfigPage'))
const RunPage = lazy(() => import('./pages/RunPage'))
const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const ReportPage = lazy(() => import('./pages/ReportPage'))
const ComparePage = lazy(() => import('./pages/ComparePage'))
const PricingPage = lazy(() => import('./pages/PricingPage'))
const LoginPage = lazy(() => import('./pages/LoginPage'))
const RechargePage = lazy(() => import('./pages/RechargePage'))
const SettingsPage = lazy(() => import('./pages/SettingsPage'))
const LogPage = lazy(() => import('./pages/LogPage'))

const fallback = (
  <div className="p-8 text-center text-sm text-gray-400 dark:text-gray-500">
    {getMessage(getStoredLocale(), 'common.loading')}
  </div>
)

function AppRoutes() {
  return (
    <>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/new" element={<NewProjectPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/scores" element={<ScoresPage />} />
        <Route path="/config" element={<ConfigPage />} />
        <Route path="/run" element={<RunPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/report" element={<ReportPage />} />
        <Route path="/compare" element={<ComparePage />} />
        <Route path="/pricing" element={<PricingPage />} />
        <Route path="/recharge" element={<RechargePage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/logs" element={<LogPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>

      {/* 全局日志面板（悬浮层） */}
      <LogPanel />
    </>
  )
}

function App() {
  return (
    <Suspense fallback={fallback}>
      <Routes>
        {/* 登录独立布局，不嵌侧栏 */}
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/*"
          element={
            <Layout>
              <Suspense fallback={fallback}>
                <AppRoutes />
              </Suspense>
            </Layout>
          }
        />
      </Routes>
    </Suspense>
  )
}

export default App
