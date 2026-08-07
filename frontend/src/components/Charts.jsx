/* Dashboard charts, drawn as inline SVG.

   No charting library. Recharts is the usual pick and costs ~100 kB gzipped —
   roughly double this app's entire main bundle — to draw three shapes that are
   a few dozen lines of SVG each. It would also arrive with its own type scale
   and default palette to override on every chart. Hand-rolled is genuinely the
   lightest option here, and it inherits the page's tokens for free.

   The palette is fixed and validated, not chosen by eye: terracotta, blue,
   plum, green all pass the lightness, chroma, contrast and colour-vision
   checks against a white card. The worst colour-blind pair (terracotta/green)
   sits in the marginal band, which is legal only with a second channel, so
   every series is also named in a legend, carries a direct value label, and is
   separated by a 2 px surface gap. Nothing here is identified by colour alone,
   and every chart has a table underneath it. */

import { useState } from 'react'

export const SERIES = ['#E07856', '#2C74D6', '#A8478F', '#4E9A1E']
const MUTED = '#8A8A9A'          // superseded: deliberately recessive
const LINE = '#E8E3DC'
const INK_SOFT = '#4A4A5E'
const INK_FAINT = '#8A8A9A'
const MAX_SERIES = 3             // a 4th reason folds into "Other", never a new hue
/* Small counts beside a large one round to nothing: a day with 2 declines next
   to a day with 192 computes to under a pixel and disappears. The bar is held
   at this height so it stays visible, which means the smallest bars are no
   longer to scale — so every bar carries its number, and the caption says so.
   The alternative, a log axis, is only honest if it is labelled and is harder
   to read at a glance; dropping the outlier would not be honest at all. */
const MIN_BAR = 6

/* A rect with only some corners rounded, so the rounding lands on the data end
   and never on the baseline. */
function bar(x, y, w, h, r, { tl, tr, br, bl } = {}) {
  const rr = Math.max(0, Math.min(r, w / 2, h / 2))
  return [
    `M${x + (tl ? rr : 0)},${y}`,
    `H${x + w - (tr ? rr : 0)}`, tr ? `A${rr},${rr} 0 0 1 ${x + w},${y + rr}` : '',
    `V${y + h - (br ? rr : 0)}`, br ? `A${rr},${rr} 0 0 1 ${x + w - rr},${y + h}` : '',
    `H${x + (bl ? rr : 0)}`, bl ? `A${rr},${rr} 0 0 1 ${x},${y + h - rr}` : '',
    `V${y + (tl ? rr : 0)}`, tl ? `A${rr},${rr} 0 0 1 ${x + rr},${y}` : '',
    'Z',
  ].join(' ')
}

function useTip() {
  const [tip, setTip] = useState(null)
  const node = tip && (
    <div className="chart-tip" style={{ left: tip.x, top: tip.y }} role="status">
      {tip.rows.map((r) => <div key={r}>{r}</div>)}
    </div>
  )
  const bind = (rows) => ({
    onMouseMove: (e) => {
      const box = e.currentTarget.closest('.chart-wrap').getBoundingClientRect()
      setTip({ x: e.clientX - box.left + 12, y: e.clientY - box.top + 12, rows })
    },
    onMouseLeave: () => setTip(null),
  })
  return [node, bind]
}

function Legend({ items }) {
  return (
    <ul className="chart-legend">
      {items.map(({ label, color }) => (
        <li key={label}>
          <span className="chart-swatch" style={{ background: color }} aria-hidden="true" />
          {label}
        </li>
      ))}
    </ul>
  )
}

