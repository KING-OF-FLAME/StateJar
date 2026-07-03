import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, setToken } from '../lib/api.js'

function AuthCard({ mode }) {
  const isSignup = mode === 'signup'
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      if (isSignup) {
        await api('/auth/signup', { method: 'POST', body: { email, password } })
      }
      const { access_token } = await api('/auth/login', {
        method: 'POST',
        body: { email, password },
      })
      setToken(access_token)
      navigate('/dashboard')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <Link className="brand" to="/">State<span className="jar">Jar</span></Link>
        <h2>{isSignup ? 'Create your account' : 'Welcome back'}</h2>
        <p className="auth-sub">
          {isSignup ? 'Deterministic memory starts here.' : 'Sign in to your memory dashboard.'}
        </p>
        <form onSubmit={submit}>
          <label>
            Email
            <input
              type="email" required value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com" autoComplete="email"
            />
          </label>
          <label>
            Password
            <input
              type="password" required minLength={8} value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={isSignup ? 'At least 8 characters' : '••••••••'}
              autoComplete={isSignup ? 'new-password' : 'current-password'}
            />
          </label>
          {error && <p className="auth-error">{error}</p>}
          <button className="btn btn-primary" disabled={busy} style={{ width: '100%' }}>
            {busy ? '…' : isSignup ? 'Sign up' : 'Log in'}
          </button>
        </form>
        <p className="auth-alt">
          {isSignup ? (
            <>Already have an account? <Link to="/login">Log in</Link></>
          ) : (
            <>New to StateJar? <Link to="/signup">Create an account</Link></>
          )}
        </p>
      </div>
    </div>
  )
}

export function Login() {
  return <AuthCard mode="login" />
}

export function Signup() {
  return <AuthCard mode="signup" />
}
