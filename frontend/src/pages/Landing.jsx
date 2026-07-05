import { useEffect, useRef, useState } from 'react'

const PROBLEMS = [
  {
    icon: '↯',
    title: 'Context drift',
    body: 'Long conversations mutate. Summaries of summaries lose the facts that mattered — the budget, the name, the decision already made.',
  },
  {
    icon: '₹',
    title: 'Token burn',
    body: 'Replaying the whole chat history on every request is the most expensive way to remember. Most of that context is never needed.',
  },
  {
    icon: '?',
    title: 'Hallucinated memory',
    body: 'Vector recall is probabilistic. Ask the same question twice, get two different pasts. Production systems need memory that is provable.',
  },
]

const FLOW = [
  {
    num: '01 · EXTRACT',
    title: 'Extract',
    video: '/videos/m1.mp4',
    body: 'Raw text becomes structured state: facts, preferences, decisions, constraints, goals — and what is still unresolved.',
    snippet: <>{'{ "preferences": { "contact_mode": '}<span className="hl">"email"</span>{' } }'}</>,
  },
  {
    num: '02 · CANONICALIZE',
    title: 'Canonicalize',
    video: '/videos/m2.mp4',
    body: 'Sorted keys, normalized numbers and dates, versioned schema. Identical meaning → byte-identical JSON. Always.',
    snippet: <>{'"₹2,000" ≡ "2000" → '}<span className="hl">2000</span></>,
  },
  {
    num: '03 · HANDLE',
    title: 'Handle',
    video: '/videos/m3.mp4',
    body: 'SHA-256 over the canonical state yields a deterministic content address. Same state, same handle, every time.',
    snippet: <span className="hl">shm_8f3a9c41be07d5a2c6…d21</span>,
  },
  {
    num: '04 · RETRIEVE MINIMUM',
    title: 'Retrieve minimum',
    video: '/videos/m6.mp4',
    body: 'Each query discloses only the fields it needs. The model never sees your transcript — just the minimal subset, audited.',
    snippet: <>{'subset_keys: ['}<span className="hl">2 of 14</span>{'] · −78% tokens'}</>,
  },
]

const MODULES = [
  ['M1', 'State Extraction', 'Structured state from raw conversation.'],
  ['M2', 'Canonicalization', 'One meaning, one byte sequence.'],
  ['M3', 'Deterministic Handles', 'Content-addressed memory via SHA-256.'],
  ['M4', 'Deduplicated Storage', 'Identical meaning is stored exactly once.'],
  ['M5', 'No Full Chat Replay', 'Raw transcripts are never stored or sent.'],
  ['M6', 'Minimal Retrieval', 'Intent-scoped subsets, not context dumps.'],
  ['M7', 'Append-Only Versioning', 'New handles per update; history never mutates.'],
  ['M8', 'Conflict Preservation', 'Changes are recorded, never silently overwritten.'],
  ['M9', 'Cross-Session Consistency', 'Same memory across sessions, providers, models.'],
  ['M10', 'Audit & Replay', 'Reconstruct exactly what any response saw.'],
]

const STATS = [
  { value: 78, suffix: '%', label: 'tokens saved', count: true },
  { value: 10, suffix: '', label: 'patent modules', count: true },
  { value: 65, suffix: '', label: 'tests passing', count: true },
  { value: 'SHA-256', label: 'deterministic', count: false },
]

/* Adds .in when the element scrolls into view; children stagger via --d. */
function Reveal({ as: Tag = 'div', className = '', delay = 0, children, ...rest }) {
  const ref = useRef(null)
  useEffect(() => {
    const el = ref.current
    if (!el || !('IntersectionObserver' in window)) {
      el?.classList.add('in')
      return
    }
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          el.classList.add('in')
          io.disconnect()
        }
      },
      { threshold: 0.15, rootMargin: '0px 0px -40px 0px' },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [])
  return (
    <Tag ref={ref} className={`reveal ${className}`} style={{ '--d': `${delay}ms` }} {...rest}>
      {children}
    </Tag>
  )
}

