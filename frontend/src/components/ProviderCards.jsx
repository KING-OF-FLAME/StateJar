import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'

/* One card per provider. Keys are write-only: once saved the console only
   ever sees the last four characters, so "Replace" is a fresh save rather
   than an edit of something we could read back. */

export const PROVIDERS = [
  {
    id: 'openrouter',
    label: 'OpenRouter',
    placeholder: 'sk-or-v1-…',
    help: 'One key, hundreds of models including free ones — openrouter.ai/keys',
  },
  {
    id: 'openai',
    label: 'OpenAI',
    placeholder: 'sk-…',
    help: 'GPT and o-series — platform.openai.com/api-keys',
  },
  {
    id: 'anthropic',
    label: 'Anthropic',
    placeholder: 'sk-ant-…',
    help: 'Claude models — console.anthropic.com/settings/keys',
  },
  {
    id: 'gemini',
    label: 'Gemini',
    placeholder: 'AIza…',
    help: 'Google AI Studio — aistudio.google.com/apikey',
  },
  {
    id: 'ollama',
    label: 'Ollama',
    local: true,
    placeholder: 'http://localhost:11434',
    help: 'Runs on your own machine — no key, no egress. Start it with `ollama serve`.',
  },
]

const DEFAULT_OLLAMA_URL = 'http://localhost:11434'

function ProviderCard({ provider, saved, onChanged }) {
  const [value, setValue] = useState(provider.local ? DEFAULT_OLLAMA_URL : '')
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [tested, setTested] = useState(null) // {ok, model_count|error}

  const showForm = provider.local || !saved || editing

  const save = async (e) => {
    e?.preventDefault()
    setError('')
    setTested(null)
    setBusy(true)
    try {
      await api('/keys/provider', {
        method: 'POST',
        body: { provider: provider.id, api_key: value.trim() },
      })
      if (!provider.local) setValue('')   // never keep the raw key around
      setEditing(false)
      await onChanged()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    setError('')
    setTested(null)
    setBusy(true)
    try {
      await api(`/keys/provider/${provider.id}`, { method: 'DELETE' })
      setValue(provider.local ? DEFAULT_OLLAMA_URL : '')
      setEditing(false)
      await onChanged()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const test = async () => {
    setError('')
    setBusy(true)
    try {
      setTested(await api(`/keys/provider/${provider.id}/test`, { method: 'POST' }))
    } catch (err) {
      setTested({ ok: false, error: err.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="prov-card" data-provider={provider.id}>
      <div className="prov-head">
        <h4>{provider.label}</h4>
        {saved && <span className="key-badge">saved ✓</span>}
        {provider.local && <span className="badge-offline">LOCAL</span>}
      </div>

      {saved && !editing && (
        <div className="prov-saved">
          <span className="mono">
            {provider.local ? `…${saved.key_last4}` : `sk-••••••••${saved.key_last4}`}
          </span>
        </div>
      )}

      {showForm && (
        <form onSubmit={save} className="prov-form">
          <input
            type={provider.local ? 'text' : 'password'}
            className="mono"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={provider.placeholder}
            autoComplete="off"
            aria-label={provider.local ? `${provider.label} base URL` : `${provider.label} API key`}
          />
          <div className="prov-actions">
            <button className="btn btn-primary" disabled={busy || !value.trim()}>
              {busy ? '…' : provider.local ? 'Save URL' : 'Save'}
            </button>
            {provider.local && (
              <button type="button" className="btn btn-ghost" onClick={test} disabled={busy}>
                Test connection
              </button>
            )}
            {editing && (
              <button type="button" className="btn btn-ghost" onClick={() => setEditing(false)}>
                Cancel
              </button>
            )}
          </div>
        </form>
      )}

      {saved && !editing && !provider.local && (
        <div className="prov-actions">
          <button className="btn btn-ghost" onClick={() => setEditing(true)} disabled={busy}>
            Replace
          </button>
          <button className="btn btn-ghost" onClick={test} disabled={busy}>
            Test
          </button>
          <button className="btn btn-danger" onClick={remove} disabled={busy}>
            Remove
          </button>
        </div>
      )}

      {saved && provider.local && (
        <div className="prov-actions">
          <button className="btn btn-ghost" onClick={remove} disabled={busy}>
            Reset to default
          </button>
        </div>
      )}

      {tested && (
        <p className={tested.ok ? 'prov-ok' : 'auth-error'}>
          {tested.ok
            ? `Connected — ${tested.model_count} model${tested.model_count === 1 ? '' : 's'} available.`
            : tested.error}
        </p>
      )}
      {error && <p className="auth-error">{error}</p>}
      <p className="prov-help">{provider.help}</p>
    </div>
  )
}

export default function ProviderCards() {
  const [saved, setSaved] = useState(null) // {provider: {key_last4, created_at}}
  const [error, setError] = useState('')

  const load = async () => {
    try {
      const keys = await api('/keys/provider')
      setSaved(Object.fromEntries(keys.map((k) => [k.provider, k])))
    } catch (err) {
      setError(err.message)
      setSaved({})
    }
  }

  useEffect(() => { load() }, [])

  return (
    <div className="panel" style={{ maxWidth: 820 }}>
      <h3>Providers</h3>
      <p className="empty-note" style={{ marginTop: 0 }}>
        Bring your own key for any of these. Each is encrypted at rest with
        AES-256-GCM and never shown again after saving — StateJar stores the
        credential, never your conversations.
      </p>
      {error && <p className="auth-error">{error}</p>}

      {saved === null ? (
        <p className="empty-note">Checking for saved keys…</p>
      ) : (
        <div className="prov-grid">
          {PROVIDERS.map((p) => (
            <ProviderCard
              key={p.id}
              provider={p}
              saved={saved[p.id] || null}
              onChanged={load}
            />
          ))}
        </div>
      )}
    </div>
  )
}
