import { Link, NavLink, Navigate, Outlet, useNavigate } from 'react-router-dom'
import { isAuthed, setToken } from '../lib/api.js'

const NAV = [
  { to: '/dashboard', label: 'Dashboard', icon: '◧' },
  { to: '/playground', label: 'Playground', icon: '▷' },
  { to: '/api-keys', label: 'API Keys', icon: '⚿' },
  { to: '/audit', label: 'Audit Log', icon: '≡' },
]

export default function Layout() {
  const navigate = useNavigate()
  if (!isAuthed()) return <Navigate to="/login" replace />

  const logout = () => {
    setToken(null)
    navigate('/login')
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <Link className="brand" to="/">State<span className="jar">Jar</span></Link>
        <nav className="side-nav">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} className={({ isActive }) => (isActive ? 'active' : '')}>
              <span className="icon">{n.icon}</span> {n.label}
            </NavLink>
          ))}
        </nav>
        <button className="side-logout" onClick={logout}>
          <span className="icon">↩</span> Logout
        </button>
      </aside>
      <main className="shell-main">
        <Outlet />
      </main>
    </div>
  )
}
