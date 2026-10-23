import {
  BookOpen,
  BookOpenCheck,
  FolderKanban,
  LayoutDashboard,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  Sparkles,
  Sun,
  Moon,
  Trash2,
} from 'lucide-react'
import { NavLink, Outlet, useLocation, useSearchParams } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { ProjectCreationModal } from './ProjectCreationModal'

const navigation = [
  { to: '/', label: '工作台', icon: LayoutDashboard, end: true },
  { to: '/projects', label: '作品', icon: FolderKanban },
  { to: '/knowledge-bases', label: '知识库', icon: BookOpenCheck },
  { to: '/inspirations', label: '灵感', icon: Sparkles },
  { to: '/recycle-bin', label: '回收站', icon: Trash2 },
  { to: '/settings', label: '设置', icon: Settings },
]

function Avatar() {
  const { user } = useAuth()
  const fallback = (user?.nickname || user?.username || 'U').slice(0, 1).toUpperCase()
  return user?.avatar ? (
    <img className="avatar" src={user.avatar} alt="" />
  ) : (
    <span className="avatar avatar-fallback">{fallback}</span>
  )
}

export function AppShell() {
  const { user, logout } = useAuth()
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    try {
      return window.localStorage.getItem('novel-agent-theme') === 'light' ? 'light' : 'dark'
    } catch {
      return 'dark'
    }
  })
  const { pathname } = useLocation()
  const detailMode = /^\/projects\/[^/]+\/(?:outline(?:\/[^/]+)?|chapters\/[^/]+(?:\/[^/]+)?)$/.test(pathname)
  const [searchParams, setSearchParams] = useSearchParams()
  const creationOpen = searchParams.get('create') === '1'

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      window.localStorage.setItem('novel-agent-theme', theme)
    } catch {
      // Keep the current selection for this session when storage is unavailable.
    }
  }, [theme])

  function closeCreation() {
    setSearchParams({}, { replace: true })
  }

  return (
    <div
      className={`${sidebarCollapsed ? 'app-layout sidebar-collapsed' : 'app-layout'}${detailMode ? ' detail-mode' : ''}`}
    >
      {!detailMode && (
        <aside className={sidebarCollapsed ? 'sidebar sidebar-collapsed' : 'sidebar'}>
          <div className="brand">
            <span className="brand-mark">
              <BookOpen size={20} strokeWidth={2.2} />
            </span>
            <div>
              <strong>墨笺</strong>
              <small>小说创作工作台</small>
            </div>
            <button
              className="icon-button sidebar-toggle"
              type="button"
              onClick={() => setSidebarCollapsed(current => !current)}
              aria-label={sidebarCollapsed ? '展开主侧边栏' : '收起主侧边栏'}
              title={sidebarCollapsed ? '展开主侧边栏' : '收起主侧边栏'}
            >
              {sidebarCollapsed ? <PanelLeftOpen size={17} /> : <PanelLeftClose size={17} />}
            </button>
          </div>

          <nav className="side-nav" aria-label="主导航">
            {navigation
              .filter(({ to }) => to !== '/recycle-bin')
              .map(({ to, label, icon: Icon, end }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={end}
                  className={({ isActive }) => (isActive ? 'nav-item active' : 'nav-item')}
                >
                  <Icon size={18} />
                  <span>{label}</span>
                </NavLink>
              ))}
          </nav>

          <div className="sidebar-footer">
            <nav className="side-nav" aria-label="辅助导航">
              <NavLink to="/recycle-bin" className={({ isActive }) => (isActive ? 'nav-item active' : 'nav-item')}>
                <Trash2 size={18} />
                <span>回收站</span>
              </NavLink>
            </nav>

            <div className="sidebar-user">
              <NavLink
                to="/profile"
                className={({ isActive }) => (isActive ? 'sidebar-user-profile active' : 'sidebar-user-profile')}
                aria-label="打开个人资料"
              >
                <Avatar />
                <div className="sidebar-user-copy">
                  <strong>{user?.nickname || user?.username}</strong>
                  <small>@{user?.username}</small>
                </div>
              </NavLink>
              <button
                className="icon-button sidebar-logout"
                type="button"
                onClick={() => void logout()}
                title="退出登录"
                aria-label="退出登录"
              >
                <LogOut size={17} />
              </button>
            </div>
          </div>
        </aside>
      )}

      <main className="main-content">
        <Outlet />
      </main>

      <div className="theme-switcher" role="group" aria-label="选择页面色调">
        <button
          className={theme === 'light' ? 'theme-option active' : 'theme-option'}
          type="button"
          aria-pressed={theme === 'light'}
          onClick={() => setTheme('light')}
          title="切换到亮色"
        >
          <Sun size={15} />
          <span>亮色</span>
        </button>
        <button
          className={theme === 'dark' ? 'theme-option active' : 'theme-option'}
          type="button"
          aria-pressed={theme === 'dark'}
          onClick={() => setTheme('dark')}
          title="切换到暗色"
        >
          <Moon size={15} />
          <span>暗色</span>
        </button>
      </div>

      <ProjectCreationModal
        open={creationOpen}
        draftKey={user?.id ? String(user.id) : undefined}
        onClose={closeCreation}
        onCreated={() => {
          window.dispatchEvent(new Event('projects:changed'))
          closeCreation()
        }}
      />

      {!detailMode && (
        <nav className="mobile-nav" aria-label="移动端导航">
          {navigation.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => (isActive ? 'mobile-nav-item active' : 'mobile-nav-item')}
            >
              <Icon size={19} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
      )}
    </div>
  )
}
