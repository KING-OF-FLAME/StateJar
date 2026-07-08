import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api.js'

const FREE_MODELS = [
  'meta-llama/llama-3.3-70b-instruct:free',
  'google/gemini-2.0-flash-exp:free',
  'mistralai/mistral-7b-instruct:free',
]

const PAID_MODELS = [
  'openai/gpt-4o-mini',
  'anthropic/claude-sonnet-4.6',
  'anthropic/claude-haiku-4.5',
  'google/gemini-2.5-flash',
]

const CUSTOM_MODEL = '__custom__'

const TABS = ['Memory State', 'Retrieved Context', 'Handles', 'Audit']

/* ---------- JSON tree ---------- */
function JsonNode({ k, value, depth = 0, coral = false }) {
  const pad = { paddingLeft: depth ? 16 : 0 }
  if (value !== null && typeof value === 'object') {
    const entries = Array.isArray(value) ? value.map((v, i) => [i, v]) : Object.entries(value)
    return (
      <div style={pad} className={coral ? 'jt-coral' : ''}>
        {k !== undefined && <span className="jt-key">{k}</span>}
        {entries.length === 0 ? (
          <span className="jt-dim">{Array.isArray(value) ? ' []' : ' {}'}</span>
        ) : (
          entries.map(([ck, cv]) => (
            <JsonNode key={ck} k={ck} value={cv} depth={depth + 1} coral={coral || ck === 'conflicts'} />
          ))
        )}
      </div>
    )
  }
  return (
    <div style={pad} className={coral ? 'jt-coral' : ''}>
      <span className="jt-key">{k}</span>{' '}
      <span className={typeof value === 'number' ? 'jt-num' : 'jt-str'}>{JSON.stringify(value)}</span>
    </div>
  )
}

function StateTree({ state }) {
  if (!state) return <p className="empty-note">No memory yet — send a message to ingest.</p>
  const order = ['facts', 'preferences', 'decisions', 'constraints', 'goals', 'unresolved', 'conflicts']
  return (
    <div className="json-tree mono">
      {order.filter((k) => state[k] !== undefined).map((k) => (
        <JsonNode key={k} k={k} value={state[k]} coral={k === 'conflicts'} />
      ))}
    </div>
  )
}

/* ---------- model picker ---------- */
function ModelPicker({ choice, customModel, onChoice, onCustomChange }) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e) => { if (!wrapRef.current?.contains(e.target)) setOpen(false) }
    const onKey = (e) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('pointerdown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const isCustom = choice === CUSTOM_MODEL
  const pick = (value) => { onChoice(value); setOpen(false) }

  return (
    <div className="mp" ref={wrapRef}>
      <button
        type="button" className="mp-btn"
        aria-haspopup="listbox" aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="mp-label mono">
          {isCustom ? (customModel.trim() || 'Custom model…') : choice}
        </span>
        {FREE_MODELS.includes(choice) && <span className="badge-free">FREE</span>}
        <span className="mp-caret" aria-hidden="true">▾</span>
      </button>

      {open && (
        <div className="mp-pop" role="listbox" aria-label="Model">
          <p className="mp-group">Free</p>
          {FREE_MODELS.map((m) => (
            <button
              type="button" key={m} role="option" aria-selected={choice === m}
              className={`mp-item${choice === m ? ' active' : ''}`}
              onClick={() => pick(m)}
            >
              <span className="mp-name mono">{m}</span>
              <span className="badge-free">FREE</span>
            </button>
          ))}
          <p className="mp-group">Paid <span className="mp-note">requires credits</span></p>
          {PAID_MODELS.map((m) => (
            <button
              type="button" key={m} role="option" aria-selected={choice === m}
              className={`mp-item${choice === m ? ' active' : ''}`}
              onClick={() => pick(m)}
            >
              <span className="mp-name mono">{m}</span>
            </button>
          ))}
          <button
            type="button" role="option" aria-selected={isCustom}
            className={`mp-item mp-custom${isCustom ? ' active' : ''}`}
            onClick={() => pick(CUSTOM_MODEL)}
          >
            Custom model…
          </button>
        </div>
      )}

      {isCustom && (
        <input
          className="mp-input mono"
          value={customModel}
          onChange={(e) => onCustomChange(e.target.value)}
          placeholder="qwen/qwen-2.5-72b-instruct"
          aria-label="Custom OpenRouter model ID"
          spellCheck={false}
        />
      )}
    </div>
  )
}

