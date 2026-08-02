import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../lib/api.js'
import AuditTimeline from '../components/AuditTimeline.jsx'
import Pipeline, { canonicalPreview, countFields, usePipeline } from '../components/Pipeline.jsx'
import {
  chatLocal, classifyError, isLocalHost, listLocalModels, normaliseBase,
} from '../lib/ollama.js'

const CUSTOM_MODEL = '__custom__'
const OLLAMA_PREFIX = 'ollama/'

const TABS = ['Memory State', 'Retrieved Context', 'Handles', 'Audit']

/* Scripted demo: user turns AND assistant replies are fixed in the client.
   Only /memory/ingest and /memory/query are called — the real memory
   pipeline (extraction, handles, minimal retrieval, audit) runs live, but
   no LLM chat endpoint and no provider key are ever involved, so the demo
   works identically on a brand-new account with zero keys saved. */
const DEMO_MSGS = {
  brief:
    'Build me a landing page. Stack: React + Tailwind. Dark theme, ' +
    'brand color #E07856. No external UI libraries. ' +
    'Target audience: Indian SMB owners.',
  followUp: 'Now add a pricing section.',
  recolor: 'Actually make the brand color #6B9080.',
  uiLib: 'Use shadcn/ui for the components.',
}

const DEMO_REPLIES = {
  scaffold: 'Landing page scaffolded — React + Tailwind, dark theme, #E07856 accents.',
  pricing:
    'Pricing section added — same React + Tailwind, dark, #E07856, ' +
    'no external UI libraries.',
  recolor:
    'Updated to #6B9080. The previous value is preserved in history, ' +
    'not overwritten.',
  uiLib:
    "Noted — that contradicts your earlier 'no external UI libraries' " +
    "constraint. I've kept both, flagged as a conflict.",
  audit:
    'Every answer above is replayable — handle, exact fields used, ' +
    'model, timestamp.',
}

const DEMO_STEP_LABELS = [
  'extracting the build spec…',
  'counting what a transcript would cost…',
  'new session — retrieving the minimum…',
  'evolving state, preserving history…',
  'recording the contradiction…',
  'writing the audit trail…',
]

/* Presenter captions: spoken-friendly step names for the stage caption bar. */
const PRESENTER_CAPTIONS = [
  'The brief: five constraints become structured state',
  'The cost of repeating yourself, turn after turn',
  'Next day, new chat — it never saw the first conversation',
  'Colour revised: a new handle, the old one still intact',
  'A contradiction: both values kept, neither overwritten',
  'Provenance: every answer replayable, field by field',
]

/* Beat 2 of the demo: the argument, not an API call. The numbers describe
   what transcript-replay costs by turn 10 when the spec must be re-pasted
   every time — the contrast the live retrieval then demonstrates for real. */
function CompareCard() {
  return (
    <div className="cmp" role="figure" aria-label="Context cost with and without StateJar">
      <div className="cmp-col cmp-without">
        <h4>Without StateJar</h4>
        <ul>
          <li>Re-paste the whole spec into every new prompt</li>
          <li>Context grows with each turn</li>
          <li className="cmp-figure">~4,100 tokens by turn 10</li>
        </ul>
      </div>
      <div className="cmp-col cmp-with">
        <h4>With StateJar</h4>
        <ul>
          <li>The spec lives in the jar, addressed by handle</li>
          <li>Each prompt sends only the fields it needs</li>
          <li className="cmp-figure">only what this turn requires</li>
        </ul>
      </div>
    </div>
  )
}

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

/* Unattended pacing: six beats at roughly five seconds each is the ~30s
   story. Presenter mode ignores this entirely and waits for Space. */
const DEMO_BEAT_PACE_MS = 4400

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

/* ---------- extraction tiers ---------- */
/* Which tier caught which field. Rules are deterministic and always run;
   the neural tiers only fill what rules missed, so a state made entirely of
   coral chips is a state whose identity is fully reproducible. */
