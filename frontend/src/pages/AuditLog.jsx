import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api.js'

/* Patent module 10 — auditable replay. Every disclosure is recorded with the
   exact handle and the exact fields that reached the model. */
export default function AuditLog() {
  const [entries, setEntries] = useState(null) // null = loading
  const [error, setError] = useState('')

  useEffect(() => {
    api('/audit?limit=100')
      .then((data) => setEntries(data.entries || []))
      .catch((e) => {
        setError(e.message)
        setEntries([])
      })
  }, [])

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Audit Log</h1>
          <p className="page-sub">
            Every response, replayable — which handle was used and exactly which
            fields were disclosed.
          </p>
        </div>
        <Link className="btn btn-ghost" to="/playground">Open Playground</Link>
      </div>

      {error && <p className="auth-error">{error}</p>}

      <div className="panel">
        {entries === null ? (
          <p className="empty-note">Loading audit trail…</p>
        ) : entries.length === 0 ? (
          <p className="empty-note">
            No disclosures recorded yet. Every query and chat writes one row here —{' '}
            <Link to="/playground">send a message →</Link>
          </p>
        ) : (
          <>
            <p className="empty-note" style={{ marginTop: 0 }}>
              {entries.length} most recent {entries.length === 1 ? 'entry' : 'entries'},
              newest first.
            </p>
            <div className="audit-list">
              {entries.map((a) => (
                <div className="audit-row" key={a.request_id}>
                  <div className="mono audit-id" title={a.request_id}>
                    {a.request_id.slice(0, 12)}…
                  </div>
                  <div className="mono audit-handle" title={a.handle_used || ''}>
                    {a.handle_used ? `${a.handle_used.slice(0, 22)}…` : '—'}
                  </div>
                  <div className="pg-chips">
                    {(a.subset_keys || []).map((k) => (
                      <span className="chip mono" key={k}>{k}</span>
                    ))}
                    {(a.subset_keys || []).length === 0 && (
                      <span className="empty-note">nothing disclosed</span>
                    )}
                  </div>
                  <div className="audit-meta">
                    {a.session_tag ? `${a.session_tag} · ` : ''}
                    {a.provider} · {a.model} ·{' '}
                    {new Date(a.created_at).toLocaleString()}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </>
  )
}