function Table({ head, rows, caption }) {
  return (
    <details className="chart-table">
      <summary>Show the numbers</summary>
      <table>
        <caption className="sr-only">{caption}</caption>
        <thead><tr>{head.map((h) => <th key={h} scope="col">{h}</th>)}</tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r[0]}>
              <th scope="row">{r[0]}</th>
              {r.slice(1).map((c, i) => <td key={i}>{c}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  )
}

/* ---- 1. Fields by namespace, active vs superseded ----------------------- */

export function NamespaceChart({ data }) {
  const [tip, bind] = useTip()
  const rows = data.filter((d) => d.active + d.superseded > 0)
  if (!rows.length) return null

  const max = Math.max(...rows.map((d) => d.active + d.superseded))
  const ROW = 26, GAP = 12, LABEL = 96, PAD = 40
  const h = rows.length * (ROW + GAP)
  /* Sized in real pixels rather than stretched to the card. An SVG scaled to
     its container scales its *text* too, which made 12px labels render at 28px
     on the widest chart. The wrapper scrolls instead. */
  const W = 392, plot = W - LABEL - PAD

  return (
    <figure className="chart-fig">
      <figcaption>
        <h3>Fields by namespace</h3>
        <p className="page-sub">
          One field holds one value. A replaced value leaves active state
          entirely and survives only as history — that is the superseded bar.
        </p>
      </figcaption>
      <Legend items={[
        { label: 'Active', color: SERIES[0] },
        { label: 'Superseded', color: MUTED },
      ]} />
      <div className="chart-wrap">
        {tip}
        <svg viewBox={`0 0 ${W} ${h}`} width={W} height={h} className="chart-svg"
             role="img"
             aria-label={`Fields by namespace across ${rows.length} namespaces`}>
          {rows.map((d, i) => {
            const y = i * (ROW + GAP)
            const total = d.active + d.superseded
            const aw = max ? (d.active / max) * plot : 0
            const sw = max ? (d.superseded / max) * plot : 0
            const only = d.superseded === 0
            return (
              <g key={d.namespace}>
                <text x={LABEL - 10} y={y + ROW / 2 + 4} textAnchor="end"
                      className="chart-cat">{d.namespace}</text>
                {d.active > 0 && (
                  <path d={bar(LABEL, y, aw, ROW, 4,
                               { tr: only, br: only })} fill={SERIES[0]}
                        {...bind([`${d.namespace}`, `Active: ${d.active}`])} />
                )}
                {d.superseded > 0 && (
                  /* 2px surface gap so the two segments never read as one */
                  <path d={bar(LABEL + aw + 2, y, Math.max(0, sw - 2), ROW, 4,
                               { tr: true, br: true })} fill={MUTED}
                        {...bind([`${d.namespace}`, `Superseded: ${d.superseded}`])} />
                )}
                <text x={LABEL + aw + sw + 8} y={y + ROW / 2 + 4}
                      className="chart-val">{total}</text>
              </g>
            )
          })}
        </svg>
      </div>
      <Table
        caption="Active and superseded field counts per namespace"
        head={['Namespace', 'Active', 'Superseded']}
        rows={rows.map((d) => [d.namespace, d.active, d.superseded])}
      />
    </figure>
  )
}

/* ---- 2. Declines by reason over time ------------------------------------ */

export function DeclineChart({ declines }) {
  const [tip, bind] = useTip()
  const buckets = declines?.buckets || []
  if (!buckets.length) return null

  // Top reasons keep a fixed hue; the tail folds into one grey "Other" rather
  // than generating a 5th colour nobody can distinguish.
  const top = (declines.reasons || []).slice(0, MAX_SERIES)
  const keyOf = (r) => (top.includes(r) ? r : 'Other')
  const series = [...top, ...(declines.reasons.length > top.length ? ['Other'] : [])]
  const colorOf = (r) => (r === 'Other' ? MUTED : SERIES[top.indexOf(r)])

  const folded = buckets.map((b) => {
    const counts = {}
    Object.entries(b.counts).forEach(([r, n]) => {
      counts[keyOf(r)] = (counts[keyOf(r)] || 0) + n
    })
    return { date: b.date, counts, total: Object.values(counts).reduce((a, c) => a + c, 0) }
  })

  const max = Math.max(...folded.map((b) => b.total))
  /* A fixed slot rather than dividing the card between however many days there
     happen to be: two buckets across a full-width chart marooned one bar at
     each end with nothing between them. */
  const H = 190, PAD_B = 32, PAD_T = 26, slot = 66
  const W = Math.max(198, folded.length * slot)
  const bw = 34
  const PLOT = H - PAD_B - PAD_T

  /* Height for one segment, floored so a count of 1 beside a count of 192 is
     still something you can see and hover. The floor is applied per segment
     and the stack is then clamped to the plot, so a tall bar cannot be pushed
     off the top by the floors underneath it. */
  const heightOf = (n) => (n > 0 ? Math.max(MIN_BAR, (n / max) * PLOT) : 0)

  return (
    <figure className="chart-fig">
      <figcaption>
        <h3>Declines by reason</h3>
        <p className="page-sub">
          What the extractor refused, and why. Each refusal is counted on the
          turn that produced it. Days with no declines are left off the axis;
          a bar too small to see is held at a minimum height, so read the
          number above it rather than the height.
        </p>
      </figcaption>
      <Legend items={series.map((r) => ({ label: r, color: colorOf(r) }))} />
      <div className="chart-wrap">
        {tip}
        <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} className="chart-svg"
             role="img"
             aria-label={`Declines by reason across ${folded.length} days`}>
          <line x1="0" y1={H - PAD_B} x2={W} y2={H - PAD_B} stroke={LINE} strokeWidth="1" />
          {folded.map((b, i) => {
            const cx = i * slot + slot / 2
            const present = series.filter((r) => b.counts[r])
            const raw = present.map((r) => heightOf(b.counts[r]))
            const stack = raw.reduce((a, c) => a + c, 0)
            const scale = stack > PLOT ? PLOT / stack : 1
            let y = H - PAD_B
            return (
              <g key={b.date}>
                {present.map((r, j) => {
                  const bh = raw[j] * scale
                  const isTop = j === present.length - 1
                  y -= bh
                  const drawn = j === 0 ? bh : Math.max(1, bh - 2)
                  return (
                    <path key={r}
                          d={bar(cx - bw / 2, y, bw, drawn, 4,
                                 { tl: isTop, tr: isTop })}
                          fill={colorOf(r)}
                          {...bind([b.date, `${r}: ${b.counts[r]}`,
                                    `day total: ${b.total}`])} />
                  )
                })}
                {/* every bar carries its number, because the smallest ones are
                    held above their true height to stay visible */}
                <text x={cx} y={y - 7} textAnchor="middle" className="chart-val">
                  {b.total}
                </text>
                <text x={cx} y={H - PAD_B + 18} textAnchor="middle" className="chart-cat">
                  {b.date.slice(5)}
                </text>
              </g>
            )
          })}
        </svg>
      </div>
      <Table
        caption="Declines by reason and day"
        head={['Day', ...series, 'Total']}
        rows={folded.map((b) => [b.date, ...series.map((r) => b.counts[r] || 0), b.total])}
      />
    </figure>
  )
}