const TIER_META = {
  rules: { label: 'rules', hint: 'Deterministic patterns — same answer on every machine' },
  gliner2: { label: 'GLiNER2', hint: 'Schema-guided neural extraction, for what the patterns missed' },
  llm: { label: 'LLM', hint: 'Strict-JSON extraction via your own provider key, messy input only' },
}

function TierChips({ sources, origins }) {
  const tiers = Array.isArray(sources) ? sources : sources ? [sources] : []
  if (!tiers.length) return null
  const counts = {}
  for (const tier of Object.values(origins || {})) {
    counts[tier] = (counts[tier] || 0) + 1
  }
  return (
    <div className="tier-chips" role="group" aria-label="Extraction tiers">
      {tiers.map((tier) => {
        const meta = TIER_META[tier] || { label: tier, hint: tier }
        return (
          <span
            key={tier}
            className={`tier-chip tier-${tier}`}
            title={counts[tier] ? `${meta.hint} — ${counts[tier]} field${counts[tier] === 1 ? '' : 's'}` : meta.hint}
          >
            <span className="tier-dot" aria-hidden="true" />
            {meta.label}
            {counts[tier] ? <span className="tier-count">{counts[tier]}</span> : null}
          </span>
        )
      })}
    </div>
  )
}

/* ---------- JSON tree ---------- */
function JsonNode({ k, value, depth = 0, coral = false, path = '', changed, origins }) {
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
              origins={origins}
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
  // unresolved entries are keyed by their field name, not their array index
  const origin = origins?.[path]
  const meta = origin ? TIER_META[origin] : null
  return (
    <div
      style={pad}
      className={`${coral ? 'jt-coral' : ''}${isChanged ? ' jt-changed' : ''}`}
      title={meta ? `${path} — found by ${meta.label}` : undefined}
    >
      <span className={isListItem ? 'jt-bullet' : 'jt-key'}>{isListItem ? '–' : k}</span>{' '}
      <span className={typeof value === 'number' ? 'jt-num' : 'jt-str'}>{JSON.stringify(value)}</span>
      {origin && <span className={`jt-origin tier-${origin}`} aria-hidden="true" />}
    </div>
  )
}

function StateTree({ state, changed, origins }) {
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
        <JsonNode
          key={k} k={k} value={state[k]} coral={k === 'conflicts'}
          path={k} changed={changed} origins={origins}
        />
      ))}
    </div>
  )
}

/* ---------- model picker ---------- */
/* Grouped by provider: only providers the user has configured appear, so the
   list is a picture of their own account rather than a menu of everything
   that exists. Custom lets any id reach any configured provider — the
   backend has no whitelist, so a brand-new model works the day it ships. */
