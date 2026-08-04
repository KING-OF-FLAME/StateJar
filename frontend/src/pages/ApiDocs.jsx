import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, isAuthed } from '../lib/api.js'
import {
  CONCEPTS, ENDPOINTS, ERROR_CODES, RATE_LIMITS,
} from '../components/docs/endpoints.js'
import { LANGUAGES, SDK_SNIPPET, snippetFor } from '../components/docs/snippets.js'

/* Self-contained reference: everything a developer needs is on this page,
   with no hop to a file on GitHub. The language choice is one piece of state
   for the whole document, so picking Python once switches every example. */

const PUBLIC_API_BASE = 'https://api.statejar.com'

const SECTIONS = [
  ['introduction', 'Introduction'],
  ['authentication', 'Authentication'],
  ['quickstart', 'Quickstart'],
  ['endpoints', 'Endpoints'],
  ['concepts', 'Concepts'],
  ['errors', 'Errors'],
  ['rate-limits', 'Rate limits'],
  ['sdk', 'SDK snippet'],
]

function CodeBlock({ code, label }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    await navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }
  return (
    <div className="snippet">
      <button type="button" className="snippet-copy" onClick={copy}
        aria-label={`Copy ${label || 'code'}`}>
        {copied ? 'Copied ✓' : 'Copy'}
      </button>
      <pre className="mono"><code>{code}</code></pre>
    </div>
  )
}

function LangTabs({ value, onChange }) {
  return (
    <div className="lang-tabs" role="tablist" aria-label="Example language">
      {LANGUAGES.map((lang) => (
        <button
          key={lang.id} role="tab" type="button"
          aria-selected={value === lang.id}
          className={value === lang.id ? 'active' : ''}
          onClick={() => onChange(lang.id)}
        >
          {lang.label}
        </button>
      ))}
    </div>
  )
}

