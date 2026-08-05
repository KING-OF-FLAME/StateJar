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
const MAX_SERIES = 4             // a 5th reason folds into "Other", never a new hue

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
  const H = 190, PAD_B = 32, PAD_T = 20, slot = 66
  const W = Math.max(198, folded.length * slot)
  const bw = 34

  return (
    <figure className="chart-fig">
      <figcaption>
        <h3>Declines by reason</h3>
        <p className="page-sub">
          What the extractor refused, and why. Each refusal is counted on the
          turn that produced it — the reason is recorded rather than guessed at.
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
            let y = H - PAD_B
            const present = series.filter((r) => b.counts[r])
            return (
              <g key={b.date}>
                {present.map((r, j) => {
                  const bh = ((b.counts[r]) / max) * (H - PAD_B - PAD_T)
                  const isTop = j === present.length - 1
                  y -= bh
                  const drawn = j === 0 ? bh : Math.max(0, bh - 2)
                  return (
                    <path key={r}
                          d={bar(cx - bw / 2, y, bw, drawn, 4,
                                 { tl: isTop, tr: isTop })}
                          fill={colorOf(r)}
                          {...bind([b.date, `${r}: ${b.counts[r]}`])} />
                  )
                })}
                <text x={cx} y={y - 6} textAnchor="middle" className="chart-val">
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

export function LineageChart({ lineage }) {
  const [tip, bind] = useTip()
  const chains = (lineage || []).filter((s) => s.versions.length)
  if (!chains.length) return null

  const widest = Math.max(...chains.map((s) => s.versions.length))
  const STEP = 52, R = 7, LABEL = 96, ROW = 48
  const W = LABEL + Math.max(1, widest - 1) * STEP + 40
  const H = chains.length * ROW

  return (
    <figure className="chart-fig">
      <figcaption>
        <h3>Handle lineage</h3>
        <p className="page-sub">
          Every turn seals a new state and points it at its parent. Nothing is
          edited in place, so the chain is the whole history — each dot is one
          content-addressed handle.
        </p>
      </figcaption>
      <div className="chart-wrap chart-scroll">
        {tip}
        <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} className="chart-svg"
             role="img"
             aria-label={`Handle lineage for ${chains.length} sessions`}>
          {chains.map((s, row) => {
            const y = row * ROW + ROW / 2
            const last = LABEL + (s.versions.length - 1) * STEP
            return (
              <g key={s.session_tag}>
                <text x={LABEL - 12} y={y + 4} textAnchor="end" className="chart-cat">
                  {s.session_tag}
                </text>
                {s.versions.length > 1 && (
                  <line x1={LABEL} y1={y} x2={last} y2={y}
                        stroke={LINE} strokeWidth="2" />
                )}
                {s.versions.map((v, i) => (
                  <g key={v.handle}
                     {...bind([
                       `${s.session_tag} · v${v.version}`,
                       v.handle,
                       `${v.fields} field${v.fields === 1 ? '' : 's'}`,
                       v.created_at.replace('T', ' ').slice(0, 16),
                     ])}>
                    {/* 2px surface ring so overlapping dots stay countable */}
                    <circle cx={LABEL + i * STEP} cy={y} r={R + 2} fill="#fff" />
                    <circle cx={LABEL + i * STEP} cy={y} r={R} fill={SERIES[0]} />
                    <text x={LABEL + i * STEP} y={y + 22} textAnchor="middle"
                          className="chart-cat">v{v.version}</text>
                  </g>
                ))}
              </g>
            )
          })}
        </svg>
      </div>
      <Table
        caption="Handle lineage per session"
        head={['Session', 'Versions', 'Latest handle', 'Fields']}
        rows={chains.map((s) => [
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