function ModelPicker({
  groups, choice, customModel, customProvider, onChoice, onCustomChange,
  onCustomProvider, disabled, disabledHint, openSignal,
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
  const configured = groups.length > 0
  const allModels = groups.flatMap((g) => [...g.free, ...g.paid])
  const selected = allModels.find((m) => m.id === choice)

  return (
    <div
      className={`mp${disabled ? ' mp-disabled' : ''}`}
      ref={wrapRef}
      title={disabled ? disabledHint : undefined}
    >
      <button
        type="button" className="mp-btn" disabled={disabled}
        title={disabled ? disabledHint : undefined}
        aria-haspopup="listbox" aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="mp-label mono">
          {isCustom
            ? (customModel.trim() || 'Custom model…')
            : (choice || 'No model')}
        </span>
        {selected?.is_free && <span className="badge-free">FREE</span>}
        {choice.startsWith(OLLAMA_PREFIX) && <span className="badge-offline">OFFLINE</span>}
        <span className="mp-caret" aria-hidden="true">▾</span>
      </button>

      {open && (
        <div className="mp-pop" role="listbox" aria-label="Model">
          {!configured && (
            <Link className="mp-item mp-empty" to="/api-keys" onClick={() => setOpen(false)}>
              Add a provider key to chat →
            </Link>
          )}

          {groups.map((group) => (
            <div key={group.provider} className="mp-provider">
              <p className="mp-group">
                {group.label}
                <span className="mp-note">
                  {group.error
                    ? 'unavailable'
                    : `${group.free.length + group.paid.length} models`}
                </span>
              </p>
              {group.error && <p className="mp-error">{group.error}</p>}

              {group.free.length > 0 && <p className="mp-sub">Free</p>}
              {group.free.map((m) => (
                <button
                  type="button" key={m.id} role="option" aria-selected={choice === m.id}
                  className={`mp-item${choice === m.id ? ' active' : ''}`}
                  onClick={() => pick(m.id)} title={m.name}
                >
                  <span className="mp-name mono">{m.id}</span>
                  <span className="badge-free">FREE</span>
                </button>
              ))}

              {group.paid.length > 0 && <p className="mp-sub">Paid</p>}
              {group.paid.map((m) => (
                <button
                  type="button" key={m.id} role="option" aria-selected={choice === m.id}
                  className={`mp-item${choice === m.id ? ' active' : ''}`}
                  onClick={() => pick(m.id)} title={m.name}
                >
                  <span className="mp-name mono">{m.id}</span>
                </button>
              ))}
            </div>
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
        <div className="mp-custom-row">
          <select
            className="mp-custom-provider"
            value={customProvider}
            onChange={(e) => onCustomProvider(e.target.value)}
            aria-label="Provider for the custom model"
            disabled={disabled}
          >
            {(configured ? groups : [{ provider: 'openrouter', label: 'OpenRouter' }])
              .map((g) => (
                <option key={g.provider} value={g.provider}>{g.label}</option>
              ))}
          </select>
          <input
            className="mp-input mono"
            value={customModel}
            onChange={(e) => onCustomChange(e.target.value)}
            placeholder="any model id, sent through unchanged"
            disabled={disabled}
            aria-label="Custom model id"
          />
        </div>
      )}
    </div>
  )
}

export default function Playground() {
  const [sessions, setSessions] = useState(() =>
    JSON.parse(localStorage.getItem('statejar_sessions') || '["session-1"]'))
  const [session, setSession] = useState(sessions[0])
  const [groups, setGroups] = useState([])   // [{provider, label, free, paid, error?}]
  const [modelChoice, setModelChoice] = useState(
    () => localStorage.getItem('statejar_model') || '')
  const [modelGone, setModelGone] = useState(false)   // selected model vanished from OpenRouter
  const [ollamaDown, setOllamaDown] = useState(false) // local daemon unreachable
  const [pickerSignal, setPickerSignal] = useState(0) // bump to force the picker open
  const [customModel, setCustomModel] = useState(
    () => localStorage.getItem('statejar_custom_model') || '')
  const [customProvider, setCustomProvider] = useState(
    () => localStorage.getItem('statejar_custom_provider') || 'openrouter')
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
  const [extractionSource, setExtractionSource] = useState(null)  // ["rules","gliner2",…]
  const [extractionOrigins, setExtractionOrigins] = useState({})  // "facts.name" -> tier
  const [changed, setChanged] = useState(null)      // dotted paths updated by last ingest
  const [copied, setCopied] = useState(false)
  const [retrieved, setRetrieved] = useState(null)  // last query subset + metadata
  const [versions, setVersions] = useState([])
  const [inspected, setInspected] = useState(null)  // old state being inspected
  const [audit, setAudit] = useState([])
  const [newAuditId, setNewAuditId] = useState(null)
  const [ollamaBase, setOllamaBase] = useState(null)  // set when browser-direct   // newest row, highlighted after a demo
  const [demoSummary, setDemoSummary] = useState(null) // {turns, savedPct} once a run finishes
  const pipe = usePipeline()
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

  /* Live catalog, one group per configured provider. A saved choice is kept
     only while the catalog still lists it — a model pulled by its provider,
     or a key that was removed, falls back to the first available one and
     raises the "no longer available" hint rather than failing at send time. */
  useEffect(() => {
    api('/models')
      .then((cat) => {
        const live = cat.groups || []
        setGroups(live)
        const all = live.flatMap((g) => [...g.free, ...g.paid])
        setModelChoice((current) => {
          if (current === CUSTOM_MODEL) return current
          if (all.some((m) => m.id === current)) return current
          if (current && all.length) setModelGone(true)
          const next = all.length ? all[0].id : ''
          localStorage.setItem('statejar_model', next)
          return next
        })
      })
      .catch(() => setGroups([]))
  }, [])

  /* Local models are enumerated by the browser, not the backend: a hosted
     StateJar can never see http://localhost:11434, but the user's own tab
     can. The list is therefore whatever they have actually pulled. */
  useEffect(() => {
    let cancelled = false
    api('/keys/provider')
      .then(async (keys) => {
        const saved = keys.find((k) => k.provider === 'ollama')
        const base = normaliseBase(saved?.config?.base_url)
        if (saved?.has_key || !isLocalHost(base)) return   // server-side mode
        setOllamaBase(base)
        try {
          const models = await listLocalModels(base)
          if (!cancelled && models.length) {
            setGroups((prev) => [
              ...prev.filter((g) => g.provider !== 'ollama'),
              { provider: 'ollama', label: 'Ollama (local)', free: models, paid: [] },
            ])
          }
        } catch {
          /* daemon down or CORS-blocked — the API Keys page explains the fix */
        }
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])

  const editCustomModel = (value) => {
    setCustomModel(value)
    localStorage.setItem('statejar_custom_model', value)
  }

  const editCustomProvider = (value) => {
    setCustomProvider(value)
    localStorage.setItem('statejar_custom_provider', value)
  }

  const allModels = groups.flatMap((g) => [...g.free, ...g.paid])
  const hasProviders = groups.length > 0

  /* The id sent to /chat. A custom id is namespaced with the provider the
     user picked so the gateway routes it there; OpenRouter ids stay in their
     native vendor/model form. */
  const effectiveModel = (() => {
    if (modelChoice !== CUSTOM_MODEL) return modelChoice
    const typed = customModel.trim()
    if (!typed) return allModels[0]?.id || ''
    if (customProvider === 'openrouter') return typed
    return typed.startsWith(`${customProvider}/`) ? typed : `${customProvider}/${typed}`
  })()

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
    if (ing.extraction_origins) setExtractionOrigins(ing.extraction_origins)
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
    pipe.reset()
    try {
      // 1. ingest — extraction + canonicalization + handle + storage
      const ing = await runIngest(session, text)

      // 2. retrieve minimum for this text as a query
      pipe.begin('retrieve')
      const q = await api('/memory/query', {
        method: 'POST',
        body: { session_tag: session, query: text },
      })
      setRetrieved(q)
      const keys = q.metadata.subset_keys || []
      pipe.complete([['retrieve', {
        badge: `${keys.length} of ${keys.length + (q.metadata.fields_dropped || 0)} fields`,
        payload: { subset_keys: keys, subset: q.subset },
      }]])

      // 3. chat — locally for ollama/*, otherwise via our gateway
      const payload = { session_tag: session, query: text, model: effectiveModel }
      try {
        const c = ollamaBase && effectiveModel.startsWith(OLLAMA_PREFIX)
          ? await chatBrowserDirect(text, q, effectiveModel)
          : await chatWithRetry(payload)
        addMsg({ role: 'assistant', content: c.response })
        // the audit row exists only once a response was actually served
        pipe.complete([['audit', {
          badge: 'logged',
          payload: { audit_id: c.audit_id, subset_keys: c.subset_keys },
        }]])
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

  /* The prompt goes straight from this browser to the user's own daemon,
     so it never reaches our servers. The retrieval already happened here, so
     the disclosure is posted back to keep the audit trail complete. */
  const chatBrowserDirect = async (text, retrieved, model) => {
    const bare = model.slice(OLLAMA_PREFIX.length)
    let result
    try {
      result = await chatLocal({
        baseUrl: ollamaBase,
        model: bare,
        systemContext:
          `Known user state (retrieved via StateJar handle ${retrieved.handle_used}): ` +
          `${JSON.stringify(retrieved.subset)}\n\nReply in plain conversational ` +
          'language. Never output JSON or internal state.',
        userMessage: text,
      })
    } catch (err) {
      const { message } = classifyError(err, ollamaBase)
      throw new Error(message)
    }
    const audited = await api('/audit/manual', {
      method: 'POST',
      body: {
        session_tag: session,
        handle_used: retrieved.handle_used,
        subset_keys: retrieved.metadata?.subset_keys || [],
        provider: 'ollama',
        model: bare,
      },
    }).catch(() => ({ audit_id: null }))
    return {
      response: result.text,
      audit_id: audited.audit_id,
      subset_keys: retrieved.metadata?.subset_keys || [],
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

  /* One ingest, tracked through the pipeline strip from the real response.
     Shared by the demo and by ordinary sends, so the strip means the same
     thing either way. Declared here but only ever called after render. */
  const runIngest = async (tag, text) => {
    pipe.begin('ingest')
    const ing = await api('/memory/ingest', {
      method: 'POST', body: { session_tag: tag, text },
    })
    applyIngest(ing)
    pipe.complete([
      ['ingest', { badge: 'sent', payload: text }],
      ['extract', {
        badge: `${countFields(ing.state)} fields`,
        payload: ing.state,
      }],
      ['canonicalize', {
        badge: 'sorted',
        payload: canonicalPreview(ing.state),
      }],
      ['handle', {
        badge: ing.handle.replace('shm_', '').slice(0, 8),
        payload: ing.handle,
      }],
      ['store', {
        badge: ing.parent_handle ? 'v+1' : 'v1',
        payload: {
          session_tag: tag,
          parent_handle: ing.parent_handle,
          conflicts: ing.conflicts || [],
        },
      }],
    ])
    return ing
  }

  const demoSteps = [
    // 1 — the brief. Five constraints a developer would otherwise re-paste.
    {
      before: () => {
        addMsg({ role: 'user', demo: true, content: DEMO_MSGS.brief })
        focusTab(0)
      },
      work: async (c) => {
        await runIngest(c.tagA, DEMO_MSGS.brief)
        await refreshVersions(c.tagA)
      },
      reply: DEMO_REPLIES.scaffold,
    },
    // 2 — the pain, side by side. No API call: this beat is the argument.
    {
      before: () => {
        addMsg({ role: 'compare', demo: true })
        addMsg({
          role: 'note', demo: true,
          content: 'Same conversation. One of them pays for the context twice.',
        })
      },
    },
    // 3 — the money shot: a brand-new session that still knows the spec.
    {
      before: (c) => {
        switchSession(c.tagB, { keep: true })
        addMsg({ role: 'user', demo: true, content: DEMO_MSGS.followUp })
      },
      work: async (c) => {
        pipe.begin('retrieve')
        const q = await demoQuery(c.tagB, DEMO_MSGS.followUp)
        setRetrieved(q)
        const keys = q.metadata.subset_keys || []
        const total = keys.length + (q.metadata.fields_dropped || 0)
        pipe.complete([
          ['retrieve', {
            badge: `${keys.length} of ${total} fields`,
            payload: { subset_keys: keys, subset: q.subset },
          }],
          ...(q.audit_id
            ? [['audit', { badge: 'logged', payload: { audit_id: q.audit_id } }]]
            : []),
        ])
        focusTab(1)
        setPulse((p) => p + 1)
      },
      reply: DEMO_REPLIES.pricing,
      note: "It never saw the first conversation. It didn't need to.",
    },
    // 4 — versioning: a new handle, the previous one still lit.
    {
      before: (c) => {
        switchSession(c.tagA, { keep: true })
        addMsg({ role: 'user', demo: true, content: DEMO_MSGS.recolor })
      },
      work: async (c) => {
        await runIngest(c.tagA, DEMO_MSGS.recolor)
        await refreshVersions(c.tagA)
        focusTab(2)
      },
      reply: DEMO_REPLIES.recolor,
    },
    // 5 — conflict preservation: both values kept, contradiction recorded.
    {
      before: () => {
        addMsg({ role: 'user', demo: true, content: DEMO_MSGS.uiLib })
      },
      work: async (c) => {
        await runIngest(c.tagA, DEMO_MSGS.uiLib)
        await refreshVersions(c.tagA)
        focusTab(0)
        setPulse((p) => p + 1)
      },
      reply: DEMO_REPLIES.uiLib,
    },
    // 6 — provenance.
    {
      work: async (c) => {
        pipe.begin('retrieve')
        const q = await demoQuery(c.tagA, DEMO_MSGS.followUp)
        const keys = q.metadata.subset_keys || []
        const total = keys.length + (q.metadata.fields_dropped || 0)
        pipe.complete([
          ['retrieve', {
            badge: `${keys.length} of ${total} fields`,
            payload: { subset_keys: keys, subset: q.subset },
          }],
          ['audit', { badge: 'logged', payload: { audit_id: q.audit_id } }],
        ])
        setNewAuditId(q.audit_id || null)
        await fetchAudit(c.tagA, auditScope)
        focusTab(3)
        setPulse((p) => p + 1)
      },
      reply: DEMO_REPLIES.audit,
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
        if (step.note) addMsg({ role: 'note', demo: true, content: step.note })
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
    // real measured average across this run's audited retrievals; stays null
    // (and the chip stays hidden) if no query ever reported a percentage
    const saved = demoSavedRef.current
    setDemoSummary(
      saved.length
        ? {
            turns: 6,
            savedPct: Math.round((saved.reduce((a, b) => a + b, 0) / saved.length) * 10) / 10,
          }
        : null,
    )
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
      autoTimerRef.current = setTimeout(() => advanceDemo(), DEMO_BEAT_PACE_MS)
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
    setDemoSummary(null)
    setNewAuditId(null)
    pipe.reset()
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
      <Pipeline stages={pipe.stages} travelling={pipe.travelling} />

      <div className="pg-cols">
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
            groups={groups}
            choice={modelChoice}
            customModel={customModel}
            customProvider={customProvider}
            onChoice={pickModel}
            onCustomChange={editCustomModel}
            onCustomProvider={editCustomProvider}
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
              <p>or brief it yourself: "Stack: React + Tailwind. Dark theme, brand color #E07856."</p>
              <p>then switch to a new session and ask: "Now add a pricing section."</p>
            </div>
          )}
          {messages.map((m, i) => {
            if (m.role === 'compare') return <CompareCard key={i} />
            if (m.role === 'note') {
              return <p className="pg-note" key={i}>{m.content}</p>
            }
            return (
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
            )
          })}
          {demoSummary && (
            <div className="demo-summary" role="status">
              <span className="demo-summary-num">{demoSummary.turns} turns</span>
              <span className="demo-summary-sep">·</span>
              <span className="demo-summary-num accent">
                {demoSummary.savedPct}% fewer prompt tokens
              </span>
              <span className="demo-summary-note">measured from this run's retrievals</span>
            </div>
          )}
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
                  <TierChips sources={extractionSource} origins={extractionOrigins} />
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
                  <StateTree state={state} changed={changed} origins={extractionOrigins} />
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
            <AuditTimeline
              entries={audit}
              scope={auditScope}
              onScope={setAuditScope}
              onCopyHandle={copyHandle}
              highlightId={newAuditId}
            />
          )}
        </div>
      </div>
      </div>
    </div>
  )
}
