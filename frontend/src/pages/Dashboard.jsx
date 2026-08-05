import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api.js'
import {
  DeclineChart, LineageChart, NamespaceChart, hasInsight,
} from '../components/Charts.jsx'

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
  const [usage, setUsage] = useState(null)
  const [insight, setInsight] = useState(null)
  const [error, setError] = useState('')
  /* undefined = still asking, '' = asked and there is no name to show.
     The distinction matters: rendering the fallback copy while the request is
     still out, then swapping in a name, is the flash this avoids. The heading
     holds the generic line until the answer is known either way. */
  const [name, setName] = useState(undefined)

  useEffect(() => {
    api('/memory/stats').then(setStats).catch((e) => setError(e.message))
    api('/usage').then(setUsage).catch(() => {}) // secondary panel: never blocks the page
    // Charts are additive: if this fails the page is the page it was before.
    // Nothing here renders a placeholder — a chart with invented data on a
    // product about not guessing would be the worst thing on the page.
    api('/memory/insights').then(setInsight).catch(() => {})
    // Never blocks the page either: an empty profile and a failed request are
    // the same thing to a heading, and neither is worth an error banner.
    api('/profile')
      .then((p) => setName((p?.display_name || '').trim()))
      .catch(() => setName(''))
  }, [])

  const num = (v) => (v == null ? '—' : v.toLocaleString())

  return (
    <>
      <div className="page-head">
        <div>
          {/* Three states, not two. Rendering the fallback while the request
              is still out and then swapping in a name is a visible flash --
              measured on first paint, the heading went "Dashboard" then
              "Welcome back, ...". So while the answer is unknown the heading
              holds its space and says nothing; it commits once, to whichever
              is true. The rest of the page never waits on it. */}
          {name === undefined
            ? <h1 className="dash-h1-pending" aria-hidden="true">&nbsp;</h1>
            : <h1>{name ? `Welcome back, ${name}` : 'Dashboard'}</h1>}
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

      {/* Rendered only once there is something real to draw. Each chart also
          returns null on its own empty series, so a user with states but no
          declines gets two charts rather than one padded with zeros. */}
      {hasInsight(insight) && (
        <>
          <div className="chart-grid chart-grid-2">
            <NamespaceChart data={insight.namespaces} />
            <DeclineChart declines={insight.declines} />
          </div>
          <div className="chart-grid">
            <LineageChart lineage={insight.lineage} />
          </div>
        </>
      )}

      <div className="page-head" style={{ marginBottom: 14 }}>
        <div>
          <h3 style={{ fontSize: '1.15rem' }}>Developer API usage</h3>
          <p className="page-sub">
            Same numbers your <span className="mono">X-API-Key</span> integrations see at{' '}
            <span className="mono">GET /api/v1/usage</span>.
          </p>
        </div>
        <Link className="btn btn-ghost" to="/api-keys">Manage API keys</Link>
      </div>

      <div className="stat-grid">
        <div className="stat-card">
          <span className="stat-label">Requests today</span>
          <span className="stat-value">{num(usage?.requests_today)}</span>
          <span className="stat-note">audited disclosures since 00:00 UTC</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Total states</span>
          <span className="stat-value">{num(usage?.total_states)}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Audit rows</span>
          <span className="stat-value">{num(usage?.total_audit_rows)}</span>
        </div>
        <div className="stat-card stat-green">
          <span className="stat-label">Est. tokens saved</span>
          <span className="stat-value">{num(usage?.est_tokens_saved)}</span>
          <span className="stat-note">summed across every disclosure</span>
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
