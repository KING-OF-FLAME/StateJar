import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../lib/api.js'
import Markdown from './Markdown.jsx'

/* The 17-turn relief-coordination demo.
 *
 * Every turn is a real /memory/ingest plus a real /memory/query — the state,
 * the handle and the retrieved subset are all live. Only the assistant's
 * replies are scripted, so the run needs no provider key and is identical on
 * a brand-new account.
 *
 * Phrasing note: several turns are worded more like a form than a sentence
 * ("Truck count is 3" rather than "we have 3 trucks"). That is deliberate.
 * The extractor is frozen, so where a natural phrasing did not survive it,
 * the turn was rewritten rather than the pipeline — see the report.
 */
export const TURNS = [
  { user: 'Relief operation for Wayanad district. Displaced families is 4,200.',
    reply: 'Logged — Wayanad district relief, 4,200 families displaced.' },
  { user: 'Truck count is 3, capacity per truck is 8 tonnes.',
    reply: 'Noted: 3 trucks at 8 tonnes each, 24 tonnes of capacity.' },
  { user: 'First convoy departs before 14 August.',
    reply: 'First convoy departure recorded for before 14 August.' },
  { user: 'Name: Meera Nair, email: meera@reliefnet.org',
    reply: 'Coordinator recorded: Meera Nair, meera@reliefnet.org.' },
  { user: 'Sanctioned budget is ₹18 lakh.',
    reply: 'Sanctioned budget of ₹18 lakh recorded.' },
  { user: 'Family kit weight is 12 kg, kit invoice is ₹850.',
    reply: 'Kit spec noted: 12 kg per kit, ₹850 per kit.' },
  { user: 'Purification tablets is 40,000 units.',
    reply: '40,000 purification tablet units logged.' },
  { user: 'Update: truck count is now 5.',
    reply: 'Updated from 3 trucks to 5 trucks.', marker: 'update' },
  { user: 'Daily report hour is 18.',
    reply: 'Daily report deadline set to 18:00.' },
  { user: 'Medical camp doctors is 3.',
    reply: 'Medical camp staffed with 3 doctors.' },
  { user: 'Actually cancel the purification tablets, state supply already covered it.',
    reply: 'Purification tablets retracted — removed from active state.',
    marker: 'retracted' },
  { user: 'Freight invoice is ₹43,200. Average run is 180 km.',
    reply: 'Freight invoice ₹43,200 over a 180 km average run recorded.' },
  { user: 'Correction: budget is now ₹22 lakh.',
    reply: 'Budget corrected from ₹18 lakh to ₹22 lakh.', marker: 'corrected' },
  { user: 'Second convoy departs 19 August.',
    reply: 'Second convoy on 19 August recorded.' },
  { user: 'Tarpaulin count is 600.',
    reply: '600 tarpaulins added.' },
  { user: 'Prefer WhatsApp for daily updates.',
    reply: 'Update channel switched to WhatsApp.' },
  { user: 'How many family kits can we cover with the current budget?',
    reply: 'At **₹850** per kit against a **₹22 lakh** budget, you can cover about '
      + '**2,588 kits** — roughly 62% of the 4,200 displaced families.\n\n'
      + 'Answered from retrieved state alone; the transcript was never replayed.',
    payoff: true },
]

const PACE_MS = 2500
const CHARS_PER_TOKEN = 4
const DEMO_SESSION = 'demo-relief'

const tokens = (text) => Math.round(text.length / CHARS_PER_TOKEN)
const fmt = (n) => n.toLocaleString()

/* Fields live in active state, across every namespace the API returns. */
function countFields(state) {
  if (!state) return 0
  const SECTIONS = ['facts', 'preferences', 'decisions', 'constraints', 'goals', 'dynamic']
  let n = 0
  const walk = (node) => {
    if (!node || typeof node !== 'object') { n += 1; return }
    if ('value' in node || 'iso' in node) { n += 1; return }
    Object.values(node).forEach(walk)
  }
  SECTIONS.forEach((s) => Object.values(state[s] || {}).forEach(walk))
  return n
}

/* The curve is the argument. A final number alone hides the shape, and the
   shape is what says "this diverges as the conversation grows". */
function Sparkline({ points }) {
  if (points.length < 2) return <div className="spark-empty" />
  const lo = Math.min(0, ...points)
  const hi = Math.max(0, ...points)
  const span = hi - lo || 1
  const W = 220
  const H = 44
  const x = (i) => (i / (points.length - 1)) * W
  const y = (v) => H - ((v - lo) / span) * H
  const path = points.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')
  const zero = y(0)
  return (
    <svg className="spark" viewBox={`0 0 ${W} ${H}`} width={W} height={H}
         role="img" aria-label="Token saving per turn">
      {lo < 0 && (
        <line x1="0" y1={zero} x2={W} y2={zero} className="spark-zero" />
      )}
      <path d={path} className="spark-line" />
      <circle cx={x(points.length - 1)} cy={y(points[points.length - 1])} r="3"
              className="spark-dot" />
    </svg>
  )
}

