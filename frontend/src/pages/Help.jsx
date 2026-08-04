import { useEffect, useMemo, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { BY_ID, ENTRIES, entriesByCategory, search } from '../lib/help.js'

/* Help centre.

   Content comes from `src/content/help/*.md` — one file per entry — so that a
   backend test can enumerate it and fail the build when a shipped surface has
   no entry. See lib/help.js and backend/tests/test_help_coverage.py.

   Every entry has a stable anchor: /help#concept.handle opens that entry
   directly, which is what makes cross-references from the console worth
   writing. */

function fmtDate(iso) {
  const d = new Date(`${iso}T00:00:00Z`)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, {
    year: 'numeric', month: 'long', day: 'numeric', timeZone: 'UTC',
  })
}

/* A body link like `#concept.handle` is a jump within the help centre, not a
   page anchor — resolving it as one would leave the URL right and the scroll
   position wrong on a fresh load. */
function bodyComponents(onJump) {
  return {
    a: ({ href, children }) => {
      const id = href?.startsWith('#') ? href.slice(1) : null
      if (id && BY_ID.has(id)) {
        return (
          <a
            href={`/help#${id}`}
            className="help-xref"
            onClick={(e) => { e.preventDefault(); onJump(id) }}
          >
            {children}
          </a>
        )
      }
      if (href?.startsWith('/')) return <Link to={href}>{children}</Link>
      return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
    },
    table: ({ children }) => (
      <div className="help-table-wrap"><table>{children}</table></div>
    ),
    /* react-markdown v10 dropped the `inline` prop, so branching on it made
       every inline span render as a block — a `<pre>` inside a `<p>`, which the
       browser hoists out and which forced the page wider than the viewport on a
       phone. Styling `code` and `pre` separately needs no such flag: inline code
       is a bare `<code>`, and a fenced block is a `<pre>` that resets it. */
    code: ({ children }) => <code className="help-code">{children}</code>,
    pre: ({ children }) => <pre className="help-pre">{children}</pre>,
  }
}

function Entry({ entry, onJump, registerRef }) {
  return (
    <article className="help-entry" id={entry.id} ref={(el) => registerRef(entry.id, el)}>
      <header className="help-entry-head">
        <h3>{entry.title}</h3>
        <a
          className="help-anchor mono"
          href={`/help#${entry.id}`}
          onClick={(e) => { e.preventDefault(); onJump(entry.id) }}
          title="Link to this entry"
        >
          #{entry.id}
        </a>
      </header>
      {entry.summary && <p className="help-summary">{entry.summary}</p>}
      <div className="help-body md">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={bodyComponents(onJump)}>
          {entry.body}
        </ReactMarkdown>
      </div>
      <p className="help-updated mono">Last updated {fmtDate(entry.updated_at)}</p>
    </article>
  )
}

export default function Help() {
  const [query, setQuery] = useState('')
  const location = useLocation()
  const navigate = useNavigate()
  const refs = useRef(new Map())
  const searchRef = useRef(null)

  const registerRef = (id, el) => {
    if (el) refs.current.set(id, el)
    else refs.current.delete(id)
  }

  const results = useMemo(() => (query.trim() ? search(query) : null), [query])
  const categories = useMemo(entriesByCategory, [])

  const jump = (id) => {
    navigate(`/help#${id}`, { replace: false })
    setQuery('')
    // one frame, so an entry hidden behind an active search is mounted first
    requestAnimationFrame(() => {
      refs.current.get(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      refs.current.get(id)?.classList.add('help-flash')
      setTimeout(() => refs.current.get(id)?.classList.remove('help-flash'), 1200)
    })
  }

  /* Deep link: /help#concept.handle lands on that entry.

     Retried rather than fired once. The page mounts 130-odd entries and the
     document keeps growing for several frames afterwards, so a single early
     scroll lands at the position the target had before the entries above it
     finished laying out. Instant rather than smooth, too — `scroll-behavior:
     smooth` on `html` would otherwise animate ten thousand pixels while the
     reader waits. */
  useEffect(() => {
    const id = decodeURIComponent(location.hash.replace('#', ''))
    if (!id || !BY_ID.has(id)) return undefined
    let frame = 0
    let last = -1
    const settle = () => {
      const el = refs.current.get(id)
      if (el) {
        const top = Math.round(el.getBoundingClientRect().top)
        el.scrollIntoView({ block: 'start', behavior: 'instant' })
        if (top === last) return                 // position stopped moving
        last = top
      }
      if (frame++ < 30) requestAnimationFrame(settle)
    }
    const raf = requestAnimationFrame(settle)
    return () => cancelAnimationFrame(raf)
  }, [location.hash])

  // "/" focuses search, the way every documentation site the user has already
  // used behaves
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === '/' && document.activeElement?.tagName !== 'INPUT') {
        e.preventDefault()
        searchRef.current?.focus()
      }
      if (e.key === 'Escape') setQuery('')
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  return (
    <div className="help-page">
      <header className="help-head">
        <h1>Help centre</h1>
        <p className="help-lede">
          Every concept, control, provider and decline reason in StateJar.
          {' '}Coverage is enforced by a test, so this cannot quietly fall behind
          the product.
        </p>
        <div className="help-search">
          <input
            ref={searchRef}
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search — try “declined”, “handle”, “why wasn’t this stored”"
            aria-label="Search help"
          />
          <span className="help-search-hint mono" aria-hidden="true">/</span>
        </div>
      </header>

      <div className="help-cols">
        <nav className="help-toc" aria-label="Help contents">
          {categories.map((c) => (
            <div key={c.id} className="help-toc-group">
              <p className="help-toc-head">{c.label}</p>
              <ul>
                {c.entries.map((e) => (
                  <li key={e.id}>
                    <a
                      href={`/help#${e.id}`}
                      onClick={(ev) => { ev.preventDefault(); jump(e.id) }}
                    >
                      {e.title}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>

        <main className="help-main">
          {results ? (
            <section className="help-results">
              <p className="help-results-count">
                {results.length === 0
                  ? `Nothing matched “${query}”.`
                  : `${results.length} result${results.length === 1 ? '' : 's'} for “${query}”`}
              </p>
              {results.length === 0 && (
                <p className="empty-note">
                  Try a single word — “handle”, “declined”, “ollama”, “tokens”.
                  {' '}Every entry is also listed on the left.
                </p>
              )}
              {results.map((e) => (
                <button
                  type="button" key={e.id} className="help-result"
                  onClick={() => jump(e.id)}
                >
                  <span className="help-result-title">{e.title}</span>
                  <span className="help-result-cat mono">{e.category}</span>
                  <span className="help-result-summary">{e.summary}</span>
                </button>
              ))}
            </section>
          ) : (
            categories.map((c) => (
              <section key={c.id} className="help-section" id={`cat-${c.id}`}>
                <h2 className="help-cat-head">{c.label}</h2>
                {c.entries.map((e) => (
                  <Entry key={e.id} entry={e} onJump={jump} registerRef={registerRef} />
                ))}
              </section>
            ))
          )}
          <p className="help-foot">
            {ENTRIES.length} entries. Something missing or wrong?
            {' '}That is a bug — the coverage test exists so it cannot be a
            silent one.
          </p>
        </main>
      </div>
    </div>
  )
}
