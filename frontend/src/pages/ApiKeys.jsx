import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import ProviderCards from '../components/ProviderCards.jsx'

/* Developer API keys: generated here, shown once, then only ever by last 4. */
function DeveloperApi() {
  const [keys, setKeys] = useState(null)
  const [fresh, setFresh] = useState(null) // the one-time plaintext
  const [copied, setCopied] = useState(false)
  const [confirming, setConfirming] = useState(null) // id pending revoke
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = () => api('/apikeys').then(setKeys).catch((e) => setError(e.message))
  useEffect(() => { load() }, [])

  const generate = async () => {
    setError('')
    setBusy(true)
    try {
      const created = await api('/apikeys/generate', { method: 'POST' })
      setFresh(created)
      setCopied(false)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const copy = async () => {
    await navigator.clipboard.writeText(fresh.api_key)
    setCopied(true)
    setTimeout(() => setCopied(false), 1600)
  }

  const revoke = async (id) => {
    setError('')
    try {
      await api(`/apikeys/${id}`, { method: 'DELETE' })
      if (fresh?.id === id) setFresh(null)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setConfirming(null)
    }
  }

  return (
    <div className="panel" style={{ maxWidth: 720, marginTop: 22 }}>
      <h3>Developer API</h3>
      <p className="empty-note" style={{ marginTop: 0 }}>
        Call StateJar from your own code with an <span className="mono">X-API-Key</span> header —
        no browser session needed. See <span className="mono">docs/api.md</span> for a quickstart.
      </p>

      {fresh && (
        <div className="key-reveal">
          <div className="key-reveal-head">
            <strong>Copy this key now</strong>
            <span>It is stored only as a hash — this is the one time it is shown.</span>
          </div>
          <div className="key-reveal-row">
            <code className="mono">{fresh.api_key}</code>
            <button className="btn btn-primary" type="button" onClick={copy}>
              {copied ? 'Copied ✓' : 'Copy'}
            </button>
          </div>
        </div>
      )}

      <button className="btn btn-primary" onClick={generate} disabled={busy}>
        {busy ? 'Generating…' : 'Generate new key'}
      </button>
      {error && <p className="auth-error">{error}</p>}

      {keys === null ? (
        <p className="empty-note">Loading keys…</p>
      ) : keys.length === 0 ? (
        <p className="empty-note">No API keys yet. Generate one to call StateJar from code.</p>
      ) : (
        <ul className="apikey-list">
          {keys.map((k) => (
            <li key={k.id}>
              <span className="mono">sj_live_••••••••{k.key_last4}</span>
              <span className="handle-meta">
                created {new Date(k.created_at).toLocaleDateString()}
              </span>
              {confirming === k.id ? (
                <span className="apikey-confirm">
                  <button className="btn btn-danger" onClick={() => revoke(k.id)}>
                    Revoke for good
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
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function ApiKeys() {
  return (
    <>
      <div className="page-head">
        <div>
          <h1>API Keys</h1>
          <p className="page-sub">
            Two kinds of key: the provider keys StateJar uses on your behalf, and the
            StateJar keys your own code uses to call this API.
          </p>
        </div>
      </div>

      <ProviderCards />

      <DeveloperApi />
    </>
  )
}
