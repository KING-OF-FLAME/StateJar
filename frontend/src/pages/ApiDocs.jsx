import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api.js'

/* The quickstart from docs/api.md, in the console so a judge can read it
   without leaving the app. Examples are pre-filled with the reader's own
   base URL, and with a real key's last 4 when they have one. */

// Branded public API. The original Railway host still serves the same
// service and is kept working for existing integrations, but new code
// should be pointed here.
const PUBLIC_API_BASE = 'https://api.statejar.com'

const CURL = {
  ingest: (base, key) => `curl -X POST "${base}/api/v1/memory/ingest" \\
  -H "X-API-Key: ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{
        "session_tag": "user-42",
        "text": "My name is Ayaan, budget under ₹2000. I prefer email."
      }'`,
  query: (base, key) => `curl -X POST "${base}/api/v1/memory/query" \\
  -H "X-API-Key: ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{
        "session_tag": "user-42",
        "query": "What is my budget?",
        "audit": true
      }'`,
  chat: (base, key) => `curl -X POST "${base}/api/v1/chat" \\
  -H "X-API-Key: ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{
        "session_tag": "user-42",
        "query": "Book my delivery with my usual preferences",
        "model": "meta-llama/llama-3.3-70b-instruct:free"
      }'`,
}

const RESPONSES = {
  ingest: `{
  "handle": "shm_18c8fecaf5dacf38deda0914ecdb1b38b40566c1",
  "parent_handle": null,
  "state": {
    "constraints": { "budget_inr_max": 2000 },
    "facts": { "name": "Ayaan" },
    "preferences": { "contact_mode": "email" }
  },
  "extraction_source": "rules"
}`,
  query: `{
  "handle_used": "shm_18c8fecaf5dacf38deda0914ecdb1b38b40566c1",
  "subset": { "constraints": { "budget_inr_max": 2000 } },
  "metadata": {
    "retrieval_mode": "intent_map",
    "subset_keys": ["constraints.budget_inr_max"],
    "fields_dropped": 4,
    "token_estimate_saved_pct": 73.9
  },
  "audit_id": "7272c2ea8d0c44e1"
}`,
  chat: `{
  "response": "Booking with your saved preferences — I'll email the confirmation and keep it under ₹2000.",
  "handle_used": "shm_18c8fecaf5dacf38deda0914ecdb1b38b40566c1",
  "subset_keys": ["preferences.contact_mode", "constraints.budget_inr_max"],
  "audit_id": "4b8e77c1a0d2f3e9"
}`,
}

const ENDPOINTS = [
  ['GET', '/api/v1/usage', 'Requests today, states, audit rows, tokens saved'],
  ['GET', '/api/v1/memory/versions?session_tag=…', 'The handle chain for a session, oldest first'],
  ['GET', '/api/v1/memory/state/{handle}', 'Any state you own, by handle'],
  ['GET', '/api/v1/audit?limit=50', 'What was disclosed, when, to which model'],
  ['GET', '/api/v1/memory/stats', 'Console summary'],
]

function Snippet({ code }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    await navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 1400)
  }
  return (
    <div className="snippet">
      <button className="snippet-copy" type="button" onClick={copy}
        aria-label="Copy code to clipboard">
        {copied ? 'Copied ✓' : 'Copy'}
      </button>
      <pre className="mono"><code>{code}</code></pre>
    </div>
  )
}

function Step({ n, title, children }) {
  return (
    <section className="docs-step">
      <h3><span className="docs-step-n mono">{n}</span> {title}</h3>
      {children}
    </section>
  )
}

