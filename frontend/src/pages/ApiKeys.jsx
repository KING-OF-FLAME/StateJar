import { useState } from 'react'
import { api } from '../lib/api.js'

export default function ApiKeys() {
  const [apiKey, setApiKey] = useState('')
  const [saved, setSaved] = useState(null) // {provider, key_last4}
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const save = async (e) => {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      const result = await api('/keys/provider', {
        method: 'POST',
        body: { provider: 'openrouter', api_key: apiKey },
      })
      setSaved(result)
      setApiKey('') // never keep the raw key around
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>API Keys</h1>
          <p className="page-sub">
            Bring your own provider key. Encrypted at rest with AES-256-GCM — never shown again after saving.
          </p>
        </div>
      </div>

      <div className="panel" style={{ maxWidth: 560 }}>
        <h3>OpenRouter</h3>
        {saved ? (
          <div className="key-saved">
            <span className="mono">sk-or-••••••••••••{saved.key_last4}</span>
            <span className="key-badge">saved ✓</span>
            <button className="btn btn-ghost" style={{ padding: '6px 14px', fontSize: '0.82rem' }}
              onClick={() => setSaved(null)}>
              Replace key
            </button>
          </div>
        ) : (
          <form onSubmit={save}>
            <label>
              API key
              <input
                type="password" required minLength={8} value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="sk-or-v1-…" className="mono" autoComplete="off"
              />
            </label>
            {error && <p className="auth-error">{error}</p>}
            <button className="btn btn-primary" disabled={busy}>
              {busy ? 'Encrypting…' : 'Save key'}
            </button>
          </form>
        )}
        <p className="empty-note" style={{ marginTop: 18 }}>
          Get a key at <span className="mono">openrouter.ai/keys</span>. Other providers
          (OpenAI, Anthropic, Gemini, Ollama) arrive in a later round.
        </p>
      </div>
    </>
  )
}