/* Counts 0 → target when scrolled into view. */
function Counter({ value, suffix }) {
  const ref = useRef(null)
  const [n, setN] = useState(0)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    let raf
    const io = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return
        io.disconnect()
        const start = performance.now()
        const dur = 1400
        const tick = (now) => {
          const t = Math.min((now - start) / dur, 1)
          const eased = 1 - Math.pow(1 - t, 3)
          setN(Math.round(eased * value))
          if (t < 1) raf = requestAnimationFrame(tick)
        }
        raf = requestAnimationFrame(tick)
      },
      { threshold: 0.4 },
    )
    io.observe(el)
    return () => {
      io.disconnect()
      cancelAnimationFrame(raf)
    }
  }, [value])
  return (
    <span ref={ref}>
      {n}
      {suffix}
    </span>
  )
}

/* Module card: video plays on hover (desktop) or tap (touch). */
function ModuleCard({ num, title, body, delay }) {
  const vidRef = useRef(null)
  const [playing, setPlaying] = useState(false)
  const idx = num.slice(1)

  const play = () => {
    vidRef.current?.play().catch(() => {})
    setPlaying(true)
  }
  const pause = () => {
    vidRef.current?.pause()
    setPlaying(false)
  }

  return (
    <Reveal
      className={`module${playing ? ' playing' : ''}`}
      delay={delay}
      onMouseEnter={play}
      onMouseLeave={pause}
      onClick={() => (playing ? pause() : play())}
    >
      <div className="module-media">
        <video
          ref={vidRef}
          src={`/videos/m${idx}.mp4#t=0.1`}
          muted
          loop
          playsInline
          preload="metadata"
          aria-label={`${title} module animation`}
        />
      </div>
      <span className="m-num mono">{num}</span>
      <h3>{title}</h3>
      <p>{body}</p>
    </Reveal>
  )
}

