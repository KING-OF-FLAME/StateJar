import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { setToken } from '../lib/api.js'
import { clearAll } from '../lib/transcript.js'

/* The signed-in affordance, shared by the landing header and the public bar.

   Both used to show "Sign in / Sign up free" unconditionally, so clicking the
   logo while signed in landed on a marketing page inviting you to create the
   account you were already using. Auth is knowable synchronously — the token is
   read from localStorage when lib/api is imported — so there is no resolving
   state to guard and no reason for the header to ever render the wrong one. */

/* Transcripts live only in this browser, so signing out is the only moment
   StateJar can clear them, and it must: a shared machine must not hand the next
   person the last person's conversation. Memory state is untouched — it is on
   the server, keyed to the account, and returns on the next sign-in. */
export function signOut() {
  clearAll()
  setToken(null)
}

export default function AccountMenu({ name }) {
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const wrapRef = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    const close = (e) => {
      if (e.key === 'Escape' || !wrapRef.current?.contains(e.target)) setOpen(false)
    }
    document.addEventListener('keydown', close)
    document.addEventListener('pointerdown', close)
    return () => {
      document.removeEventListener('keydown', close)
      document.removeEventListener('pointerdown', close)
    }
  }, [open])

  const logout = () => {
    setOpen(false)
    signOut()
    navigate('/login')
  }

  const initial = (name || '').trim().charAt(0).toUpperCase()

  return (
    <div className="acct" ref={wrapRef}>
      <Link className="btn btn-ghost acct-dash" to="/dashboard">Dashboard</Link>
      <button
        type="button"
        className="acct-trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={name ? `Account menu for ${name}` : 'Account menu'}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="acct-avatar" aria-hidden="true">{initial || '●'}</span>
        <span className="acct-caret" aria-hidden="true">▾</span>
      </button>
      {open && (
        <div className="acct-menu" role="menu">
          {name && <p className="acct-who">{name}</p>}
          <Link role="menuitem" to="/dashboard" onClick={() => setOpen(false)}>Dashboard</Link>
          <Link role="menuitem" to="/profile" onClick={() => setOpen(false)}>Profile</Link>
          <button role="menuitem" type="button" onClick={logout}>Log out</button>
        </div>
      )}
    </div>
  )
}
