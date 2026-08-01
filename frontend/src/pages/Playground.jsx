import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
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
  // Local Ollama models: only ever populated from the backend, which serves
  // them behind SHOW_OLLAMA so production never advertises a laptop daemon.
  local: [],
}

const CUSTOM_MODEL = '__custom__'
const OLLAMA_PREFIX = 'ollama/'

const TABS = ['Memory State', 'Retrieved Context', 'Handles', 'Audit']

/* Scripted demo: user turns AND assistant replies are fixed in the client.
   Only /memory/ingest and /memory/query are called — the real memory
   pipeline (extraction, handles, minimal retrieval, audit) runs live, but
   no LLM chat endpoint and no provider key are ever involved, so the demo
   works identically on a brand-new account with zero keys saved. */
const DEMO_MSGS = [
  'My name is Ayaan, I prefer email, budget ₹2000',
  'Book my delivery with my usual preferences',
  'Budget is now ₹2500',
]

const DEMO_REPLIES = [
  "Got it, Ayaan! I've noted your email preference and ₹2000 budget.",
  "Booking with your saved preferences — I'll email you the confirmation " +
    'and keep it under ₹2000. Only your delivery time is pending: when ' +
    'should it arrive?',
  "Updated — your budget is now ₹2500. The earlier ₹2000 isn't " +
    "overwritten: it's preserved in your version history, and this " +
    'disclosure was logged in the audit trail.',
]

const DEMO_STEP_LABELS = [
  'extracting structured state…',
  'minting handle & logging audit…',
  'retrieving minimal subset cross-session…',
  'replying from memory, not transcript…',
  'evolving state, preserving history…',
  'writing the audit trail…',
]

/* Presenter captions: spoken-friendly step names for the stage caption bar. */
const PRESENTER_CAPTIONS = [
  'Extraction: raw words become structured state',
  'Sealing: SHA-256 handle minted, disclosure audited',
  'New session: retrieving the minimum',
  'Answering from memory — the transcript was never stored',
  'Budget revised: history preserved, conflict recorded',
  'The audit trail: proof of exactly what was disclosed',
]

