import { useCallback, useEffect, useRef, useState } from 'react'

/* Live view of the seven stages a message passes through inside StateJar.
   Every badge and popover below is filled from a real /memory/ingest or
   /memory/query response — nothing here runs on a timer of its own, so the
   strip can never claim a stage the panels did not actually reach. The only
   timed part is the reveal stagger, which paces stages that all completed
   in the same round trip so the eye can follow them. */

export const PIPELINE_STAGES = [
  { key: 'ingest', label: 'Ingest' },
  { key: 'extract', label: 'Extract' },
  { key: 'canonicalize', label: 'Canonicalize' },
  { key: 'handle', label: 'Handle' },
  { key: 'store', label: 'Store' },
  { key: 'retrieve', label: 'Retrieve' },
  { key: 'audit', label: 'Audit' },
]

const IDLE = Object.fromEntries(PIPELINE_STAGES.map((s) => [s.key, { status: 'idle' }]))

const reduceMotion = () =>
  typeof window !== 'undefined' &&
  window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

/* Same shape the backend hashes: keys sorted at every level, no whitespace.
   Serialising the state the API returned reproduces the canonical string the
   handle was computed from, so the popover shows the real bytes. */
export function canonicalPreview(value) {
  const sorted = (v) => {
    if (Array.isArray(v)) return v.map(sorted)
    if (v && typeof v === 'object') {
      return Object.keys(v).sort().reduce((o, k) => ((o[k] = sorted(v[k])), o), {})
    }
    return v
  }
  return JSON.stringify(sorted(value))
}

const META_KEYS = new Set(['schema_version', 'norm_version', 'parent_handle'])

/* Leaf fields in a state, ignoring the version markers the canonicalizer adds. */
export function countFields(state) {
  if (!state || typeof state !== 'object') return 0
  let n = 0
  for (const [k, v] of Object.entries(state)) {
    if (META_KEYS.has(k)) continue
    if (Array.isArray(v)) n += v.length
    else if (v && typeof v === 'object') n += Object.keys(v).length
    else n += 1
  }
  return n
}

export function usePipeline() {
  const [stages, setStages] = useState(IDLE)
  const [travelling, setTravelling] = useState(null)
  const timers = useRef([])

  const clearTimers = useCallback(() => {
    timers.current.forEach(clearTimeout)
    timers.current = []
  }, [])

  useEffect(() => clearTimers, [clearTimers])

  const reset = useCallback(() => {
    clearTimers()
    setStages(IDLE)
    setTravelling(null)
  }, [clearTimers])

  /* Mark a stage in flight — called before the request leaves. */
  const begin = useCallback((key) => {
    setStages((s) => ({ ...s, [key]: { ...s[key], status: 'active' } }))
    setTravelling(key)
  }, [])

  /* Reveal stages that a single response proved complete.
     entries: [key, { badge, payload }][] */
  const complete = useCallback((entries) => {
    if (!entries.length) return
    const gap = reduceMotion() ? 0 : 170
    entries.forEach(([key, data], i) => {
      timers.current.push(setTimeout(() => {
        setTravelling(key)
        setStages((s) => {
          const next = { ...s, [key]: { status: 'active', ...data } }
          const prev = entries[i - 1]?.[0]
          if (prev) next[prev] = { ...s[prev], status: 'done' }
          return next
        })
      }, i * gap))
    })
    timers.current.push(setTimeout(() => {
      const last = entries[entries.length - 1][0]
      setStages((s) => ({ ...s, [last]: { ...s[last], status: 'done' } }))
      setTravelling(null)
    }, entries.length * gap))
  }, [])

  /* Put the strip back exactly as a previous turn left it, with no reveal
     stagger — a rehydrated session is showing history, not a live run, and
     replaying the animation would claim stages are happening now. */
  const restore = useCallback((saved) => {
    clearTimers()
    setTravelling(null)
    setStages(saved && typeof saved === 'object' ? { ...IDLE, ...saved } : IDLE)
  }, [clearTimers])

  return { stages, travelling, reset, begin, complete, restore }
}

function Payload({ data }) {
  if (data == null) return null
  const text = typeof data === 'string' ? data : JSON.stringify(data, null, 2)
  return <pre className="pipe-pop-body mono">{text}</pre>
}

export default function Pipeline({ stages, travelling }) {
  const [open, setOpen] = useState(null)

  // click-away and Escape, so a popover can never trap a presenter mid-demo
  useEffect(() => {
    if (!open) return
    const close = (e) => {
      if (e.key === 'Escape' || !e.target.closest?.('.pipe-stage')) setOpen(null)
    }
    document.addEventListener('keydown', close)
    document.addEventListener('pointerdown', close)
    return () => {
      document.removeEventListener('keydown', close)
      document.removeEventListener('pointerdown', close)
    }
  }, [open])

  return (
    <div className="pipe" role="group" aria-label="StateJar memory pipeline">
      <ol className="pipe-track">
        {PIPELINE_STAGES.map((stage, i) => {
          const st = stages[stage.key] || { status: 'idle' }
          const done = st.status === 'done'
          return (
            <li
              key={stage.key}
              className={
                `pipe-stage is-${st.status}` +
                (travelling === stage.key ? ' is-travelling' : '')
              }
            >
              {i > 0 && (
                <span className="pipe-link" aria-hidden="true">
                  <i className="pipe-travel" />
                </span>
              )}
              <button
                type="button"
                className="pipe-node"
                aria-label={`${stage.label}: ${st.status}${st.badge ? `, ${st.badge}` : ''}`}
                aria-expanded={open === stage.key}
                disabled={!done || st.payload == null}
                onClick={() => setOpen(open === stage.key ? null : stage.key)}
              >
                <span aria-hidden="true">{done ? '✓' : ''}</span>
              </button>
              <span className="pipe-label mono">{stage.label}</span>
              <span className="pipe-badge mono">{st.badge || ''}</span>

              {open === stage.key && st.payload != null && (
                <div className="pipe-pop" role="dialog" aria-label={`${stage.label} detail`}>
                  <div className="pipe-pop-head mono">{stage.label}</div>
                  <Payload data={st.payload} />
                </div>
              )}
            </li>
          )
        })}
      </ol>
    </div>
  )
}
