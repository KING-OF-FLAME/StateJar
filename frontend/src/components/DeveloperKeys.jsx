import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'

/* Developer API keys. A key is shown exactly once; everything after that is
   lifecycle — when it expires, when it was last used, whether it still
   works. That is the information someone needs when an integration breaks. */

const EXPIRY_OPTIONS = [
  { id: '7d', label: '7 days' },
  { id: '30d', label: '30 days' },
  { id: '365d', label: '1 year' },
  { id: 'never', label: 'Never' },
]

const STATUS_LABEL = {
  active: 'active',
  expiring_soon: 'expiring soon',
  expired: 'expired',
  revoked: 'revoked',
}

export function relativeFuture(iso) {
  if (!iso) return 'never'
  const ms = new Date(iso).getTime() - Date.now()
  if (Number.isNaN(ms)) return '—'
  const days = Math.round(ms / 86400000)
  if (ms <= 0) return `${Math.abs(days) || 0}d ago`
  if (days === 0) return 'today'
  if (days === 1) return 'in 1 day'
  if (days < 45) return `in ${days} days`
  return `in ${Math.round(days / 30)} months`
}

export function relativePast(iso) {
  if (!iso) return 'never'
  const secs = Math.round((Date.now() - new Date(iso).getTime()) / 1000)
  if (Number.isNaN(secs)) return '—'
  if (secs < 60) return 'just now'
  if (secs < 3600) return `${Math.round(secs / 60)}m ago`
  if (secs < 86400) return `${Math.round(secs / 3600)}h ago`
  return `${Math.round(secs / 86400)}d ago`
}

function RevealModal({ created, onClose }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    await navigator.clipboard.writeText(created.api_key)
    setCopied(true)
    setTimeout(() => setCopied(false), 1600)
  }
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="New API key">
      <div className="modal">
        <h3>Copy your key now</h3>
        <p className="modal-warn">
          This is the only time it will ever be shown. StateJar stores just a
          SHA-256 hash — if you lose it, generate a new one.
        </p>
        <div className="key-reveal-row">
          <code className="mono">{created.api_key}</code>
          <button className="btn btn-primary" type="button" onClick={copy}>
            {copied ? 'Copied ✓' : 'Copy'}
          </button>
        </div>
        <p className="modal-meta">
          {created.label ? `${created.label} · ` : ''}
          expires {created.expires_at
            ? `${relativeFuture(created.expires_at)} (${new Date(created.expires_at).toLocaleDateString()})`
            : 'never'}
        </p>
        <button className="btn btn-ghost" type="button" onClick={onClose}>
          I've saved it
        </button>
      </div>
    </div>
  )
}

export default function DeveloperKeys() {
  const [keys, setKeys] = useState(null)
  const [expiry, setExpiry] = useState('30d')
  const [label, setLabel] = useState('')
  const [created, setCreated] = useState(null)
  const [confirming, setConfirming] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = () => api('/apikeys').then(setKeys).catch((e) => {
    setError(e.message)
    setKeys([])
  })
  useEffect(() => { load() }, [])

  const generate = async () => {
    setError('')
    setBusy(true)
    try {
      const out = await api('/apikeys/generate', {
        method: 'POST',
        body: { expires_in: expiry, label: label.trim() || null },
      })
      setCreated(out)
      setLabel('')
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const revoke = async (id) => {
    setError('')
    try {
      await api(`/apikeys/${id}`, { method: 'DELETE' })
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setConfirming(null)
    }
  }

  const copyKey = async (last4) => {
    await navigator.clipboard.writeText(`sj_live_…${last4}`)
  }

  const expiringSoon = (keys || []).filter((k) => k.status === 'expiring_soon')

  return (
    <div className="panel" style={{ maxWidth: 900, marginTop: 22 }}>
      <h3>Developer API</h3>
      <p className="empty-note" style={{ marginTop: 0 }}>
        Call StateJar from your own code with an <span className="mono">X-API-Key</span>{' '}
        header — no browser session needed.
      </p>

      {expiringSoon.length > 0 && (
        <div className="banner-warn" role="status">
          {expiringSoon.length === 1
            ? `1 key expires ${relativeFuture(expiringSoon[0].expires_at)}.`
            : `${expiringSoon.length} keys expire within 7 days.`}{' '}
          Generate a replacement before it lapses.
        </div>
      )}

      <div className="keygen">
        <label className="keygen-field">
          <span>Name <span className="prov-optional">optional</span></span>
          <input
            type="text" value={label} onChange={(e) => setLabel(e.target.value)}
            placeholder="CI pipeline" maxLength={100} aria-label="Key name"
          />
        </label>
        <div className="keygen-field">
          <span>Expires</span>
          <div className="segmented" role="group" aria-label="Key expiry">
            {EXPIRY_OPTIONS.map((option) => (
              <button
                key={option.id} type="button"
                className={expiry === option.id ? 'active' : ''}
                aria-pressed={expiry === option.id}
                onClick={() => setExpiry(option.id)}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
        <button className="btn btn-primary" onClick={generate} disabled={busy}>
          {busy ? 'Generating…' : 'Generate key'}
        </button>
      </div>

      {error && <p className="auth-error">{error}</p>}

      {keys === null ? (
        <p className="empty-note">Loading keys…</p>
      ) : keys.length === 0 ? (
        <div className="keys-empty">
          <p className="empty-note">
            No API keys yet — one key is all it takes to call StateJar from code.
          </p>
          <button className="btn btn-primary" onClick={generate} disabled={busy}>
            Generate your first key
          </button>
        </div>
      ) : (
        <div className="table-scroll">
          <table className="keys-table">
            <thead>
              <tr>
                <th>Name</th><th>Key</th><th>Created</th>
                <th>Expires</th><th>Last used</th><th>Status</th><th />
              </tr>
            </thead>
            <tbody>
              {keys.map((k) => (
                <tr key={k.id} className={k.status === 'revoked' ? 'is-dim' : ''}>
                  <td>{k.label || <span className="empty-note">—</span>}</td>
                  <td>
                    <button
                      type="button" className="mono key-cell"
                      onClick={() => copyKey(k.key_last4)}
                      title="Copy the masked form"
                    >
                      sj_live_…{k.key_last4}
                    </button>
                  </td>
                  <td title={new Date(k.created_at).toLocaleString()}>
                    {relativePast(k.created_at)}
                  </td>
                  <td title={k.expires_at ? new Date(k.expires_at).toLocaleString() : 'no expiry'}>
                    {k.expires_at ? relativeFuture(k.expires_at) : 'never'}
                  </td>
                  <td title={k.last_used_at ? new Date(k.last_used_at).toLocaleString() : 'never used'}>
                    {relativePast(k.last_used_at)}
                  </td>
                  <td>
                    <span className={`status-pill st-${k.status}`}>
                      {STATUS_LABEL[k.status] || k.status}
                    </span>
                  </td>
                  <td className="keys-actions">
                    {k.revoked ? (
                      <span className="empty-note">—</span>
                    ) : confirming === k.id ? (
                      <span className="apikey-confirm">
                        <button className="btn btn-danger" onClick={() => revoke(k.id)}>
                          Revoke
                        </button>
                        <button className="btn btn-ghost" onClick={() => setConfirming(null)}>
                          Cancel
                        </button>
                      </span>
                    ) : (
                      <button className="btn btn-ghost" onClick={() => setConfirming(k.id)}>
                        Revoke
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {created && <RevealModal created={created} onClose={() => setCreated(null)} />}
    </div>
  )
}
