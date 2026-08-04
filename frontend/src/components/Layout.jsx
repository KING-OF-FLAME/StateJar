import { Link, NavLink, Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'
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

/* Pages a visitor can read before deciding to sign up.

   They are reference material, not account data: About explains what StateJar
   is, the API reference explains how to call it, and Help explains every
   control in it. Putting the answer to "what is this and how do I use it"
   behind a login means only people who already committed can read it.

   Each keeps one URL. An authed user gets them inside the console with the
   sidebar; a visitor gets the same page inside a public bar. Anything not on
   this list still redirects to /login. */
const PUBLIC_PATHS = new Set(['/about', '/api-docs', '/help'])

function PublicBar() {
  return (
    <header className="pub-bar">
      <div className="pub-bar-inner">
        <Link className="brand" to="/">
          <img className="brand-logo" src="/logo-mark.png" width="21" height="25"
               alt="StateJar logo" />
          State<span className="jar">Jar</span>
        </Link>
        <nav className="pub-nav" aria-label="Public pages">
          <NavLink to="/about" className={({ isActive }) => (isActive ? 'active' : '')}>About</NavLink>
          <NavLink to="/api-docs" className={({ isActive }) => (isActive ? 'active' : '')}>API Docs</NavLink>
          <NavLink to="/help" className={({ isActive }) => (isActive ? 'active' : '')}>Help</NavLink>
        </nav>
        <div className="pub-ctas">
          <Link className="btn btn-ghost pub-cta" to="/login">Sign in</Link>
          <Link className="btn btn-primary pub-cta" to="/signup">Sign up free</Link>
        </div>
      </div>
    </header>
  )
}

export default function Layout() {
  const navigate = useNavigate()
  const { pathname } = useLocation()

  if (!isAuthed()) {
    if (!PUBLIC_PATHS.has(pathname)) return <Navigate to="/login" replace />
    return (
      <div className="pub-shell">
        <PublicBar />
        <main className="pub-main">
          <Outlet />
        </main>
        <footer className="pub-foot">
          <p>
            <Link to="/signup">Create a free account</Link> to try the
            Playground — the memory pipeline runs without a provider key.
          </p>
          <p className="mono">Indian Patent 202621017626</p>
        </footer>
      </div>
    )
  }

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
        {/* signed in, the brand goes to your console, not to the page
            inviting you to create the account you are already using */}
        <Link className="brand" to="/dashboard">State<span className="jar">Jar</span></Link>
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
