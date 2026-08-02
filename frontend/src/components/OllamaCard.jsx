import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import {
  DEFAULT_OLLAMA_URL, modeFor, normaliseBase, originsFix, testConnection,
} from '../lib/ollama.js'

function CopyLine({ label, command }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    await navigator.clipboard.writeText(command)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }
  return (
    <div className="fix-line">
      <span className="fix-os">{label}</span>
      <code className="mono">{command}</code>
      <button type="button" className="fix-copy" onClick={copy}>
        {copied ? 'Copied ✓' : 'Copy'}
      </button>
    </div>
  )
}

/* Ollama is the one provider whose endpoint may live on the user's own
   machine, where our backend can never reach it. Two modes, labelled so the
   user can see which one is in play. */
export default function OllamaCard({ saved, onChanged }) {
  const [baseUrl, setBaseUrl] = useState(DEFAULT_OLLAMA_URL)
  const [apiKey, setApiKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  useEffect(() => {
    if (!saved?.config) return
    setBaseUrl(saved.config.base_url || DEFAULT_OLLAMA_URL)
  }, [saved])

  const mode = modeFor({ baseUrl, apiKey: apiKey || saved?.has_key })
  const isDirect = mode === 'browser-direct'

  const save = async (e) => {
    e?.preventDefault()
    setError('')
    setResult(null)
    setBusy(true)
    try {
      await api('/keys/provider', {
        method: 'POST',
        body: {
          provider: 'ollama',
          // one row, two values — the provider parses this back out
          api_key: JSON.stringify({
            base_url: normaliseBase(baseUrl),
            ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
          }),
        },
      })
      setApiKey('')
      await onChanged()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    setError('')
    setResult(null)
    setBusy(true)
    try {
      await api('/keys/provider/ollama', { method: 'DELETE' })
      setBaseUrl(DEFAULT_OLLAMA_URL)
      setApiKey('')
      await onChanged()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  /* Local endpoints are tested from the browser, because that is exactly how
     they will be used; a remote one is tested by the backend, for the same
     reason. */
  const test = async () => {
    setError('')
    setBusy(true)
    try {
      if (isDirect) {
        setResult(await testConnection(baseUrl))
      } else {
        const out = await api('/keys/provider/ollama/test', { method: 'POST' })
        setResult(out.ok
          ? { ok: true, count: out.model_count }
          : { ok: false, kind: 'error', message: out.error })
      }
    } catch (err) {
      setResult({ ok: false, kind: 'error', message: err.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="prov-card prov-ollama" data-provider="ollama">
      <div className="prov-head">
        <h4>Ollama (local)</h4>
        <span className="badge-offline">LOCAL</span>
        {saved && <span className="key-badge">saved ✓</span>}
      </div>

      <p className="prov-explainer">
        Runs on your machine. Your prompts never leave your computer —
        StateJar only supplies the minimal memory subset.
      </p>

      <span className={`prov-mode mode-${isDirect ? 'direct' : 'server'}`}>
        {isDirect ? 'Local · browser-direct' : 'Remote · server-side'}
      </span>

      <form onSubmit={save} className="prov-form">
        <label className="prov-label">
          Base URL
          <input
            type="text" className="mono" value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder={DEFAULT_OLLAMA_URL}
            aria-label="Ollama base URL"
          />
        </label>
        <label className="prov-label">
          API key <span className="prov-optional">optional — for Ollama Cloud or a remote host</span>
          <input
            type="password" className="mono" value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={saved?.has_key ? '•••••• saved' : 'leave blank for a local daemon'}
            autoComplete="off" aria-label="Ollama API key"
          />
        </label>
        <div className="prov-actions">
          <button className="btn btn-primary" disabled={busy}>
            {busy ? '…' : 'Save'}
          </button>
          <button type="button" className="btn btn-ghost" onClick={test} disabled={busy}>
            Test connection
          </button>
          {saved && (
            <button type="button" className="btn btn-ghost" onClick={remove} disabled={busy}>
              Reset
            </button>
          )}
        </div>
      </form>

      {result?.ok && (
        <p className="prov-ok">
          Connected — {result.count} model{result.count === 1 ? '' : 's'} installed.
        </p>
      )}

      {result && !result.ok && (
        <div className="ollama-fix">
          <p className="auth-error" style={{ marginBottom: 8 }}>{result.message}</p>
          {result.kind === 'cors' && (
            <>
              <p className="fix-title">
                Ollama blocks browser requests by default. Restart it so this page is allowed:
              </p>
              <CopyLine label="macOS / Linux" command={originsFix.unix} />
              <CopyLine label="Windows (cmd)" command={originsFix.windows} />
              <CopyLine label="PowerShell" command={originsFix.powershell} />
            </>
          )}
        </div>
      )}

      {error && <p className="auth-error">{error}</p>}

      <p className="prov-help">
        No key needed for a local daemon — install models with{' '}
        <span className="mono">ollama pull llama3.2</span>. A key routes the call
        through StateJar's server instead, for Ollama Cloud or a remote host.
      </p>
    </div>
  )
}