/* The baseline is stated everywhere a percentage is. A bare percentage with
   no stated comparison is not defensible under questioning. */
function SavingsLine({ sent, replay, pct, mode }) {
  const low = pct < 25
  return (
    <div className="savings">
      <span className="savings-main">
        Sent <b>{fmt(sent)}</b> tokens · a full-transcript replay would send{' '}
        <b>{fmt(replay)}</b> ·{' '}
        <b className={pct >= 0 ? 'savings-pos' : 'savings-neg'}>
          {pct >= 0 ? `${pct}% saved` : `${Math.abs(pct)}% more`}
        </b>
      </span>
      {low && (
        <span className="savings-why">
          {mode === 'full_state'
            ? 'Full state sent — small enough that selection isn’t needed, so '
              + 'StateJar is sending the whole jar. The saving appears once the '
              + 'conversation outgrows the state.'
            : 'Early turns save little: the state and the transcript are still '
              + 'nearly the same size.'}
        </span>
      )}
    </div>
  )
}

export default function ReliefDemo({ onState, onHandle, onClose }) {
  const [idx, setIdx] = useState(-1)        // -1 = not started
  const [playing, setPlaying] = useState(false)
  const [msgs, setMsgs] = useState([])
  const [curve, setCurve] = useState([])
  const [fields, setFields] = useState(0)
  const [last, setLast] = useState(null)    // {sent, replay, pct, mode}
  const [done, setDone] = useState(false)
  const [handle, setHandle] = useState(null)
  const [error, setError] = useState('')

  const timer = useRef(null)
  // the index a click handler should trust: `idx` in a closure can be a
  // render behind if a turn finished between render and click
  const idxRef = useRef(-1)
  const transcript = useRef([])
  const busy = useRef(false)
  const scroller = useRef(null)

  const clearTimer = () => {
    if (timer.current) { clearTimeout(timer.current); timer.current = null }
  }

  /* One turn: a real ingest, a real query, then the scripted reply. */
  const runTurn = useCallback(async (i) => {
    const turn = TURNS[i]
    transcript.current.push(turn.user, turn.reply)
    setMsgs((m) => [...m, { role: 'user', text: turn.user, marker: turn.marker }])

    let state = null
    let sent = 0
    let mode = ''
    try {
      const ing = await api('/memory/ingest', {
        method: 'POST',
        body: { session_tag: DEMO_SESSION, text: turn.user },
      })
      state = ing.state
      setHandle(ing.handle)
      onHandle?.(ing.handle)
      onState?.(ing.state)

      const q = await api('/memory/query', {
        method: 'POST',
        body: { session_tag: DEMO_SESSION, query: turn.user, audit: true },
      })
      sent = tokens(JSON.stringify(q.subset))
      mode = q.metadata?.retrieval_mode || ''
    } catch (err) {
      setError(err.message)
    }

    const replay = tokens(transcript.current.join('\n'))
    // Unchanged measurement: what StateJar actually disclosed, against what a
    // memoryless system would have replayed. Nothing here is scaled or floored.
    const pct = replay ? Math.round((1 - sent / replay) * 1000) / 10 : 0

    setFields(countFields(state))
    setCurve((c) => [...c, pct])
    setLast({ sent, replay, pct, mode })
    setMsgs((m) => [...m, { role: 'assistant', text: turn.reply, payoff: turn.payoff }])
  }, [onHandle, onState])

  /* Autoplay loop. Guarded so a Pause mid-request cannot double-fire. */
  useEffect(() => {
    if (!playing || done) return undefined
    if (idxRef.current >= TURNS.length - 1) {
      setPlaying(false); setDone(true); return undefined
    }
    clearTimer()
    timer.current = setTimeout(async () => {
      if (busy.current) return
      busy.current = true
      const next = idxRef.current + 1
      await runTurn(next)
      idxRef.current = next
      setIdx(next)
      busy.current = false
    }, idxRef.current < 0 ? 300 : PACE_MS)
    return clearTimer
  }, [playing, idx, done, runTurn])

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: 'smooth' })
  }, [msgs])

  useEffect(() => clearTimer, [])

  const start = () => { setPlaying(true); setError('') }
  const pause = () => { setPlaying(false); clearTimer() }

  const restart = async () => {
    clearTimer()
    setPlaying(false)
    setDone(false)
    idxRef.current = -1
    setIdx(-1)
    setMsgs([])
    setCurve([])
    setFields(0)
    setLast(null)
    setHandle(null)
    setError('')
    transcript.current = []
    // a fresh session tag each run, so a restart never rides on the previous
    // run's state and never touches the user's own sessions
    await new Promise((r) => setTimeout(r, 60))
    setPlaying(true)
  }

  const skipToEnd = async () => {
    clearTimer()
    setPlaying(false)
    // Wait for an in-flight turn rather than bailing on it. Returning early
    // here left the run stalled with no timer and no end card — Skip looked
    // like it did nothing, which on stage is worse than a slow demo.
    while (busy.current) {
      await new Promise((r) => setTimeout(r, 60))   // eslint-disable-line no-await-in-loop
    }
    busy.current = true
    try {
      // `idx` is read once, but every later index comes from the loop, so a
      // stale closure cannot skip or repeat a turn
      for (let i = idxRef.current + 1; i < TURNS.length; i += 1) {
        await runTurn(i)        // eslint-disable-line no-await-in-loop
        idxRef.current = i
        setIdx(i)
      }
    } finally {
      busy.current = false
    }
    setDone(true)
  }

  const progress = idx < 0 ? 0 : Math.round(((idx + 1) / TURNS.length) * 100)

  return (
    <div className="relief-demo">
      <div className="rd-bar">
        <span className="rd-title">
          Relief coordination · <span className="rd-session mono">{DEMO_SESSION}</span>
        </span>
        <span className="rd-progress">
          turn {Math.max(idx + 1, 0)} / {TURNS.length}
        </span>
        <div className="rd-controls">
          {!playing && !done && idx < 0 && (
            <button className="btn btn-primary pg-mini" onClick={start}>▶ Play</button>
          )}
          {!playing && !done && idx >= 0 && (
            <button className="btn btn-primary pg-mini" onClick={start}>▶ Resume</button>
          )}
          {playing && (
            <button className="btn btn-ghost pg-mini" onClick={pause}>❚❚ Pause</button>
          )}
          {!done && (
            <button className="btn btn-ghost pg-mini" onClick={skipToEnd}>⏭ Skip to end</button>
          )}
          <button className="btn btn-ghost pg-mini" onClick={restart}>↺ Restart</button>
          {onClose && (
            <button className="btn btn-ghost pg-mini" onClick={onClose}>✕</button>
          )}
        </div>
      </div>

      <div className="rd-progressbar"><div style={{ width: `${progress}%` }} /></div>

      <div className="rd-metrics">
        <div className="rd-metric">
          <span className="rd-metric-num">{fields}</span>
          <span className="rd-metric-label">fields in active state</span>
        </div>
        <div className="rd-metric rd-curve">
          <Sparkline points={curve} />
          <span className="rd-metric-label">token saving per turn</span>
        </div>
      </div>

      {last && <SavingsLine {...last} />}
      {error && <p className="auth-error">{error}</p>}

      <div className="rd-chat" ref={scroller}>
        {msgs.map((m, i) => (
          <div key={i} className={`pg-msg ${m.role}`}>
            <span className="pg-role">
              {m.role === 'user' ? 'coordinator' : 'assistant'}
              {m.marker && <span className={`rd-marker rd-${m.marker}`}>{m.marker}</span>}
            </span>
            <div className={`pg-bubble${m.payoff ? ' rd-payoff' : ''}`}>
              {m.role === 'assistant' ? <Markdown>{m.text}</Markdown> : m.text}
            </div>
          </div>
        ))}
      </div>

      {done && last && (
        <div className="rd-endcard">
          <h4>Run complete</h4>
          <div className="rd-end-grid">
            <div><b>{TURNS.length}</b><span>turns</span></div>
            <div><b>{fields}</b><span>fields in active state</span></div>
            <div>
              <b className={last.pct >= 0 ? 'savings-pos' : 'savings-neg'}>
                {last.pct >= 0 ? `${last.pct}%` : `−${Math.abs(last.pct)}%`}
              </b>
              <span>{last.pct >= 0 ? 'tokens saved' : 'more than replay'}</span>
            </div>
          </div>
          <p className="rd-end-baseline">
            Final turn sent <b>{fmt(last.sent)}</b> tokens; a full-transcript
            replay would have sent <b>{fmt(last.replay)}</b>.
          </p>
          {last.pct < 70 && (
            <p className="rd-end-note">
              Below the 70% mark, and honestly so: at {fields} fields the state
              is still under the full-state threshold, so every turn sends the
              whole jar. Selective retrieval — and the saving — engages once the
              conversation outgrows the state.
            </p>
          )}
          {handle && (
            <p className="rd-end-handle">
              Session handle <code className="mono">{handle}</code>
              <span className="rd-end-hint">
                Paste it into a new session with a different model to restore
                this state.
              </span>
            </p>
          )}
        </div>
      )}
    </div>
  )
}
