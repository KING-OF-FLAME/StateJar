import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api.js'

/* Fallback catalog shown until GET /models answers (the backend serves the
   live free list from OpenRouter; stale hardcoded IDs 404 with
   "No endpoints found"). */
const FALLBACK_CATALOG = {
  free: [
    { id: 'meta-llama/llama-3.3-70b-instruct:free', name: 'Llama 3.3 70B Instruct (free)' },
    { id: 'google/gemma-3-27b-it:free', name: 'Gemma 3 27B (free)' },
    { id: 'deepseek/deepseek-chat-v3.1:free', name: 'DeepSeek V3.1 (free)' },
  ],
  paid: [
    { id: 'openai/gpt-4o-mini', name: 'GPT-4o mini' },
    { id: 'anthropic/claude-sonnet-4.6', name: 'Claude Sonnet 4.6' },
    { id: 'anthropic/claude-haiku-4.5', name: 'Claude Haiku 4.5' },
    { id: 'google/gemini-2.5-flash', name: 'Gemini 2.5 Flash' },
  ],
}

const CUSTOM_MODEL = '__custom__'

const TABS = ['Memory State', 'Retrieved Context', 'Handles', 'Audit']

/* Scripted demo: user turns are fixed; assistant replies come from the
   backend's zero-key "demo" provider, so ingest/retrieval/audit are real. */
const DEMO_MSGS = [
  'My name is Ayaan, I prefer email, budget ₹2000',
  'Book my delivery with my usual preferences',
  'Budget is now ₹2500',
]

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

const fmtTime = (ts) =>
  new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

/* Dotted paths whose value differs between two states (for the coral pulse). */
function diffPaths(oldS, newS, prefix = '') {
  const out = []
  if (!newS || typeof newS !== 'object') return out
  for (const [k, v] of Object.entries(newS)) {
    const p = prefix ? `${prefix}.${k}` : `${k}`
    const ov = oldS && typeof oldS === 'object' ? oldS[k] : undefined
    if (JSON.stringify(ov) === JSON.stringify(v)) continue
    if (v && typeof v === 'object' && ov && typeof ov === 'object') {
      out.push(...diffPaths(ov, v, p))
    } else {
      out.push(p)
    }
  }
  return out
}

/* ---------- JSON tree ---------- */
function JsonNode({ k, value, depth = 0, coral = false, path = '', changed }) {
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
            <JsonNode
              key={ck} k={ck} value={cv} depth={depth + 1}
              coral={coral || ck === 'conflicts'}
              path={path ? `${path}.${ck}` : `${ck}`}
              changed={changed}
            />
          ))
        )}
      </div>
    )
  }
  const isChanged = changed?.has(path)
  return (
    <div style={pad} className={`${coral ? 'jt-coral' : ''}${isChanged ? ' jt-changed' : ''}`}>
      <span className="jt-key">{k}</span>{' '}
      <span className={typeof value === 'number' ? 'jt-num' : 'jt-str'}>{JSON.stringify(value)}</span>
    </div>
  )
}

function StateTree({ state, changed }) {
  if (!state) {
    return (
      <p className="empty-note">
        No memory yet — send a message or run the instant demo; extracted state appears here live.
      </p>
    )
  }
  const order = ['facts', 'preferences', 'decisions', 'constraints', 'goals', 'unresolved', 'conflicts']
  return (
    <div className="json-tree mono">
      {order.filter((k) => state[k] !== undefined).map((k) => (
        <JsonNode key={k} k={k} value={state[k]} coral={k === 'conflicts'} path={k} changed={changed} />
      ))}
    </div>
  )
}

