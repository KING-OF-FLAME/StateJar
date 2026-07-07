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
    snippet: (
      <>
        {'{ "name": '}<span className="hl">"Ayaan"</span>{', "budget": '}<span className="hl">2000</span>
        {', "preferences": { "contact_mode": "email" }, "goal": "trip_planning", "unresolved": ["dates"] }'}
      </>
    ),
  },
  {
    num: '02 · CANONICALIZE',
    title: 'Canonicalize',
    video: '/videos/m2.mp4',
    body: 'Sorted keys, normalized numbers and dates, versioned schema. Identical meaning → byte-identical JSON. Always.',
    snippet: (
      <>
        {'{ "budget": "₹2,000", "name": "Ayaan" } → '}
        <span className="hl">{'{ "budget": 2000, "name": "Ayaan" }'}</span>{' '}
        <span className="dim">{'// sorted keys, normalized numbers, schema v1'}</span>
      </>
    ),
  },
  {
    num: '03 · HANDLE',
    title: 'Handle',
    video: '/videos/m3.mp4',
    body: 'SHA-256 over the canonical state yields a deterministic content address. Same state, same handle, every time.',
    snippet: <span className="hl hash">shm_8f3a9c41be07d5a2c6f1e8b3a4d9c7e2f5a8b1c40d7e0f3a6b9c2d5e8f1a4d21</span>,
  },
  {
    num: '04 · RETRIEVE MINIMUM',
    title: 'Retrieve minimum',
    video: '/videos/m6.mp4',
    body: 'Each query discloses only the fields it needs. The model never sees your transcript — just the minimal subset, audited.',
    snippet: (
      <>
        {'query: "What\'s his budget?" → subset_keys: ['}
        <span className="hl">"budget", "name"</span>{'] · '}
        <span className="hl">2 of 14</span>{' fields · −78% tokens'}
      </>
    ),
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

const NAV_LINKS = [
  ['#problem', 'Why StateJar'],
  ['#how', 'How it works'],
  ['#modules', 'Patent modules'],
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

/* Lightbox modal shared by all module cards. */
function VideoModal({ module: mod, onClose }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [onClose])

  if (!mod) return null
  const [num, title, body] = mod

  return (
    <div className="lightbox" role="dialog" aria-modal="true" aria-label={`${title} video`} onClick={onClose}>
      <div className="lightbox-panel" onClick={(e) => e.stopPropagation()}>
        <button className="lightbox-close" onClick={onClose} aria-label="Close video">✕</button>
        <video
          key={num}
          src={`/videos/m${num.slice(1)}.mp4`}
          autoPlay
          loop
          muted
          playsInline
          aria-label={`${title} module animation`}
        />
        <div className="lightbox-caption">
          <span className="m-num mono">{num}</span>
          <h3>{title}</h3>
          <p>{body}</p>
        </div>
      </div>
    </div>
  )
}

export default function Landing() {
  const [menuOpen, setMenuOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const [activeModule, setActiveModule] = useState(null)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  // Lock body scroll; close on Esc or any tap outside the panel while the menu is open.
  useEffect(() => {
    if (!menuOpen) return
    document.body.style.overflow = 'hidden'
    const onPointerDown = (e) => {
      if (!e.target.closest('.nav-panel') && !e.target.closest('.nav-burger')) setMenuOpen(false)
    }
    const onKey = (e) => e.key === 'Escape' && setMenuOpen(false)
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.body.style.overflow = ''
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [menuOpen])

  const closeMenu = () => setMenuOpen(false)

  return (
    <>
      <nav className={`nav${scrolled ? ' nav-scrolled' : ''}`} aria-label="Main navigation">
        <div className="container nav-inner">
          <a className="brand" href="/">
            <img className="brand-logo" src="/logo.png" alt="StateJar logo — a jar holding structured memory" />
            State<span className="jar">Jar</span>
          </a>
          <button
            className="nav-burger"
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((v) => !v)}
          >
            {menuOpen ? '✕' : '☰'}
          </button>
          <div className="nav-links">
            {NAV_LINKS.map(([href, label]) => (
              <a key={href} href={href}>{label}</a>
            ))}
            <a className="btn btn-ghost btn-nav" href="/playground">Open the Playground</a>
          </div>
        </div>
      </nav>

      {/* Outside <nav>: its backdrop-filter creates a containing block that would trap position:fixed children. */}
      <div className={`nav-overlay${menuOpen ? ' open' : ''}`} onClick={closeMenu} aria-hidden="true" />
        <aside className={`nav-panel${menuOpen ? ' open' : ''}`} aria-label="Menu" aria-hidden={!menuOpen}>
          <div className="nav-panel-head">
            <a className="brand" href="/" onClick={closeMenu}>
              <img className="brand-logo" src="/logo.png" alt="StateJar logo" />
              State<span className="jar">Jar</span>
            </a>
            <button className="nav-panel-close" onClick={closeMenu} aria-label="Close menu">✕</button>
          </div>
          <div className="nav-panel-links">
            {NAV_LINKS.map(([href, label], i) => (
              <a key={href} href={href} style={{ '--i': i }} onClick={closeMenu}>
                {label}
                <span className="chev" aria-hidden="true">→</span>
              </a>
            ))}
          </div>
          <div className="nav-panel-ctas">
            <a className="btn btn-ghost" href="/login" onClick={closeMenu}>Log in</a>
            <a className="btn btn-primary" href="/playground" onClick={closeMenu}>Open the Playground</a>
          </div>
          <p className="nav-panel-foot mono">Indian Patent 202621017626</p>
        </aside>

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

          <p className="trust-strip fade-item" style={{ '--d': '380ms' }}>
            Indian Patent 202621017626 <span aria-hidden="true">·</span> SHA-256 deterministic{' '}
            <span aria-hidden="true">·</span> BYOK encrypted (AES-256-GCM)
          </p>

          <div className="hero-handle fade-item" style={{ '--d': '440ms' }} aria-hidden="true">
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

      <section id="how" className="section-alt">
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
              Click a card to watch its module in motion.
            </p>
          </Reveal>
          <div className="modules">
            {MODULES.map((mod, i) => {
              const [num, title, body] = mod
              return (
                <Reveal
                  as="button"
                  type="button"
                  className="module"
                  key={num}
                  delay={(i % 5) * 80}
                  onClick={() => setActiveModule(mod)}
                  aria-label={`Watch the ${title} module animation`}
                >
                  <span className="m-num mono">{num}</span>
                  <h3>{title}</h3>
                  <p>{body}</p>
                  <span className="m-watch"><span aria-hidden="true">▶</span> Watch</span>
                </Reveal>
              )
            })}
          </div>
        </div>
      </section>

      {activeModule && <VideoModal module={activeModule} onClose={() => setActiveModule(null)} />}

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
        <div className="container footer-grid">
          <div className="footer-col">
            <a className="brand" href="/">
              <img className="brand-logo" src="/logo.png" alt="StateJar logo" />
              State<span className="jar">Jar</span>
            </a>
            <p className="footer-tag">Deterministic, minimal-disclosure memory for multi-session conversational AI.</p>
          </div>
          <div className="footer-col">
            <h3 className="footer-head">Product</h3>
            <a href="/playground">Playground</a>
            <a href="/signup">Sign up</a>
            <a href="/login">Log in</a>
          </div>
          <div className="footer-col">
            <h3 className="footer-head">Legal & patent</h3>
            <p>Indian Patent APP No. 202621017626</p>
          </div>
        </div>
        <div className="footer-bar">
          <div className="container">
            <span>© 2026 StateJar · All Rights Reserved · Built by Team Hello World</span>
          </div>
        </div>
      </footer>
    </>
  )
}