export default function ApiDocs() {
  const [hasKey, setHasKey] = useState(null)   // null = still checking
  const [last4, setLast4] = useState(null)

  // What this build actually calls. VITE_API_URL is baked in at build time,
  // so it is the truth for a deployed console; when it is unset (local dev)
  // fall back to the public branded API rather than this page's own origin,
  // so the snippets are always something a reader can paste and run.
  const base = import.meta.env.VITE_API_URL || PUBLIC_API_BASE

  useEffect(() => {
    api('/apikeys')
      .then((keys) => {
        setHasKey(keys.length > 0)
        if (keys.length) setLast4(keys[0].key_last4)
      })
      .catch(() => setHasKey(false)) // docs must render even if the call fails
  }, [])

  const key = last4 ? `sj_live_…${last4}` : 'sj_live_YOUR_KEY'

  return (
    <>
      <div className="page-head">
        <div>
          <h1>API Docs</h1>
          <p className="page-sub">
            Give any application deterministic, auditable memory over HTTP.
          </p>
        </div>
        <Link className="btn btn-primary" to="/api-keys">Manage API keys</Link>
      </div>

      <div className="panel docs-panel">
        <Step n="1" title="Get a key">
          {hasKey === null ? (
            <p className="empty-note">Checking your keys…</p>
          ) : hasKey ? (
            <p className="empty-note">
              You have an active key ending <span className="mono">{last4}</span>. The
              examples below use it — paste your full key in place of{' '}
              <span className="mono">{key}</span>.
            </p>
          ) : (
            <p className="empty-note">
              No keys yet. <Link to="/api-keys">Generate one →</Link> It is shown once
              and stored only as a SHA-256 hash.
            </p>
          )}
          <Snippet code={`export STATEJAR_URL=${base}\nexport STATEJAR_KEY=sj_live_…`} />
        </Step>

        <Step n="2" title="Ingest — turn text into structured state">
          <p className="docs-note">
            The <span className="mono">handle</span> is a content address: identical
            state always produces an identical handle. New information for the same{' '}
            <span className="mono">session_tag</span> mints a new handle whose{' '}
            <span className="mono">parent_handle</span> points at the previous one —
            history is appended, never overwritten.
          </p>
          <Snippet code={CURL.ingest(base, key)} />
          <p className="docs-label">Response</p>
          <Snippet code={RESPONSES.ingest} />
        </Step>

        <Step n="3" title="Query — retrieve the minimum a question needs">
          <p className="docs-note">
            <span className="mono">subset</span> is the only thing you put in a model's
            context — not the transcript, not the whole profile.{' '}
            <span className="mono">audit: true</span> records the disclosure so you can
            prove later exactly what was shared.
          </p>
          <Snippet code={CURL.query(base, key)} />
          <p className="docs-label">Response</p>
          <Snippet code={RESPONSES.query} />
        </Step>

        <Step n="4" title="Chat — let StateJar assemble the context">
          <p className="docs-note">
            Needs a provider key saved on the <Link to="/api-keys">API Keys</Link> page.
            StateJar retrieves the minimal subset, builds the system context, calls the
            model and writes the audit row in one round trip.
          </p>
          <Snippet code={CURL.chat(base, key)} />
          <p className="docs-label">Response</p>
          <Snippet code={RESPONSES.chat} />
        </Step>

        <Step n="5" title="Everything else">
          <div className="table-scroll">
            <table className="docs-table">
              <thead>
                <tr><th>Method</th><th>Path</th><th>Purpose</th></tr>
              </thead>
              <tbody>
                {ENDPOINTS.map(([m, p, why]) => (
                  <tr key={p}>
                    <td className="mono">{m}</td>
                    <td className="mono">{p}</td>
                    <td>{why}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="docs-note">
            An API key authenticates the data plane only. Minting keys, listing them
            and reading your provider key stay console-only, so a leaked key cannot
            mint a successor or spend your provider credit. Rate limit on{' '}
            <span className="mono">/chat</span> is 60/hour per key; over it returns{' '}
            <span className="mono">429</span>. Errors are always{' '}
            <span className="mono">{'{"detail": "…"}'}</span>.
          </p>
          <p className="docs-note">
            Full reference: <span className="mono">docs/api.md</span> in the repo, or the
            interactive schema at <span className="mono">{base}/docs</span>.
          </p>
        </Step>
      </div>
    </>
  )
}
