import { BookOpen, FolderKanban, LayoutDashboard, LogOut, Settings, Trash2, UserRound } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

const navigation = [
  { to: '/', label: '工作台', icon: LayoutDashboard, end: true },
  { to: '/projects', label: '作品', icon: FolderKanban },
  { to: '/recycle-bin', label: '回收站', icon: Trash2 },
  { to: '/profile', label: '资料', icon: UserRound },
  { to: '/settings', label: '设置', icon: Settings },
]

function Avatar() {
  const { user } = useAuth()
  const fallback = (user?.nickname || user?.username || 'U').slice(0, 1).toUpperCase()
  return user?.avatar ? <img className="avatar" src={user.avatar} alt="" /> : <span className="avatar avatar-fallback">{fallback}</span>
}

export function AppShell() {
  const { user, logout } = useAuth()

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark"><BookOpen size={20} strokeWidth={2.2} /></span>
          <div><strong>墨笺</strong><small>小说创作工作台</small></div>
        </div>

        <nav className="side-nav" aria-label="主导航">
          {navigation.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => isActive ? 'nav-item active' : 'nav-item'}>
              <Icon size={18} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-user">
          <Avatar />
          <div className="sidebar-user-copy">
            <strong>{user?.nickname || user?.username}</strong>
            <small>@{user?.username}</small>
          </div>
          <button className="icon-button sidebar-logout" type="button" onClick={() => void logout()} title="退出登录" aria-label="退出登录">
            <LogOut size={17} />
          </button>
        </div>
      </aside>

      <main className="main-content"><Outlet /></main>

      <nav className="mobile-nav" aria-label="移动端导航">
        {navigation.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} className={({ isActive }) => isActive ? 'mobile-nav-item active' : 'mobile-nav-item'}>
            <Icon size={19} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