/* Eases a displayed number toward `value` (for the live tokens-saved card). */
function EasedNumber({ value }) {
  const [n, setN] = useState(0)
  useEffect(() => {
    let raf
    const start = performance.now()
    const from = n
    const dur = 900
    const tick = (now) => {
      const t = Math.min((now - start) / dur, 1)
      const eased = 1 - Math.pow(1 - t, 3)
      setN(Math.round((from + (value - from) * eased) * 10) / 10)
      if (t < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [value]) // eslint-disable-line react-hooks/exhaustive-deps
  return <>{n}</>
}

/* Hard ceiling on any single demo step's network work: past this the beat
   degrades to its scripted reply rather than sitting on a spinner. */
const DEMO_STEP_TIMEOUT_MS = 6000

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
  // a numeric key means this is an item in a list (e.g. constraints.requirements);
  // a bullet reads better than "0:" for a collected value
  const isListItem = typeof k === 'number'
  return (
    <div style={pad} className={`${coral ? 'jt-coral' : ''}${isChanged ? ' jt-changed' : ''}`}>
      <span className={isListItem ? 'jt-bullet' : 'jt-key'}>{isListItem ? '–' : k}</span>{' '}
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
function ModelPicker({
  catalog, choice, customModel, onChoice, onCustomChange, disabled, disabledHint, openSignal,
}) {
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
    <div className={`mp${disabled ? ' mp-disabled' : ''}`} ref={wrapRef} title={disabled ? disabledHint : undefined}>
      <button
        type="button" className="mp-btn" disabled={disabled}
        title={disabled ? disabledHint : undefined}
        aria-haspopup="listbox" aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="mp-label mono">
          {isCustom ? (customModel.trim() || 'Custom model…') : choice}
        </span>
        {catalog.free.some((m) => m.id === choice) && <span className="badge-free">FREE</span>}
        {choice.startsWith(OLLAMA_PREFIX) && <span className="badge-offline">OFFLINE</span>}
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
          {catalog.local?.length > 0 && (
            <>
              <p className="mp-group">Local (offline) <span className="mp-note">runs on this machine</span></p>
              {catalog.local.map((m) => (
                <button
                  type="button" key={m.id} role="option" aria-selected={choice === m.id}
                  className={`mp-item${choice === m.id ? ' active' : ''}`}
                  onClick={() => pick(m.id)}
                  title={m.name}
                >
                  <span className="mp-name mono">{m.id}</span>
                  <span className="badge-offline">OFFLINE</span>
                </button>
              ))}
            </>
          )}
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
  const [ollamaDown, setOllamaDown] = useState(false) // local daemon unreachable
  const [pickerSignal, setPickerSignal] = useState(0) // bump to force the picker open
  const [customModel, setCustomModel] = useState(
    () => localStorage.getItem('statejar_custom_model') || '')
  const [auditScope, setAuditScope] = useState('session')
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [typing, setTyping] = useState(false)       // demo typing indicator
  const [demoRunning, setDemoRunning] = useState(false)
  const [demoStep, setDemoStep] = useState(0)       // 1-6 while the demo runs
  const [tab, setTab] = useState(0)
  const [state, setState] = useState(null)          // current memory state
  const [handle, setHandle] = useState(null)
  const [extractionSource, setExtractionSource] = useState(null) // "rules" | "gliner+rules"
  const [changed, setChanged] = useState(null)      // dotted paths updated by last ingest
  const [copied, setCopied] = useState(false)
  const [retrieved, setRetrieved] = useState(null)  // last query subset + metadata
  const [versions, setVersions] = useState([])
  const [inspected, setInspected] = useState(null)  // old state being inspected
  const [audit, setAudit] = useState([])
  const [pulse, setPulse] = useState(0)             // animation trigger
  const [searchParams, setSearchParams] = useSearchParams()
  const [presenter, setPresenter] = useState(() => searchParams.has('presenter'))
  const [presenterSaved, setPresenterSaved] = useState(null) // real % from /memory/query; null = hide card
  const presenterRef = useRef(presenter)            // read inside async demo flow
  const demoSavedRef = useRef([])                   // per-query saved % collected during a demo run
  const demoCtxRef = useRef(null)                   // { runId, tagA, tagB, idx, busy } while running
  const autoTimerRef = useRef(null)                 // non-presenter auto-advance timer
  const runIdRef = useRef(0)                        // bumped on restart to invalidate the old run
  const demoCtlRef = useRef({})                     // latest start/advance for the key handler
  const chatEndRef = useRef(null)
  const chatRef = useRef(null)                      // chat column, scrolled into view on demo start
  const inspectorRef = useRef(null)                 // inspector column, auto-scrolled on mobile
  const stateRef = useRef(null)                     // latest state for diffing in async flows
  // Session tag whose transcript survives the next switch. Stored as the tag
  // (not a boolean) so the [session] effect stays idempotent — a consumed
  // flag would let StrictMode's second effect pass wipe the first message.
  const keepForRef = useRef(null)

  const persistSessions = (list) => {
    setSessions(list)
    localStorage.setItem('statejar_sessions', JSON.stringify(list))
  }

  const switchSession = (tag, { keep = false } = {}) => {
    keepForRef.current = keep ? tag : null
    setSession(tag)
  }

  const pickModel = (value) => {
    setModelChoice(value)
    setModelGone(false)
    setOllamaDown(false)
    localStorage.setItem('statejar_model', value)
  }

  // Live model catalog: default to the first free model returned; keep the
  // user's saved choice only if it still exists (custom is always kept).
  useEffect(() => {
    api('/models')
      .then((cat) => {
        if (!cat.free?.length) return
        setCatalog({ free: cat.free, paid: cat.paid, local: cat.local || [] })
        setModelChoice((current) => {
          const known = [...cat.free, ...cat.paid, ...(cat.local || [])]
            .some((m) => m.id === current)
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

  /* Turn a provider failure into an actionable hint. The backend's exact
     message is always shown in the error bubble; these chips add the fix. */
  const flagIfModelGone = (err) => {
    const msg = err.message || ''
    if (/no endpoints found/i.test(msg)) {
      setModelGone(true)
      setPickerSignal((n) => n + 1)
    }
    // only when the daemon itself is unreachable — "ollama serve" is no fix
    // for e.g. "model requires more system memory"
    if (effectiveModel.startsWith(OLLAMA_PREFIX) && /not reachable|ollama serve/i.test(msg)) {
      setOllamaDown(true)
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
    if (ing.extraction_source) setExtractionSource(ing.extraction_source)
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
    if (keepForRef.current !== session) {
      setMessages([])
      setRetrieved(null)
    }
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

  /* On mobile/stacked layout, bring the inspector tab being updated into
     view so the live panel changes are actually seen. */
  const focusTab = (i) => {
    setTab(i)
    setInspected(null)
    if (window.innerWidth <= 1000) {
      // deferred: the inspector remounts on pulse (key change), which would
      // cancel a scroll started against the old node
      setTimeout(() => {
        inspectorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }, 350)
    }
  }

  /* ---------- demo step machine ----------
     Six scripted beats, fully self-contained for any account: only
     /memory/ingest and /memory/query (audited) are ever called, and every
     assistant reply is a local constant — no /chat call, no provider key,
     no dependency on the selected model.

     Each beat is { caption, before, work, reply }. The runner guarantees,
     via try/catch/finally + a hard timeout, that the typing indicator is
     always cleared and the scripted reply is always rendered — so a slow
     or failed backend degrades the demo instead of freezing it. */

  const demoSteps = [
    {
      before: (c) => { addMsg({ role: 'user', demo: true, content: DEMO_MSGS[0] }); focusTab(0) },
      work: async (c) => {
        const ing = await api('/memory/ingest', {
          method: 'POST', body: { session_tag: c.tagA, text: DEMO_MSGS[0] },
        })
        applyIngest(ing)
        await refreshVersions(c.tagA)
      },
    },
    {
      work: async (c) => {
        await demoQuery(c.tagA, DEMO_MSGS[0])
        await fetchAudit(c.tagA, auditScope)
      },
      reply: DEMO_REPLIES[0],
    },
    {
      before: (c) => {
        switchSession(c.tagB, { keep: true })
        addMsg({ role: 'user', demo: true, content: DEMO_MSGS[1] })
      },
      work: async (c) => {
        const q = await demoQuery(c.tagB, DEMO_MSGS[1])
        setRetrieved(q)
        focusTab(1)
        setPulse((p) => p + 1)
      },
    },
    { reply: DEMO_REPLIES[1] },
    {
      before: (c) => {
        switchSession(c.tagA, { keep: true })
        addMsg({ role: 'user', demo: true, content: DEMO_MSGS[2] })
      },
      work: async (c) => {
        const ing = await api('/memory/ingest', {
          method: 'POST', body: { session_tag: c.tagA, text: DEMO_MSGS[2] },
        })
        applyIngest(ing)
        await refreshVersions(c.tagA)
        focusTab(2)
      },
    },
    {
      work: async (c) => {
        await demoQuery(c.tagA, DEMO_MSGS[2])
        await fetchAudit(c.tagA, auditScope)
        focusTab(3)
        setPulse((p) => p + 1)
      },
      reply: DEMO_REPLIES[2],
    },
  ]

  /* Audited retrieval — its metadata is the only source for the presenter
     "tokens saved" card (null until a real percentage arrives). */
  const demoQuery = async (tag, query) => {
    const q = await api('/memory/query', {
      method: 'POST', body: { session_tag: tag, query, audit: true },
    })
    const pct = q?.metadata?.token_estimate_saved_pct
    if (typeof pct === 'number' && Number.isFinite(pct)) {
      demoSavedRef.current.push(pct)
      const avg =
        demoSavedRef.current.reduce((a, b) => a + b, 0) / demoSavedRef.current.length
      setPresenterSaved(Math.round(avg * 10) / 10)
    }
    return q
  }

  /* Runs one beat. Never rejects, never leaves a spinner up. */
  const runStep = async (idx) => {
    const ctx = demoCtxRef.current
    const step = demoSteps[idx]
    if (!ctx || !step) return
    setDemoStep(idx + 1)
    try {
      step.before?.(ctx)
    } catch (err) {
      console.error(`[statejar demo] step ${idx + 1} setup failed:`, err)
    }
    if (step.work) setTyping(true)
    try {
      if (step.work) {
        await Promise.race([
          step.work(ctx),
          new Promise((_, reject) =>
            setTimeout(
              () => reject(new Error(`timed out after ${DEMO_STEP_TIMEOUT_MS}ms`)),
              DEMO_STEP_TIMEOUT_MS,
            )),
        ])
      }
    } catch (err) {
      // degraded, not stuck: the scripted beat still lands
      console.error(`[statejar demo] step ${idx + 1} ${err.message} — continuing with the scripted reply`)
    } finally {
      if (demoCtxRef.current?.runId === ctx.runId) {
        setTyping(false)
        if (step.reply) addMsg({ role: 'assistant', demo: true, content: step.reply })
      }
    }
  }

  const clearAutoAdvance = () => {
    if (autoTimerRef.current) {
      clearTimeout(autoTimerRef.current)
      autoTimerRef.current = null
    }
  }

  const endDemo = () => {
    clearAutoAdvance()
    demoCtxRef.current = null
    setDemoRunning(false)
    setDemoStep(0)
  }

  /* Drives one beat, then hands control back: the presenter advances with
     Space / "Next", otherwise a timer does. */
  const driveStep = async (idx) => {
    const ctx = demoCtxRef.current
    if (!ctx) return
    ctx.idx = idx
    ctx.busy = true
    await runStep(idx)
    if (demoCtxRef.current?.runId !== ctx.runId) return // restarted mid-step
    ctx.busy = false
    // a Space pressed while this beat was still working is honoured now,
    // never swallowed — an early tap must not strand the presenter
    if (ctx.pendingAdvance) {
      ctx.pendingAdvance = false
      advanceDemo()
      return
    }
    if (!presenterRef.current) {
      clearAutoAdvance()
      autoTimerRef.current = setTimeout(() => advanceDemo(), 1200)
    }
  }

  const advanceDemo = () => {
    const ctx = demoCtxRef.current
    if (!ctx) return
    if (ctx.busy) {
      ctx.pendingAdvance = true
      return
    }
    clearAutoAdvance()
    const next = ctx.idx + 1
    if (next >= demoSteps.length) {
      endDemo()
      return
    }
    void driveStep(next)
  }

  const startDemo = () => {
    if (busy) return
    clearAutoAdvance()
    // a new run id invalidates any in-flight step from a previous run
    const runId = ++runIdRef.current
    const stamp = Date.now().toString(36)
    const tagA = `demo-${stamp}`
    const tagB = `demo-${stamp}-next`
    demoCtxRef.current = { runId, tagA, tagB, idx: -1, busy: false, pendingAdvance: false }
    demoSavedRef.current = []
    setPresenterSaved(null)
    setInput('')
    setDemoRunning(true)
    // stray focus must never swallow the presenter's Space key
    document.activeElement?.blur?.()
    chatRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    // Clear explicitly and switch with keep:true — letting the session
    // effect do the clearing would race the first step and wipe its message.
    setMessages([])
    setRetrieved(null)
    // fresh sessions so the demo never touches the user's own memory
    persistSessions([...sessions, tagA, tagB])
    switchSession(tagA, { keep: true })
    void driveStep(0)
  }

  // stop timers if the component unmounts mid-demo
  useEffect(() => clearAutoAdvance, [])

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

  /* ---------- presenter mode (?presenter=true) ---------- */

  // body class drives the CSS (hidden chrome, bigger type, high contrast)
  useEffect(() => {
    presenterRef.current = presenter
    document.body.classList.toggle('presenter-mode', presenter)
    return () => document.body.classList.remove('presenter-mode')
  }, [presenter])

  const exitPresenter = () => {
    setPresenter(false)
    const next = new URLSearchParams(searchParams)
    next.delete('presenter')
    setSearchParams(next, { replace: true })
  }

  /* Space = start/advance, R = restart, Esc = exit. Bound to window so it
     fires wherever focus sits; deliberate typing in a field still wins, and
     Esc there just releases focus so the next Space reaches the demo. */
  useEffect(() => {
    if (!presenter) return
    const onKey = (e) => {
      const el = e.target
      const tag = el?.tagName
      const inField =
        tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el?.isContentEditable
      if (e.key === 'Escape') {
        e.preventDefault()
        if (inField) el.blur() // first Esc leaves the field, second exits
        else exitPresenter()
        return
      }
      if (inField) return // the user meant to type
      if (e.code === 'Space') {
        e.preventDefault() // no page scroll, no re-click of a focused button
        const ctl = demoCtlRef.current
        if (demoCtxRef.current) ctl.advance?.()
        else ctl.start?.()
      } else if (e.key === 'r' || e.key === 'R') {
        e.preventDefault()
        demoCtlRef.current.start?.()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [presenter, searchParams, setSearchParams])

  // keep the key handler + on-screen buttons pointed at the latest closures
  useEffect(() => {
    demoCtlRef.current = { start: startDemo, advance: advanceDemo }
  })

  const locked = busy || demoRunning

  return (
    <div className="pg">
      {/* only shown once a real token_estimate_saved_pct has arrived */}
      {presenter && presenterSaved !== null && (
        <div className="presenter-counter" role="status" aria-live="polite">
          <span className="presenter-counter-label">Tokens saved this demo</span>
          <span className="presenter-counter-num">
            <EasedNumber value={presenterSaved} />%
          </span>
        </div>
      )}
      {presenter && (
        <div className="presenter-caption" role="status">
          {demoRunning && demoStep > 0 ? (
            <span className="presenter-caption-text">
              Step {demoStep}/6 — {PRESENTER_CAPTIONS[demoStep - 1]}
            </span>
          ) : (
            <span className="presenter-caption-text">
              Presenter mode — press Space to start the demo
            </span>
          )}
          {/* mouse fallback: a dead key must never strand a live demo */}
          <span className="presenter-controls">
            <button type="button" className="presenter-btn" onClick={() => (
              demoRunning ? advanceDemo() : startDemo()
            )}>
              {demoRunning ? 'Next ▸' : 'Start ▸'}
            </button>
            <button type="button" className="presenter-btn presenter-btn-ghost" onClick={startDemo}>
              Restart
            </button>
            <span className="presenter-hint mono">Space · R · Esc</span>
          </span>
        </div>
      )}
      <div className="pg-chat" ref={chatRef}>
        <div className="pg-toolbar">
          <button className="btn btn-primary pg-mini demo-btn" onClick={startDemo} disabled={locked}>
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
            disabledHint="Not used in demo mode"
            openSignal={pickerSignal}
          />
          {modelGone && (
            <span className="chip chip-warn">
              This model is no longer available — pick another
            </span>
          )}
          {ollamaDown && (
            <span className="chip chip-warn mono">Start Ollama locally: ollama serve</span>
          )}
        </div>

        {demoRunning && demoStep > 0 && (
          <div className="demo-progress" role="status" aria-live="polite">
            <span className="demo-progress-label mono">
              Step {demoStep} of 6 — {DEMO_STEP_LABELS[demoStep - 1]}
            </span>
            <div className="demo-progress-track" aria-hidden="true">
              <div
                className="demo-progress-fill"
                style={{ width: `${(demoStep / 6) * 100}%` }}
              />
            </div>
          </div>
        )}

        <div className="pg-messages">
          {messages.length === 0 && !demoRunning && (
            <div className="pg-hint">
              <button className="btn btn-primary demo-cta" onClick={startDemo} disabled={locked}>
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

      <div className="pg-inspector" key={pulse} ref={inspectorRef}>
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
                  {extractionSource && (
                    <span className="chip chip-meta mono" title="Which extraction layer produced this state">
                      extraction: {extractionSource}
                    </span>
                  )}
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
                {retrieved.metadata.retrieval_mode && (
                  <span className="chip chip-meta mono" title="How this subset was selected">
                    retrieval: {retrieved.metadata.retrieval_mode}
                  </span>
                )}
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
