import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api.js'

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1200)
  }
  return (
    <button className="copy-btn" onClick={copy} title="Copy handle">
      {copied ? '✓' : '⧉'}
    </button>
  )
}

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api('/memory/stats').then(setStats).catch((e) => setError(e.message))
  }, [])

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Dashboard</h1>
          <p className="page-sub">Your deterministic memory at a glance.</p>
        </div>
        <Link className="btn btn-primary" to="/playground">Open Playground</Link>
      </div>

      {error && <p className="auth-error">{error}</p>}

      <div className="stat-grid">
        <div className="stat-card">
          <span className="stat-label">Sessions</span>
          <span className="stat-value">{stats ? stats.session_count : '—'}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Memory states</span>
          <span className="stat-value">{stats ? stats.state_count : '—'}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Audit entries</span>
          <span className="stat-value">{stats ? stats.audit_count : '—'}</span>
        </div>
        <div className="stat-card stat-green">
          <span className="stat-label">Tokens saved (last chat)</span>
          <span className="stat-value">
            {stats?.token_saved_pct != null ? `${stats.token_saved_pct}%` : '—'}
          </span>
          <span className="stat-note">minimal disclosure vs full state</span>
        </div>
      </div>

      <div className="panel">
        <h3>Latest handles</h3>
        {stats && stats.latest_handles.length === 0 && (
          <p className="empty-note">
            No memory states yet. <Link to="/playground">Ingest your first conversation →</Link>
          </p>
        )}
        <ul className="handle-list">
          {(stats?.latest_handles || []).map((h) => (
            <li key={h.handle}>
              <span className="mono handle-text">{h.handle}</span>
              <span className="handle-meta">{h.session_tag}</span>
              <CopyButton text={h.handle} />
            </li>
          ))}
        </ul>
      </div>
    </>
  )
}