/* ---- 3. Handle lineage --------------------------------------------------- */

/* Session tags used to be drawn into a fixed left gutter, one row per session,
   and an over-long tag clipped there — "spanfix-1785910318" rendering as
   "fix-1785910318", which reads as a different session rather than as a
   truncation. There is no gutter now: one session is shown at a time and its
   tag is the full string in the selector, so the clipping problem is gone
   rather than mitigated.

   What changed between two consecutive states, from the field count alone.
   The payload carries `fields` and `declines` per version and nothing else, so
   this reports exactly what those two support and hedges where they do not:
   a count that did not move means a value was replaced in place OR nothing new
   was extracted, and there is no way to tell which from here. Claiming
   "superseded" on that would be a guess rendered as a fact, on the one chart
   whose subject is that we do not guess. */
const STEP_KINDS = {
  start: { color: SERIES[0], label: 'first state' },
  add: { color: SERIES[0], label: 'field added' },
  drop: { color: SERIES[2], label: 'field left active state' },
  same: { color: MUTED, label: 'no new field' },
}

function stepsOf(versions) {
  return versions.map((v, i) => {
    const prev = versions[i - 1]
    const declined = v.declines > 0
    if (!prev) return { kind: 'start', mark: `${v.fields}`, declined }
    const delta = v.fields - prev.fields
    if (delta > 0) return { kind: 'add', mark: `+${delta}`, declined }
    if (delta < 0) return { kind: 'drop', mark: `${delta}`, declined }
    return { kind: 'same', mark: '=', declined }
  })
}

const lastAt = (s) => s.versions[s.versions.length - 1].created_at || ''