/* ---------- model picker ---------- */
function ModelPicker({ catalog, choice, customModel, onChoice, onCustomChange, disabled, openSignal }) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef(null)

  // parent bumps openSignal to force the picker open (e.g. stale model error)
  useEffect(() => {
    if (openSignal) setOpen(true)
  }, [openSignal])

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
        type="button" className="mp-btn" disabled={disabled}
        aria-haspopup="listbox" aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="mp-label mono">
          {isCustom ? (customModel.trim() || 'Custom model…') : choice}
        </span>
        {catalog.free.some((m) => m.id === choice) && <span className="badge-free">FREE</span>}
        <span className="mp-caret" aria-hidden="true">▾</span>
      </button>

      {open && (
        <div className="mp-pop" role="listbox" aria-label="Model">
          <p className="mp-group">Free</p>
          {catalog.free.map((m) => (
            <button
              type="button" key={m.id} role="option" aria-selected={choice === m.id}
              className={`mp-item${choice === m.id ? ' active' : ''}`}
              onClick={() => pick(m.id)}
              title={m.name}
            >
              <span className="mp-name mono">{m.id}</span>
              <span className="badge-free">FREE</span>
            </button>
          ))}
          <p className="mp-group">Paid <span className="mp-note">requires credits</span></p>
          {catalog.paid.map((m) => (
            <button
              type="button" key={m.id} role="option" aria-selected={choice === m.id}
              className={`mp-item${choice === m.id ? ' active' : ''}`}
              onClick={() => pick(m.id)}
              title={m.name}
            >
              <span className="mp-name mono">{m.id}</span>
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
          disabled={disabled}
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
  const [catalog, setCatalog] = useState(FALLBACK_CATALOG)
  const [modelChoice, setModelChoice] = useState(
    () => localStorage.getItem('statejar_model') || FALLBACK_CATALOG.free[0].id)
  const [modelGone, setModelGone] = useState(false)   // selected model vanished from OpenRouter
  const [pickerSignal, setPickerSignal] = useState(0) // bump to force the picker open
  const [customModel, setCustomModel] = useState(
    () => localStorage.getItem('statejar_custom_model') || '')
  const [auditScope, setAuditScope] = useState('session')
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [typing, setTyping] = useState(false)       // demo typing indicator
  const [demoRunning, setDemoRunning] = useState(false)
  const [tab, setTab] = useState(0)
  const [state, setState] = useState(null)          // current memory state
  const [handle, setHandle] = useState(null)
  const [changed, setChanged] = useState(null)      // dotted paths updated by last ingest
  const [copied, setCopied] = useState(false)
  const [retrieved, setRetrieved] = useState(null)  // last query subset + metadata
  const [versions, setVersions] = useState([])
  const [inspected, setInspected] = useState(null)  // old state being inspected
  const [audit, setAudit] = useState([])
  const [pulse, setPulse] = useState(0)             // animation trigger
  const chatEndRef = useRef(null)
  const stateRef = useRef(null)                     // latest state for diffing in async flows
  const keepMessagesRef = useRef(false)             // demo keeps the transcript across session switches

  const persistSessions = (list) => {
    setSessions(list)
    localStorage.setItem('statejar_sessions', JSON.stringify(list))
  }

  const switchSession = (tag, { keep = false } = {}) => {
    keepMessagesRef.current = keep
    setSession(tag)
  }

  const pickModel = (value) => {
    setModelChoice(value)
    setModelGone(false)
    localStorage.setItem('statejar_model', value)
  }

  // Live model catalog: default to the first free model returned; keep the
  // user's saved choice only if it still exists (custom is always kept).
  useEffect(() => {
    api('/models')
      .then((cat) => {
        if (!cat.free?.length) return
        setCatalog({ free: cat.free, paid: cat.paid })
        setModelChoice((current) => {
          const known = [...cat.free, ...cat.paid].some((m) => m.id === current)
          if (current === CUSTOM_MODEL || known) return current
          localStorage.setItem('statejar_model', cat.free[0].id)
          return cat.free[0].id
        })
      })
      .catch(() => {}) // keep the fallback catalog
  }, [])

  const editCustomModel = (value) => {
    setCustomModel(value)
    localStorage.setItem('statejar_custom_model', value)
  }

  // model string sent to the gateway; blank custom falls back to the free default
  const effectiveModel =
    modelChoice === CUSTOM_MODEL ? (customModel.trim() || catalog.free[0].id) : modelChoice

  /* OpenRouter's 404 for a delisted/renamed model — surface a hint and reopen the picker. */
  const flagIfModelGone = (err) => {
    if (/no endpoints found/i.test(err.message || '')) {
      setModelGone(true)
      setPickerSignal((n) => n + 1)
    }
  }

  const newSession = () => {
    const tag = `session-${sessions.length + 1}`
    persistSessions([...sessions, tag])
    switchSession(tag)
  }

  const addMsg = (m) => setMessages((prev) => [...prev, { ts: Date.now(), ...m }])

  const applyIngest = (ing) => {
    setChanged(new Set(diffPaths(stateRef.current, ing.state)))
    stateRef.current = ing.state
    setState(ing.state)
    setHandle(ing.handle)
    setPulse((p) => p + 1)
  }

  const fetchAudit = async (tag, scope) => {
    const filter = scope === 'session' ? `&session_tag=${encodeURIComponent(tag)}` : ''
    const a = await api(`/audit?limit=20${filter}`)
    setAudit(a.entries)
  }

  const refreshVersions = async (tag) => {
    const v = await api(`/memory/versions?session_tag=${encodeURIComponent(tag)}`)
    setVersions(v.versions.slice().reverse()) // newest first
  }

  const refreshSidePanels = async (tag) => {
    await Promise.all([refreshVersions(tag), fetchAudit(tag, auditScope)])
  }

  // load state when switching sessions
  useEffect(() => {
    setInspected(null)
    setChanged(null)
    if (!keepMessagesRef.current) {
      setMessages([])
      setRetrieved(null)
    }
    keepMessagesRef.current = false
    api(`/memory/versions?session_tag=${encodeURIComponent(session)}`)
      .then(async (v) => {
        setVersions(v.versions.slice().reverse())
        if (v.versions.length) {
          const latest = v.versions[v.versions.length - 1]
          const s = await api(`/memory/state/${latest}`)
          stateRef.current = s.state
          setState(s.state)
          setHandle(latest)
        } else {
          stateRef.current = null
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
  }, [messages, typing])

  /* One silent retry on network failure (e.g. a backend cold start). */
  const chatWithRetry = async (body) => {
    try {
      return await api('/chat', { method: 'POST', body })
    } catch (err) {
      if (err.isNetwork) return api('/chat', { method: 'POST', body })
      throw err
    }
  }

  const send = async (e) => {
    e.preventDefault()
    const text = input.trim()
    if (!text || busy || demoRunning) return
    setInput('')
    setBusy(true)
    addMsg({ role: 'user', content: text })
    try {
      // 1. ingest — extraction + canonicalization + handle + storage
      const ing = await api('/memory/ingest', {
        method: 'POST',
        body: { session_tag: session, text },
      })
      applyIngest(ing)

      // 2. retrieve minimum for this text as a query
      const q = await api('/memory/query', {
        method: 'POST',
        body: { session_tag: session, query: text },
      })
      setRetrieved(q)

      // 3. chat via the user's provider key
      const payload = { session_tag: session, query: text, model: effectiveModel }
      try {
        const c = await chatWithRetry(payload)
        addMsg({ role: 'assistant', content: c.response })
      } catch (err) {
        flagIfModelGone(err)
        addMsg({ role: 'assistant', error: true, content: err.message, payload })
      }
      await refreshSidePanels(session)
    } catch (err) {
      addMsg({ role: 'assistant', error: true, content: err.message })
    } finally {
      setBusy(false)
    }
  }

  /* Re-run just the failed chat call, replacing its error bubble. */
  const retryChat = async (idx, payload) => {
    if (busy || demoRunning) return
    setBusy(true)
    try {
      const c = await chatWithRetry(payload)
      setMessages((m) => m.map((x, i) =>
        (i === idx ? { role: 'assistant', content: c.response, ts: Date.now() } : x)))
      await refreshSidePanels(session)
    } catch (err) {
      flagIfModelGone(err)
      setMessages((m) => m.map((x, i) =>
        (i === idx ? { ...x, content: err.message, ts: Date.now() } : x)))
    } finally {
      setBusy(false)
    }
  }

  /* Scripted 6-step demo: real ingest/retrieval/audit, zero-key scripted replies. */
  const runDemo = async () => {
    if (busy || demoRunning) return
    setDemoRunning(true)
    setInput('')
    const stamp = Date.now().toString(36).slice(-5)
    const tagA = `demo-${stamp}`
    const tagB = `demo-${stamp}-next`
    const demoChat = async (tag, query) => {
      const c = await chatWithRetry({
        session_tag: tag, query, model: 'scripted-demo', provider: 'demo',
      })
      return c.response
    }
    try {
      // fresh sessions so the demo never touches the user's own memory
      persistSessions([...sessions, tagA, tagB])
      switchSession(tagA)
      await wait(400)

      // step 1 — extract: real ingest; state + handle appear live
      addMsg({ role: 'user', demo: true, content: DEMO_MSGS[0] })
      setTab(0)
      setTyping(true)
      await wait(700)
      const ing1 = await api('/memory/ingest', {
        method: 'POST', body: { session_tag: tagA, text: DEMO_MSGS[0] },
      })
      applyIngest(ing1)
      await refreshVersions(tagA)

      // step 2 — scripted acknowledgement (audited via the demo provider)
      await wait(800)
      const reply1 = await demoChat(tagA, DEMO_MSGS[0])
      setTyping(false)
      addMsg({ role: 'assistant', demo: true, content: reply1 })
      fetchAudit(tagA, auditScope).catch(() => {})

      // step 3 — new session: cross-session minimal retrieval
      await wait(900)
      switchSession(tagB, { keep: true })
      await wait(400)
      addMsg({ role: 'user', demo: true, content: DEMO_MSGS[1] })
      setTyping(true)
      await wait(700)
      const q = await api('/memory/query', {
        method: 'POST', body: { session_tag: tagB, query: DEMO_MSGS[1] },
      })
      setRetrieved(q)
      setTab(1)
      setPulse((p) => p + 1)

      // step 4 — scripted booking reply
      await wait(800)
      const reply2 = await demoChat(tagB, DEMO_MSGS[1])
      setTyping(false)
      addMsg({ role: 'assistant', demo: true, content: reply2 })

      // step 5 — back in the first session: state evolves, old handle preserved
      await wait(900)
      switchSession(tagA, { keep: true })
      await wait(400)
      addMsg({ role: 'user', demo: true, content: DEMO_MSGS[2] })
      setTyping(true)
      await wait(700)
      const ing2 = await api('/memory/ingest', {
        method: 'POST', body: { session_tag: tagA, text: DEMO_MSGS[2] },
      })
      applyIngest(ing2)
      await refreshVersions(tagA)
      setTab(2)

      // step 6 — scripted acknowledgement, then the audit trail of it all
      await wait(800)
      const reply3 = await demoChat(tagA, DEMO_MSGS[2])
      setTyping(false)
      addMsg({ role: 'assistant', demo: true, content: reply3 })
      await wait(700)
      await fetchAudit(tagA, auditScope).catch(() => {})
      setTab(3)
      setPulse((p) => p + 1)
    } catch (err) {
      setTyping(false)
      addMsg({ role: 'assistant', error: true, content: `Demo stopped: ${err.message}` })
    } finally {
      setDemoRunning(false)
    }
  }

  const inspect = async (h) => {
    const s = await api(`/memory/state/${h}`)
    setInspected(s)
    setTab(0)
  }

  const copyHandle = async (h) => {
    try {
      await navigator.clipboard.writeText(h)
      setCopied(true)
      setTimeout(() => setCopied(false), 1200)
    } catch {
      /* clipboard unavailable (http / old browser) — leave the handle selectable */
    }
  }

  const locked = busy || demoRunning

  return (
    <div className="pg">
      <div className="pg-chat">
        <div className="pg-toolbar">
          <button className="btn btn-primary pg-mini demo-btn" onClick={runDemo} disabled={locked}>
            {demoRunning ? 'Demo running…' : '▶ Run instant demo'}
          </button>
          <select
            value={session} disabled={demoRunning}
            onChange={(e) => switchSession(e.target.value)}
            aria-label="Session"
          >
            {sessions.map((s) => <option key={s}>{s}</option>)}
          </select>
          <button className="btn btn-ghost pg-mini" onClick={newSession} disabled={demoRunning}>
            + New session
          </button>
          <ModelPicker
            catalog={catalog}
            choice={modelChoice}
            customModel={customModel}
            onChoice={pickModel}
            onCustomChange={editCustomModel}
            disabled={demoRunning}
            openSignal={pickerSignal}
          />
          {modelGone && (
            <span className="chip chip-warn">
              This model is no longer available — pick another
            </span>
          )}
        </div>

        <div className="pg-messages">
          {messages.length === 0 && !demoRunning && (
            <div className="pg-hint">
              <button className="btn btn-primary demo-cta" onClick={runDemo} disabled={locked}>
                ▶ Run instant demo
              </button>
              <p className="mono">// no API key needed — watch the memory pipeline run live</p>
              <p>or say: "My name is Ayaan, I prefer email, budget ₹2000"</p>
              <p>then switch to a new session and ask: "Book my delivery"</p>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`pg-msg ${m.role}`}>
              <span className="pg-role">
                {m.role === 'user' ? 'you' : 'assistant'}
                {m.demo && <span className="chip-demo">demo</span>}
                <span className="pg-time">{fmtTime(m.ts)}</span>
              </span>
              <div className={`pg-bubble${m.error ? ' pg-error' : ''}`}>
                {m.content}
                {m.error && m.payload && (
                  <button
                    className="retry-btn" disabled={locked}
                    onClick={() => retryChat(i, m.payload)}
                  >
                    ↻ Retry
                  </button>
                )}
              </div>
            </div>
          ))}
          {(busy || typing) && (
            <div className="pg-msg assistant"><div className="pg-bubble pg-typing">···</div></div>
          )}
          <div ref={chatEndRef} />
        </div>

        <form className="pg-input" onSubmit={send}>
          <input
            value={input} onChange={(e) => setInput(e.target.value)}
            placeholder="Say something memorable…" disabled={locked}
          />
          <button className="btn btn-primary" disabled={locked || !input.trim()}>Send</button>
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

        <div className="pg-tab-body pulse-in" key={tab}>
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
                    <p className="pg-handle-line mono">
                      handle: <span className="hl-accent">{handle}</span>
                      <button
                        className="copy-btn handle-copy" type="button"
                        onClick={() => copyHandle(handle)}
                        aria-label="Copy handle"
                        title="Copy handle"
                      >
                        {copied ? '✓' : '⧉'}
                      </button>
                    </p>
                  )}
                  <StateTree state={state} changed={changed} />
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
            ) : (
              <p className="empty-note">
                Send a message to see the minimal subset the LLM receives — never your full transcript.
              </p>
            )
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
            ) : (
              <p className="empty-note">
                No versions yet — every update mints a new content-addressed handle; history is never overwritten.
              </p>
            )
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
                    ? 'No audited responses in this session yet — every chat logs exactly what was disclosed.'
                    : 'No audited responses yet — every chat logs exactly what was disclosed.'}
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