export default function Landing() {
  return (
    <>
      <nav className="nav" aria-label="Main navigation">
        <div className="container nav-inner">
          <a className="brand" href="/">
            <img className="brand-logo" src="/logo.png" alt="StateJar logo — a jar holding structured memory" />
            State<span className="jar">Jar</span>
          </a>
          <div className="nav-links">
            <a href="#problem">Why StateJar</a>
            <a href="#how">How it works</a>
            <a href="#modules">Patent modules</a>
            <a className="btn btn-ghost" href="/playground" style={{ padding: '8px 18px' }}>Open the Playground</a>
          </div>
        </div>
      </nav>

      <header className="hero">
        <div className="container">
          <span className="hero-badge fade-item">Indian Patent No. 202621017626</span>
          <h1 className="fade-item" style={{ '--d': '80ms' }}>
            Deterministic memory for AI that never forgets — <em>or hallucinates its past.</em>
          </h1>
          <p className="hero-sub fade-item" style={{ '--d': '160ms' }}>
            Patent-backed, token-saving memory infrastructure for multi-session
            conversational AI. Structured state, content-addressed handles, minimal disclosure.
          </p>
          <div className="hero-ctas fade-item" style={{ '--d': '240ms' }}>
            <a className="btn btn-primary" href="/playground">Try the Playground</a>
            <a className="btn btn-ghost" href="#how">See how it works</a>
          </div>

          <div className="hero-media fade-item" style={{ '--d': '320ms' }}>
            <video
              src="/videos/m6.mp4"
              autoPlay
              loop
              muted
              playsInline
              aria-label="Animation of StateJar's minimal-disclosure retrieval: only the needed fields pass through to the model"
            />
          </div>

          <div className="hero-handle fade-item" style={{ '--d': '400ms' }} aria-hidden="true">
            <div><span className="dim">$</span> statejar ingest <span className="dim">"Budget is under ₹2000, prefer email."</span></div>
            <div style={{ marginTop: 10 }}>
              <span className="dim">handle</span>&nbsp;&nbsp;<span className="hl">shm_8f3a9c41be07d5a2c6f13e9048a7b5c2e6f04d21</span>
            </div>
            <div>
              <span className="dim">state</span>&nbsp;&nbsp;&nbsp;{'{ constraints: { budget_inr_max: '}<span className="ok">2000</span>{' } }'}
            </div>
            <div>
              <span className="dim">replay</span>&nbsp;&nbsp;<span className="ok">deterministic ✓</span>&nbsp;<span className="dim">· transcript stored: never</span>
            </div>
          </div>

          <div className="stats-band">
            {STATS.map((s, i) => (
              <Reveal className="stat" key={s.label} delay={i * 90}>
                <span className="stat-num">{s.count ? <Counter value={s.value} suffix={s.suffix} /> : s.value}</span>
                <span className="stat-cap">{s.label}</span>
              </Reveal>
            ))}
          </div>
        </div>
      </header>

      <section id="problem">
        <div className="container">
          <Reveal>
            <p className="section-kicker">The problem</p>
            <h2 className="section-title">Long conversations are where AI memory quietly breaks.</h2>
            <p className="section-lede">
              Today's assistants either replay everything, summarize lossily, or guess from embeddings.
              All three fail in production.
            </p>
          </Reveal>
          <div className="cards-3">
            {PROBLEMS.map((p, i) => (
              <Reveal className="card" key={p.title} delay={i * 110}>
                <div className="card-icon" aria-hidden="true">{p.icon}</div>
                <h3>{p.title}</h3>
                <p>{p.body}</p>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <section id="how" style={{ background: '#F4F0EA', borderTop: '1px solid var(--line)', borderBottom: '1px solid var(--line)' }}>
        <div className="container">
          <Reveal>
            <p className="section-kicker">How it works</p>
            <h2 className="section-title">From messy text to a provable memory address.</h2>
            <p className="section-lede">
              Four deterministic stages. No embeddings in the write path, no probabilistic recall —
              the same state always resolves to the same handle.
            </p>
          </Reveal>
          <div className="flow">
            {FLOW.map((s, i) => (
              <Reveal className="flow-step" key={s.title} delay={i * 110}>
                <div className="flow-media">
                  <video
                    src={s.video}
                    autoPlay
                    loop
                    muted
                    playsInline
                    preload="metadata"
                    aria-label={`${s.title} stage animation`}
                  />
                </div>
                <div className="flow-num">{s.num}</div>
                <h3>{s.title}</h3>
                <p>{s.body}</p>
                <div className="snippet">{s.snippet}</div>
                {i < FLOW.length - 1 && <span className="flow-arrow" aria-hidden="true">→</span>}
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <section id="modules">
        <div className="container">
          <Reveal>
            <p className="section-kicker">Patent architecture</p>
            <h2 className="section-title">Ten modules, one guarantee: memory you can audit.</h2>
            <p className="section-lede">
              Every layer of StateJar maps to a module of Indian Patent 202621017626.
              Hover a card to see its module in motion.
            </p>
          </Reveal>
          <div className="modules">
            {MODULES.map(([num, title, body], i) => (
              <ModuleCard key={num} num={num} title={title} body={body} delay={(i % 5) * 80} />
            ))}
          </div>
        </div>
      </section>

      <section style={{ paddingTop: 0 }}>
        <div className="container">
          <Reveal className="cta-band">
            <h2>Give your AI a past it can prove.</h2>
            <p>Ingest a conversation, watch the handle appear, and query the minimum.</p>
            <a className="btn btn-primary" href="/playground">Try the Playground</a>
          </Reveal>
        </div>
      </section>

      <footer>
        <div className="container">
          <span className="footer-brand">
            <img src="/logo.png" alt="StateJar logo" width="22" height="26" />
            Indian Patent No. 202621017626 · Built by Yash Raj
          </span>
          <span className="mono" style={{ fontSize: '0.75rem' }}>statejar · deterministic state-handle memory</span>
        </div>
      </footer>
    </>
  )
}