export function LineageChart({ lineage }) {
  const [tip, bind] = useTip()
  const chains = (lineage || []).filter((s) => s.versions.length)
  const recent = [...chains].sort((a, b) => lastAt(b).localeCompare(lastAt(a)))
  const [picked, setPicked] = useState('')
  if (!chains.length) return null

  /* One session, not all of them. Twenty near-identical two-dot rows stacked
     down the page cost a screenful and proved nothing that one detailed chain
     does not prove better; the rest move behind the selector. */
  const chain = recent.find((s) => s.session_tag === picked) || recent[0]
  const steps = stepsOf(chain.versions)
  const kinds = [...new Set(steps.map((s) => s.kind))]

  const STEP = 62, R = 8, PAD_X = 26, MID = 52
  const W = PAD_X * 2 + Math.max(1, chain.versions.length - 1) * STEP
  const H = 96

  const handles = chains.reduce((a, s) => a + s.versions.length, 0)
  const deepest = Math.max(...chains.map((s) => s.versions.length))

  return (
    <figure className="chart-fig">
      <figcaption>
        <h3>Handle lineage</h3>
        <p className="page-sub">
          Every turn seals a new state and points it at its parent. Nothing is
          edited in place, so the chain is the whole history — each dot is one
          content-addressed handle, marked with what changed at that step.
        </p>
      </figcaption>

      <p className="lin-summary">
        <b>{handles}</b> handles · <b>{chains.length}</b> session{chains.length === 1 ? '' : 's'}
        {' '}· deepest chain <b>{deepest}</b>
      </p>

      <div className="lin-controls">
        <label className="sr-only" htmlFor="lin-session">Session</label>
        <select id="lin-session" className="lin-select"
                value={chain.session_tag}
                onChange={(e) => setPicked(e.target.value)}>
          {recent.map((s) => (
            <option key={s.session_tag} value={s.session_tag}>
              {s.session_tag} · {s.versions.length} handle{s.versions.length === 1 ? '' : 's'}
            </option>
          ))}
        </select>
        <span className="lin-when">
          last sealed {(lastAt(chain) || '').replace('T', ' ').slice(0, 16) || '—'}
        </span>
      </div>

      {/* `start` is deliberately absent: it shares terracotta with `add`, and
          two legend rows carrying the same swatch read as a rendering bug. The
          first dot is self-evidently the first, its mark is the starting field
          count rather than a delta, and its tooltip names it. */}
      <Legend items={kinds.filter((k) => k !== 'start').map((k) => ({
        label: STEP_KINDS[k].label, color: STEP_KINDS[k].color,
      }))} />

      {/* `chart-scroll` opts this one out of the mobile scale-to-fit: a 16-dot
          chain squeezed into a phone card is a 0.3 scale, which is ~4px type.
          A long chain scrolls; it does not shrink. */}
      <div className="chart-wrap chart-scroll">
        {tip}
        <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} className="chart-svg"
             role="img"
             aria-label={`Handle chain for session ${chain.session_tag}, `
                         + `${chain.versions.length} states`}>
          {chain.versions.length > 1 && (
            <line x1={PAD_X} y1={MID} x2={W - PAD_X} y2={MID}
                  stroke={LINE} strokeWidth="2" />
          )}
          {chain.versions.map((v, i) => {
            const step = steps[i]
            const cx = PAD_X + i * STEP
            return (
              <g key={v.handle}
                 {...bind([
                   `v${v.version} · ${STEP_KINDS[step.kind].label}`,
                   v.handle,
                   `${v.fields} field${v.fields === 1 ? '' : 's'} active`
                     + (step.declined ? ` · ${v.declines} declined` : ''),
                   (v.created_at || '').replace('T', ' ').slice(0, 16),
                 ])}>
                <text x={cx} y={MID - 20} textAnchor="middle" className="chart-val">
                  {step.mark}
                </text>
                {/* 2px surface ring so adjacent dots stay countable */}
                <circle cx={cx} cy={MID} r={R + 2} fill="#fff" />
                <circle cx={cx} cy={MID} r={R} fill={STEP_KINDS[step.kind].color} />
                {step.declined && (
                  <circle cx={cx + R + 1} cy={MID - R - 1} r="3" fill={SERIES[1]}>
                    <title>a value was declined on this turn</title>
                  </circle>
                )}
                <text x={cx} y={MID + 26} textAnchor="middle" className="chart-cat">
                  v{v.version}
                </text>
              </g>
            )
          })}
        </svg>
      </div>

      <Table
        caption="Every session, its chain depth and its latest handle"
        head={['Session', 'Handles', 'Latest handle', 'Fields']}
        rows={recent.map((s) => [
          s.session_tag,
          s.versions.length,
          s.versions[s.versions.length - 1].handle.slice(0, 18) + '…',
          s.versions[s.versions.length - 1].fields,
        ])}
      />
    </figure>
  )
}

export function hasInsight(ins) {
  if (!ins) return false
  return Boolean(
    ins.namespaces?.length || ins.declines?.buckets?.length || ins.lineage?.length,
  )
}