/* ---------- playground ---------- */
export default function Playground() {
  const [sessions, setSessions] = useState(() =>
    JSON.parse(localStorage.getItem('statejar_sessions') || '["session-1"]'))
  const [session, setSession] = useState(sessions[0])
  const [modelChoice, setModelChoice] = useState(() => {
    const saved = localStorage.getItem('statejar_model')
    if (saved === CUSTOM_MODEL || FREE_MODELS.includes(saved) || PAID_MODELS.includes(saved)) {
      return saved
    }
    return FREE_MODELS[0]
  })
  const [customModel, setCustomModel] = useState(
    () => localStorage.getItem('statejar_custom_model') || '')
  const [auditScope, setAuditScope] = useState('session')
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [tab, setTab] = useState(0)
  const [state, setState] = useState(null)          // current memory state
  const [handle, setHandle] = useState(null)
  const [retrieved, setRetrieved] = useState(null)  // last query subset + metadata
  const [versions, setVersions] = useState([])
  const [inspected, setInspected] = useState(null)  // old state being inspected
  const [audit, setAudit] = useState([])
  const [pulse, setPulse] = useState(0)             // animation trigger
  const chatEndRef = useRef(null)

  const persistSessions = (list) => {
    setSessions(list)
    localStorage.setItem('statejar_sessions', JSON.stringify(list))
  }

  const pickModel = (value) => {
    setModelChoice(value)
    localStorage.setItem('statejar_model', value)
  }

  const editCustomModel = (value) => {
    setCustomModel(value)
    localStorage.setItem('statejar_custom_model', value)
  }

  // model string sent to the gateway; blank custom falls back to the free default
  const effectiveModel =
    modelChoice === CUSTOM_MODEL ? (customModel.trim() || FREE_MODELS[0]) : modelChoice

  const newSession = () => {
    const tag = `session-${sessions.length + 1}`
    persistSessions([...sessions, tag])
    setSession(tag)
    setMessages([])
    setState(null)
    setHandle(null)
    setRetrieved(null)
    setInspected(null)
  }

  const fetchAudit = async (tag, scope) => {
    const filter = scope === 'session' ? `&session_tag=${encodeURIComponent(tag)}` : ''
    const a = await api(`/audit?limit=20${filter}`)
    setAudit(a.entries)
  }

  const refreshSidePanels = async (tag) => {
    const [v] = await Promise.all([
      api(`/memory/versions?session_tag=${encodeURIComponent(tag)}`),
      fetchAudit(tag, auditScope),
    ])
    setVersions(v.versions.slice().reverse()) // newest first
  }

  // load state when switching sessions
  useEffect(() => {
    setInspected(null)
    setMessages([])
    setRetrieved(null)
    api(`/memory/versions?session_tag=${encodeURIComponent(session)}`)
      .then(async (v) => {
        setVersions(v.versions.slice().reverse())
        if (v.versions.length) {
          const latest = v.versions[v.versions.length - 1]
          const s = await api(`/memory/state/${latest}`)
          setState(s.state)
          setHandle(latest)
        } else {
          setState(null)
          setHandle(null)
        }
      })
      .catch(() => {})
  }, [session])

  // audit trail follows the active session and the This session / All toggle
  useEffect(() => {
    fetchAudit(session, auditScope).catch(() => {})
  }, [session, auditScope])

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const send = async (e) => {
    e.preventDefault()
    const text = input.trim()
    if (!text || busy) return
    setInput('')
    setBusy(true)
    setMessages((m) => [...m, { role: 'user', content: text }])
    try {
      // 1. ingest — extraction + canonicalization + handle + storage
      const ing = await api('/memory/ingest', {
        method: 'POST',
        body: { session_tag: session, text },
      })
      setState(ing.state)
      setHandle(ing.handle)

      // 2. retrieve minimum for this text as a query
      const q = await api('/memory/query', {
        method: 'POST',
        body: { session_tag: session, query: text },
      })
      setRetrieved(q)

      // 3. chat via the user's provider key (graceful if none saved)
      let reply
      try {
        const c = await api('/chat', {
          method: 'POST',
          body: { session_tag: session, query: text, model: effectiveModel },
        })
        reply = c.response
      } catch (err) {
        reply = `⚠ ${err.message} — memory pipeline still ran: state extracted, handle ${ing.handle.slice(0, 16)}… created. Save an OpenRouter key in API Keys to get live responses.`
      }
      setMessages((m) => [...m, { role: 'assistant', content: reply }])
      await refreshSidePanels(session)
      setPulse((p) => p + 1) // animate the inspector
    } catch (err) {
      setMessages((m) => [...m, { role: 'assistant', content: `⚠ ${err.message}` }])
    } finally {
      setBusy(false)
    }
  }

  const inspect = async (h) => {
    const s = await api(`/memory/state/${h}`)
    setInspected(s)
    setTab(0)
  }

  return (
    <div className="pg">
      <div className="pg-chat">
        <div className="pg-toolbar">
          <select value={session} onChange={(e) => setSession(e.target.value)}>
            {sessions.map((s) => <option key={s}>{s}</option>)}
          </select>
          <button className="btn btn-ghost pg-mini" onClick={newSession}>+ New session</button>
          <ModelPicker
            choice={modelChoice}
            customModel={customModel}
            onChoice={pickModel}
            onCustomChange={editCustomModel}
          />
        </div>

        <div className="pg-messages">
          {messages.length === 0 && (
            <div className="pg-hint">
              <p className="mono">// try:</p>
              <p>"My name is Ayaan, I prefer email, budget ₹2000"</p>
              <p>then switch to a new session and ask: "Book my delivery"</p>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`pg-msg ${m.role}`}>
              <span className="pg-role">{m.role === 'user' ? 'you' : 'assistant'}</span>
              <div className="pg-bubble">{m.content}</div>
            </div>
          ))}
          {busy && <div className="pg-msg assistant"><div className="pg-bubble pg-typing">···</div></div>}
          <div ref={chatEndRef} />
        </div>

        <form className="pg-input" onSubmit={send}>
          <input
            value={input} onChange={(e) => setInput(e.target.value)}
            placeholder="Say something memorable…" disabled={busy}
          />
          <button className="btn btn-primary" disabled={busy || !input.trim()}>Send</button>
        </form>
      </div>

      <div className="pg-inspector" key={pulse}>
        <div className="pg-tabs">
          {TABS.map((t, i) => (
            <button key={t} className={i === tab ? 'active' : ''} onClick={() => { setTab(i); setInspected(null) }}>
              {t}
            </button>
          ))}
        </div>

        <div className="pg-tab-body pulse-in">
          {tab === 0 && (
            <>
              {inspected ? (
                <>
                  <div className="pg-inspect-note">
                    Inspecting historical state <span className="mono">{inspected.handle.slice(0, 20)}…</span>
                    <button className="pg-mini btn btn-ghost" onClick={() => setInspected(null)}>back to latest</button>
                  </div>
                  <StateTree state={inspected.state} />
                </>
              ) : (
                <>
                  {handle && (
                    <p className="pg-handle-line mono">handle: <span className="hl-accent">{handle}</span></p>
                  )}
                  <StateTree state={state} />
                </>
              )}
            </>
          )}

          {tab === 1 && (
            retrieved ? (
              <>
                <div className="pg-chips">
                  {retrieved.metadata.subset_keys.map((k) => (
                    <span className="chip mono" key={k}>{k}</span>
                  ))}
                  {retrieved.metadata.subset_keys.length === 0 && (
                    <span className="empty-note">query needed no stored state</span>
                  )}
                  <span className="chip chip-green">
                    ~{retrieved.metadata.token_estimate_saved_pct}% tokens saved
                  </span>
                </div>
                <p className="pg-section-label">exact subset sent to the LLM</p>
                <StateTree state={retrieved.subset} />
              </>
            ) : <p className="empty-note">Send a message to see what the LLM actually receives.</p>
          )}

          {tab === 2 && (
            versions.length ? (
              <div className="timeline">
                {versions.map((h, i) => (
                  <div className="tl-item" key={h}>
                    <div className="tl-dot" />
                    {i < versions.length - 1 && <div className="tl-line" />}
                    <button className="tl-handle mono" onClick={() => inspect(h)} title="Click to inspect">
                      {h}
                    </button>
                    <span className="tl-meta">{i === 0 ? 'latest' : `parent of v${versions.length - i + 0}`}</span>
                    {i < versions.length - 1 && <span className="tl-arrow">↑ evolved from</span>}
                  </div>
                ))}
              </div>
            ) : <p className="empty-note">No versions yet in this session.</p>
          )}

          {tab === 3 && (
            <>
              <div className="audit-scope" role="group" aria-label="Audit scope">
                <button
                  className={auditScope === 'session' ? 'active' : ''}
                  onClick={() => setAuditScope('session')}
                >
                  This session
                </button>
                <button
                  className={auditScope === 'all' ? 'active' : ''}
                  onClick={() => setAuditScope('all')}
                >
                  All sessions
                </button>
              </div>
              {audit.length ? (
                <div className="audit-list">
                  {audit.map((a) => (
                    <div className="audit-row" key={a.request_id}>
                      <div className="mono audit-id">{a.request_id.slice(0, 12)}…</div>
                      <div className="mono audit-handle">{a.handle_used?.slice(0, 22)}…</div>
                      <div className="pg-chips">
                        {(a.subset_keys || []).map((k) => <span className="chip mono" key={k}>{k}</span>)}
                      </div>
                      <div className="audit-meta">
                        {auditScope === 'all' && a.session_tag ? `${a.session_tag} · ` : ''}
                        {a.provider} · {a.model} · {new Date(a.created_at).toLocaleTimeString()}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="empty-note">
                  {auditScope === 'session'
                    ? 'No audited responses in this session yet — chats appear here.'
                    : 'No audited responses yet — chats appear here.'}
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
