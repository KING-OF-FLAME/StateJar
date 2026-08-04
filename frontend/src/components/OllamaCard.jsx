import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import {
  DEFAULT_OLLAMA_URL, normaliseBase, originsFix, testConnection,
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

function TestResult({ result, showOriginsFix }) {
  if (!result) return null
  if (result.ok) {
    return (
      <p className="prov-ok">
        Connected — {result.count} model{result.count === 1 ? '' : 's'} available.
      </p>
    )
  }
  return (
    <div className="ollama-fix">
      <p className="auth-error" style={{ marginBottom: 8 }}>{result.message}</p>
      {showOriginsFix && result.kind === 'cors' && (
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
  )
}

/* Shared form plumbing. The two cards differ in what they promise, not in
   how they save. */
function useCardState(defaultUrl, saved) {
  const [baseUrl, setBaseUrl] = useState(defaultUrl)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  useEffect(() => {
    setBaseUrl(saved?.config?.base_url || defaultUrl)
  }, [saved, defaultUrl])

  const run = async (fn) => {
    setError('')
    setBusy(true)
    try {
      await fn()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  return { baseUrl, setBaseUrl, busy, error, setError, result, setResult, run }
}

/* --- Card A: the daemon on this machine ----------------------------------
 *
 * One card used to cover both of these, with an optional key field deciding
 * which was in force. That made the privacy promise unreadable: a user could
 * not tell whether their prompt was staying on their machine or being sent
 * through our backend. They are now two cards over two provider rows, so each
 * states one thing and configuring one cannot disturb the other.
 */
export function OllamaLocalCard({ saved, onChanged }) {
  const s = useCardState(DEFAULT_OLLAMA_URL, saved)

  const save = (e) => {
    e?.preventDefault()
    s.setResult(null)
    return s.run(async () => {
      await api('/keys/provider', {
        method: 'POST',
        body: {
          provider: 'ollama',
          // base URL only — a local daemon has no credential to hold, and
          // offering a key field here is what blurred the two cards together
          api_key: JSON.stringify({ base_url: normaliseBase(s.baseUrl) }),
        },
      })
      await onChanged()
    })
  }

  const remove = () => {
    s.setResult(null)
    return s.run(async () => {
      await api('/keys/provider/ollama', { method: 'DELETE' })
      s.setBaseUrl(DEFAULT_OLLAMA_URL)
      await onChanged()
    })
  }

  /* Tested from the browser, because that is exactly how it will be used —
     a backend probe would prove nothing about reachability from here. */
  const test = () => s.run(async () => {
    s.setResult(await testConnection(s.baseUrl))
  })

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

      <span className="prov-mode mode-direct">Local · browser-direct</span>

      <form onSubmit={save} className="prov-form">
        <label className="prov-label">
          Base URL
          <input
            type="text" className="mono" value={s.baseUrl}
            onChange={(e) => s.setBaseUrl(e.target.value)}
            placeholder={DEFAULT_OLLAMA_URL}
            aria-label="Local Ollama base URL"
          />
        </label>
        <div className="prov-actions">
          <button className="btn btn-primary" disabled={s.busy}>
            {s.busy ? '…' : 'Save'}
          </button>
          <button type="button" className="btn btn-ghost" onClick={test} disabled={s.busy}>
            Test connection
          </button>
          {saved && (
            <button type="button" className="btn btn-ghost" onClick={remove} disabled={s.busy}>
              Reset
            </button>
          )}
        </div>
      </form>

      <TestResult result={s.result} showOriginsFix />
      {s.error && <p className="auth-error">{s.error}</p>}

      <p className="prov-help">
        Install models with <span className="mono">ollama pull llama3.2</span>.
      </p>
    </div>
  )
}

/* --- Card B: a host we call on the user's behalf -------------------------- */

export function OllamaRemoteCard({ saved, onChanged }) {
  const s = useCardState('', saved)
  const [apiKey, setApiKey] = useState('')

  const save = (e) => {
    e?.preventDefault()
    s.setResult(null)
    if (!normaliseBase(s.baseUrl).startsWith('http')) {
      s.setError('Enter the base URL of your remote or cloud Ollama host.')
      return undefined
    }
    if (!apiKey.trim() && !saved?.has_key) {
      s.setError('A remote host needs an API key.')
      return undefined
    }
    return s.run(async () => {
      await api('/keys/provider', {
        method: 'POST',
        body: {
          provider: 'ollama_remote',
          api_key: JSON.stringify({
            base_url: normaliseBase(s.baseUrl),
            ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
          }),
        },
      })
      setApiKey('')
      await onChanged()
    })
  }

  const remove = () => {
    s.setResult(null)
    return s.run(async () => {
      await api('/keys/provider/ollama_remote', { method: 'DELETE' })
      s.setBaseUrl('')
      setApiKey('')
      await onChanged()
    })
  }

  /* Tested by the backend, because that is who will make the real call. */
  const test = () => s.run(async () => {
    try {
      const out = await api('/keys/provider/ollama_remote/test', { method: 'POST' })
      s.setResult(out.ok
        ? { ok: true, count: out.model_count }
        : { ok: false, kind: 'error', message: out.error })
    } catch (err) {
      s.setResult({ ok: false, kind: 'error', message: err.message })
    }
  })

  return (
    <div className="prov-card prov-ollama" data-provider="ollama_remote">
      <div className="prov-head">
        <h4>Ollama (remote / cloud)</h4>
        <span className="badge-remote">REMOTE</span>
        {saved && <span className="key-badge">saved ✓</span>}
      </div>

      <p className="prov-explainer">
        For Ollama Cloud or a self-hosted remote daemon. Calls are routed
        through StateJar&apos;s server, so your key is stored encrypted and your
        prompts transit our backend.
      </p>

      <span className="prov-mode mode-server">Remote · via StateJar server</span>

      <form onSubmit={save} className="prov-form">
        <label className="prov-label">
          Base URL
          <input
            type="text" className="mono" value={s.baseUrl}
            onChange={(e) => s.setBaseUrl(e.target.value)}
            placeholder="https://your-ollama-host.example.com"
            aria-label="Remote Ollama base URL"
          />
        </label>
        <label className="prov-label">
          API key <span className="prov-optional">required</span>
          <input
            type="password" className="mono" value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={saved?.has_key ? '•••••• saved' : 'your Ollama Cloud key'}
            autoComplete="off" aria-label="Remote Ollama API key"
          />
        </label>
        <div className="prov-actions">
          <button className="btn btn-primary" disabled={s.busy}>
            {s.busy ? '…' : 'Save'}
          </button>
          <button type="button" className="btn btn-ghost" onClick={test} disabled={s.busy}>
            Test connection
          </button>
          {saved && (
            <button type="button" className="btn btn-ghost" onClick={remove} disabled={s.busy}>
              Reset
            </button>
          )}
        </div>
      </form>

      <TestResult result={s.result} />
      {s.error && <p className="auth-error">{s.error}</p>}
    </div>
  )
}

export default OllamaLocalCard
