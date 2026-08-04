import { Link, NavLink, Navigate, Outlet, useNavigate } from 'react-router-dom'
import { isAuthed, setToken } from '../lib/api.js'
import { clearAll } from '../lib/transcript.js'

const NAV = [
  { to: '/dashboard', label: 'Dashboard', icon: '◧' },
  { to: '/playground', label: 'Playground', icon: '▷' },
  { to: '/api-keys', label: 'API Keys', icon: '⚿' },
  { to: '/api-docs', label: 'API Docs', icon: '❯' },
  { to: '/audit', label: 'Audit Log', icon: '≡' },
  { to: '/about', label: 'About', icon: '◇' },
  { to: '/help', label: 'Help', icon: '?' },
]

export default function Layout() {
  const navigate = useNavigate()
  if (!isAuthed()) return <Navigate to="/login" replace />

  /* Transcripts live only in this browser, so logging out is the only moment
     StateJar can clear them — and it must, or a shared machine hands the next
     person the last person's conversation. Memory state is unaffected: it is
     on the server, keyed to the account, and comes back on the next login. */
  const logout = () => {
    clearAll()
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
