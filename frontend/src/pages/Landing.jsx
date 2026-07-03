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
    body: 'Raw text becomes structured state: facts, preferences, decisions, constraints, goals — and what is still unresolved.',
    snippet: <>{'{ "preferences": { "contact_mode": '}<span className="hl">"email"</span>{' } }'}</>,
  },
  {
    num: '02 · CANONICALIZE',
    title: 'Canonicalize',
    body: 'Sorted keys, normalized numbers and dates, versioned schema. Identical meaning → byte-identical JSON. Always.',
    snippet: <>{'"₹2,000" ≡ "2000" → '}<span className="hl">2000</span></>,
  },
  {
    num: '03 · HANDLE',
    title: 'Handle',
    body: 'SHA-256 over the canonical state yields a deterministic content address. Same state, same handle, every time.',
    snippet: <span className="hl">shm_8f3a9c41be07d5a2c6…d21</span>,
  },
  {
    num: '04 · RETRIEVE MINIMUM',
    title: 'Retrieve minimum',
    body: 'Each query discloses only the fields it needs. The model never sees your transcript — just the minimal subset, audited.',
    snippet: <>{'subset_keys: ['}<span className="hl">2 of 14</span>{'] · −78% tokens'}</>,
  },
]

const MODULES = [
  ['M1', 'State Extraction', 'Structured state from raw conversation.'],
  ['M2', 'Canonicalization', 'One meaning, one byte sequence.'],
  ['M3', 'Deterministic Handles', 'Content-addressed memory via SHA-256.'],
  ['M4', 'Versioned Evolution', 'Append-only lineage; history never mutates.'],
  ['M5', 'No Full Chat Replay', 'Raw transcripts are never stored or sent.'],
  ['M6', 'Minimal Retrieval', 'Intent-scoped subsets, not context dumps.'],
  ['M7', 'Conflict Detection', 'Changes are recorded, never silently overwritten.'],
  ['M8', 'Audit & Replay', 'Reconstruct exactly what any response saw.'],
  ['M9', 'Cross-Session Consistency', 'Same memory across sessions, providers, models.'],
  ['M10', 'Provider Gateway', 'Bring your own key — encrypted at rest, AES-256-GCM.'],
]

export default function Landing() {
  return (
    <>
      <nav className="nav">
        <div className="container nav-inner">
          <a className="brand" href="/">State<span className="jar">Jar</span></a>
          <div className="nav-links">
            <a href="#problem">Why</a>
            <a href="#how">How it works</a>
            <a href="#modules">Patent modules</a>
            <a className="btn btn-ghost" href="/playground" style={{ padding: '8px 18px' }}>Playground</a>
          </div>
        </div>
      </nav>

      <header className="hero">
        <div className="container">
          <span className="hero-badge">Indian Patent No. 202621017626</span>
          <h1>
            Deterministic memory for AI that never forgets — <em>or hallucinates its past.</em>
          </h1>
          <p className="hero-sub">
            Patent-backed, token-saving memory infrastructure for multi-session
            conversational AI. Structured state, content-addressed handles, minimal disclosure.
          </p>
          <div className="hero-ctas">
            <a className="btn btn-primary" href="/playground">Try the Playground</a>
            <a className="btn btn-ghost" href="#how">See how it works</a>
          </div>

          <div className="hero-handle" aria-hidden="true">
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
        </div>
      </header>

      <section id="problem">
        <div className="container">
          <p className="section-kicker">The problem</p>
          <h2 className="section-title">Long conversations are where AI memory quietly breaks.</h2>
          <p className="section-lede">
            Today's assistants either replay everything, summarize lossily, or guess from embeddings.
            All three fail in production.
          </p>
          <div className="cards-3">
            {PROBLEMS.map((p) => (
              <div className="card" key={p.title}>
                <div className="card-icon">{p.icon}</div>
                <h3>{p.title}</h3>
                <p>{p.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="how" style={{ background: '#F4F0EA', borderTop: '1px solid var(--line)', borderBottom: '1px solid var(--line)' }}>
        <div className="container">
          <p className="section-kicker">How it works</p>
          <h2 className="section-title">From messy text to a provable memory address.</h2>
          <p className="section-lede">
            Four deterministic stages. No embeddings in the write path, no probabilistic recall —
            the same state always resolves to the same handle.
          </p>
          <div className="flow">
            {FLOW.map((s, i) => (
              <div className="flow-step" key={s.title}>
                <div className="flow-num">{s.num}</div>
                <h3>{s.title}</h3>
                <p>{s.body}</p>
                <div className="snippet">{s.snippet}</div>
                {i < FLOW.length - 1 && <span className="flow-arrow">→</span>}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="modules">
        <div className="container">
          <p className="section-kicker">Patent architecture</p>
          <h2 className="section-title">Ten modules, one guarantee: memory you can audit.</h2>
          <p className="section-lede">
            Every layer of StateJar maps to a module of Indian Patent 202621017626.
          </p>
          <div className="modules">
            {MODULES.map(([num, title, body]) => (
              <div className="module" key={num}>
                <span className="m-num mono">{num}</span>
                <h4>{title}</h4>
                <p>{body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section style={{ paddingTop: 0 }}>
        <div className="container">
          <div className="cta-band">
            <h2>Give your AI a past it can prove.</h2>
            <p>Ingest a conversation, watch the handle appear, and query the minimum.</p>
            <a className="btn btn-primary" href="/playground">Try the Playground</a>
          </div>
        </div>
      </section>

      <footer>
        <div className="container">
          <span>Indian Patent No. 202621017626 · Built by Yash Raj</span>
          <span className="mono" style={{ fontSize: '0.75rem' }}>statejar · deterministic state-handle memory</span>
        </div>
      </footer>
    </>
  )
}
