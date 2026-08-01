import { useState } from 'react'
import { api } from '../lib/api.js'

/* Provenance timeline. Each node is one audited disclosure; expanding it
   replays the request against the stored state and re-derives the handle,
   so "byte-identical" is a verified claim rather than a label. */

const RING_COUNT = 5

export function relativeTime(iso) {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const secs = Math.max(0, Math.round((Date.now() - then) / 1000))
  if (secs < 45) return 'just now'
  const mins = Math.round(secs / 60)
  if (mins < 60) return `${mins}m ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.round(hours / 24)}d ago`
}

/* Stable colour per handle so a judge can see several answers sharing one
   memory version at a glance. */
function ringFor(handle, order) {
  if (!handle) return 0
  if (!(handle in order)) order[handle] = Object.keys(order).length
  return order[handle] % RING_COUNT
}

function Replay({ entry }) {
  const [open, setOpen] = useState(false)
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const toggle = async () => {
    const next = !open
    setOpen(next)
    if (!next || data || loading) return
    setLoading(true)
    setError('')
    try {
      setData(await api(`/audit/${encodeURIComponent(entry.request_id)}/replay`))
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="tl-replay">
      <button
        type="button" className="tl-replay-toggle" onClick={toggle}
        aria-expanded={open}
      >
        <span className="tl-caret" aria-hidden="true">{open ? '▾' : '▸'}</span> Replay
      </button>

      {open && (
        <div className="tl-replay-body">
          {loading && <p className="empty-note">Reconstructing…</p>}
          {error && <p className="auth-error">{error}</p>}
          {data && (
            <>
              <div className="tl-verify">
                {data.verified ? (
                  <span className="tl-verified">byte-identical ✓</span>
                ) : (
                  <span className="tl-unverified">state changed since logging ✕</span>
                )}
                <span className="tl-verify-note">
                  handle re-derived from the stored state
                  {data.recomputed_handle && (
                    <span className="mono"> · {data.recomputed_handle.slice(0, 18)}…</span>
                  )}
                </span>
              </div>
              <p className="tl-section-label">exact context sent to the model</p>
              <pre className="tl-payload mono">
                {JSON.stringify(data.subset, null, 2)}
              </pre>
            </>
          )}
        </div>
      )}
    </div>
  )
}

export default function AuditTimeline({ entries, scope, onScope, onCopyHandle, highlightId }) {
  const order = {}

  return (
    <>
      <div className="audit-scope" role="group" aria-label="Audit scope">
        <button className={scope === 'session' ? 'active' : ''} onClick={() => onScope('session')}>
          This session
        </button>
        <button className={scope === 'all' ? 'active' : ''} onClick={() => onScope('all')}>
          All sessions
        </button>
      </div>

      {!entries.length ? (
        <p className="empty-note">
          No audited responses yet — run the demo or send a message.
        </p>
      ) : (
        <ol className="tl">
          {entries.map((a) => (
            <li
              key={a.request_id}
              className={`tl-entry${highlightId === a.request_id ? ' is-new' : ''}`}
            >
              <span
                className={`tl-node ring-${ringFor(a.handle_used, order)}`}
                aria-hidden="true"
              />
              <div className="tl-card">
                <div className="tl-card-head">
                  <span className="mono tl-req" title={a.request_id}>
                    {a.request_id.slice(0, 12)}…
                  </span>
                  <span className="tl-when" title={new Date(a.created_at).toLocaleString()}>
                    {relativeTime(a.created_at)}
                  </span>
                </div>

                {a.handle_used && (
                  <button
                    type="button" className="mono tl-handle"
                    onClick={() => onCopyHandle?.(a.handle_used)}
                    title="Click to copy the full handle"
                  >
                    {a.handle_used.slice(0, 26)}… ⧉
                  </button>
                )}

                <div className="pg-chips">
                  {(a.subset_keys || []).map((k) => (
                    <span className="chip mono" key={k}>{k}</span>
                  ))}
                  {!(a.subset_keys || []).length && (
                    <span className="empty-note">nothing disclosed</span>
                  )}
                </div>

                <div className="tl-meta">
                  {scope === 'all' && a.session_tag ? `${a.session_tag} · ` : ''}
                  {a.provider} · {a.model}
                </div>

                <Replay entry={a} />
              </div>
            </li>
          ))}
        </ol>
      )}
    </>
  )
}