function SchemaTable({ caption, rows, withRequired }) {
  if (!rows.length) return <p className="docs-note">No parameters.</p>
  return (
    <div className="table-scroll">
      <table className="docs-table">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            <th>Field</th><th>Type</th>
            {withRequired && <th>Required</th>}
            <th>Description</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row[0]}>
              <td className="mono">{row[0]}</td>
              <td className="mono docs-type">{row[1]}</td>
              {withRequired && (
                <td>{row[2] ? <span className="req-yes">yes</span> : <span className="req-no">no</span>}</td>
              )}
              <td>{withRequired ? row[3] : row[2]}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function EndpointCard({ endpoint, base, apiKey, language, onLanguage }) {
  const spec = {
    base, key: apiKey, method: endpoint.method,
    path: endpoint.path, body: endpoint.body,
  }
  return (
    <article className="ep-card" id={`ep-${endpoint.id}`}>
      <header className="ep-head">
        <span className={`ep-pill ep-${endpoint.method.toLowerCase()}`}>{endpoint.method}</span>
        <code className="mono ep-path">{endpoint.path}</code>
      </header>
      <p className="docs-note">{endpoint.description}</p>

      <p className="docs-label">Request</p>
      <SchemaTable caption={`${endpoint.title} request`} rows={endpoint.request} withRequired />

      <p className="docs-label">Response</p>
      <SchemaTable caption={`${endpoint.title} response`} rows={endpoint.response} />

      <p className="docs-label">Example request</p>
      <LangTabs value={language} onChange={onLanguage} />
      <CodeBlock code={snippetFor(language, spec)} label={`${endpoint.title} request`} />

      <p className="docs-label">Example response</p>
      <CodeBlock code={JSON.stringify(endpoint.example, null, 2)} label={`${endpoint.title} response`} />
    </article>
  )
}

export default function ApiDocs() {
  const [language, setLanguage] = useState(
    () => localStorage.getItem('statejar_docs_lang') || 'curl')
  const [keyInfo, setKeyInfo] = useState(null)   // null = loading
  const [active, setActive] = useState('introduction')
  const [navOpen, setNavOpen] = useState(false)

  const base = import.meta.env.VITE_API_URL || PUBLIC_API_BASE
  const apiKey = keyInfo?.key_last4 ? `sj_live_…${keyInfo.key_last4}` : 'sj_live_YOUR_KEY'

  const pickLanguage = (id) => {
    setLanguage(id)
    localStorage.setItem('statejar_docs_lang', id)
  }

  /* Docs must render without a session — a visitor reads these before signing
     up. The guard is not decoration: `api()` turns any 401 into a redirect to
     /login, so calling this logged out would bounce the reader off the page
     they came to read, and the catch below would never run. */
  useEffect(() => {
    if (!isAuthed()) {
      setKeyInfo(false)
      return
    }
    api('/apikeys')
      .then((keys) => setKeyInfo(keys.find((k) => k.status === 'active') || false))
      .catch(() => setKeyInfo(false))
  }, [])

  // highlight the section currently in view
  useEffect(() => {
    const headings = SECTIONS
      .map(([id]) => document.getElementById(id))
      .filter(Boolean)
    if (!headings.length) return
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting)
        if (visible.length) setActive(visible[0].target.id)
      },
      { rootMargin: '-80px 0px -70% 0px' },
    )
    headings.forEach((h) => observer.observe(h))
    return () => observer.disconnect()
  }, [keyInfo])

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

      <div className="docs-layout">
        <nav className={`docs-nav${navOpen ? ' open' : ''}`} aria-label="Documentation sections">
          <button
            type="button" className="docs-nav-toggle"
            onClick={() => setNavOpen((v) => !v)}
            aria-expanded={navOpen}
          >
            {SECTIONS.find(([id]) => id === active)?.[1] || 'Contents'}
            <span aria-hidden="true">▾</span>
          </button>
          <ul>
            {SECTIONS.map(([id, label]) => (
              <li key={id}>
                <a
                  href={`#${id}`}
                  className={active === id ? 'active' : ''}
                  onClick={() => setNavOpen(false)}
                >
                  {label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div className="docs-body">
          {/* 1 */}
          <section id="introduction" className="docs-section">
            <h2>Introduction</h2>
            <p className="docs-lede">
              StateJar turns conversations into structured state that any model can
              read. It stores extracted facts, preferences, decisions and
              constraints — never the transcript — and addresses each version by a
              SHA-256 hash of its canonical form. Ask a question and you get back
              only the fields that question needs, with a record of exactly what
              was disclosed.
            </p>
            <p className="docs-note">
              That hash is the whole idea: the same meaning always produces the same
              handle, so memory is reproducible rather than probabilistic. Base URL:
            </p>
            <CodeBlock code={`export STATEJAR_URL=${base}`} label="base url" />
          </section>

          {/* 2 */}
          <section id="authentication" className="docs-section">
            <h2>Authentication</h2>
            <p className="docs-note">
              Every request carries an <span className="mono">X-API-Key</span> header.
              Generate a key under{' '}
              <Link to="/api-keys">API Keys → Developer API</Link>; it is shown once
              and stored only as a SHA-256 hash, so a lost key is replaced rather
              than recovered.
            </p>
            {keyInfo === null ? (
              <p className="empty-note">Checking your keys…</p>
            ) : keyInfo ? (
              <p className="empty-note">
                Examples below use your active key ending{' '}
                <span className="mono">{keyInfo.key_last4}</span> — paste the full
                value in its place.
              </p>
            ) : (
              <p className="empty-note">
                No active key yet. <Link to="/api-keys">Generate one →</Link>
              </p>
            )}
            <CodeBlock code={`X-API-Key: ${apiKey}`} label="auth header" />
            <p className="docs-note">
              Keys can be issued with a 7-day, 30-day, 1-year or never expiry, and
              revoked at any time — revocation takes effect on the next request. An
              expired key returns <span className="mono">401</span> with the date it
              lapsed, so a stale value in an <span className="mono">.env</span>
              {' '}diagnoses itself:
            </p>
            <CodeBlock
              code={'{\n  "detail": "API key expired on 2026-07-04"\n}'}
              label="expired response"
            />
            <p className="docs-note">
              A key authenticates the data plane only. Minting keys, listing them
              and reading your provider keys stay console-only, so a leaked key
              cannot mint a successor or spend your provider credit.
            </p>
          </section>

          {/* 3 */}
          <section id="quickstart" className="docs-section">
            <h2>Quickstart</h2>
            <p className="docs-note">Sixty seconds from key to retrieved memory.</p>
            <ol className="docs-steps">
              <li>
                <strong>Generate a key</strong> under{' '}
                <Link to="/api-keys">API Keys</Link>, then export it:
                <CodeBlock code={`export STATEJAR_URL=${base}\nexport STATEJAR_KEY=${apiKey}`} label="exports" />
              </li>
              <li>
                <strong>Store something.</strong>
                <LangTabs value={language} onChange={pickLanguage} />
                <CodeBlock
                  code={snippetFor(language, {
                    base, key: apiKey, method: 'POST', path: '/api/v1/memory/ingest',
                    body: { session_tag: 'user-42', text: 'I prefer email, budget under 2000.' },
                  })}
                  label="quickstart ingest"
                />
              </li>
              <li>
                <strong>Ask for it back</strong> — note how little comes out.
                <CodeBlock
                  code={snippetFor(language, {
                    base, key: apiKey, method: 'POST', path: '/api/v1/memory/query',
                    body: { session_tag: 'user-42', query: 'What is my budget?', audit: true },
                  })}
                  label="quickstart query"
                />
              </li>
            </ol>
          </section>

          {/* 4 */}
          <section id="endpoints" className="docs-section">
            <h2>Endpoints</h2>
            {ENDPOINTS.map((endpoint) => (
              <EndpointCard
                key={endpoint.id} endpoint={endpoint} base={base} apiKey={apiKey}
                language={language} onLanguage={pickLanguage}
              />
            ))}
          </section>

          {/* 6 */}
          <section id="concepts" className="docs-section">
            <h2>Concepts</h2>
            <div className="concept-grid">
              {CONCEPTS.map((concept) => (
                <div className="concept-card" key={concept.id}>
                  <h3>{concept.title}</h3>
                  <p>{concept.body}</p>
                  <pre className="concept-diagram mono">{concept.diagram}</pre>
                </div>
              ))}
            </div>
          </section>

          {/* 7 */}
          <section id="errors" className="docs-section">
            <h2>Errors</h2>
            <p className="docs-note">
              Every error is <span className="mono">{'{"detail": "…"}'}</span>, and the
              detail is written to be actionable rather than generic.
            </p>
            <div className="table-scroll">
              <table className="docs-table">
                <thead><tr><th>Status</th><th>Meaning</th><th>How to fix</th></tr></thead>
                <tbody>
                  {ERROR_CODES.map(([code, meaning, fix]) => (
                    <tr key={code}>
                      <td className="mono"><span className={`status-pill s${code[0]}`}>{code}</span></td>
                      <td>{meaning}</td>
                      <td>{fix}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {/* 8 */}
          <section id="rate-limits" className="docs-section">
            <h2>Rate limits</h2>
            <div className="table-scroll">
              <table className="docs-table">
                <thead><tr><th>Endpoint</th><th>Limit</th><th>Keyed by</th></tr></thead>
                <tbody>
                  {RATE_LIMITS.map(([endpoint, limit, keyed]) => (
                    <tr key={endpoint}>
                      <td className="mono">{endpoint}</td>
                      <td>{limit}</td>
                      <td>{keyed}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="docs-note">
              Chat is keyed per API key, so one integration cannot exhaust another's
              budget. Over the limit returns <span className="mono">429</span>.
            </p>
          </section>

          {/* 9 */}
          <section id="sdk" className="docs-section">
            <h2>SDK snippet</h2>
            <p className="docs-note">
              No package to install — paste this into your project and you have a
              client.
            </p>
            <CodeBlock code={SDK_SNIPPET} label="python sdk" />
          </section>
        </div>
      </div>
    </>
  )
}
