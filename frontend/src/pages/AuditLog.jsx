import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api.js'
import AuditTimeline from '../components/AuditTimeline.jsx'

/* Patent module 10 — auditable replay, as a provenance timeline.
   Filters are server-side so they work past the first page, and the export
   reflects the filtered view rather than whatever happens to be loaded. */

const PAGE_SIZE = 50

function isoDay(value) {
  return value ? `${value}T00:00:00` : ''
}

export default function AuditLog() {
  const [entries, setEntries] = useState(null)
  const [total, setTotal] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [facets, setFacets] = useState({ providers: [], sessions: [] })

  const [session, setSession] = useState('')
  const [provider, setProvider] = useState('')
  const [search, setSearch] = useState('')
  const [since, setSince] = useState('')
  const [until, setUntil] = useState('')
  const [includeDemo, setIncludeDemo] = useState(true)

  const query = useMemo(() => {
    const params = new URLSearchParams({ limit: String(PAGE_SIZE) })
    if (session) params.set('session_tag', session)
    if (provider) params.set('provider', provider)
    if (search.trim()) params.set('search', search.trim())
    if (since) params.set('since', isoDay(since))
    if (until) params.set('until', `${until}T23:59:59`)
    if (!includeDemo) params.set('include_demo', 'false')
    return params
  }, [session, provider, search, since, until, includeDemo])

  const load = useCallback(async (offset = 0) => {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams(query)
      params.set('offset', String(offset))
      const data = await api(`/audit?${params.toString()}`)
      setEntries((prev) => (offset === 0 ? data.entries : [...(prev || []), ...data.entries]))
      setTotal(data.total)
      setHasMore(data.has_more)
    } catch (err) {
      setError(err.message)
      setEntries([])
    } finally {
      setLoading(false)
    }
  }, [query])

  useEffect(() => { load(0) }, [load])
  useEffect(() => {
    api('/audit/facets').then(setFacets).catch(() => {})
  }, [])

  const exportJson = () => {
    const blob = new Blob([JSON.stringify(entries || [], null, 2)],
      { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `statejar-audit-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const clearFilters = () => {
    setSession(''); setProvider(''); setSearch('')
    setSince(''); setUntil(''); setIncludeDemo(true)
  }

  const filtered = session || provider || search || since || until || !includeDemo

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Audit Log</h1>
          <p className="page-sub">
            Every response, replayable — which handle was used and exactly which
            fields were disclosed.
          </p>
        </div>
        <Link className="btn btn-ghost" to="/playground">Open Playground</Link>
      </div>

      {error && <p className="auth-error">{error}</p>}

      <div className="filters" role="search">
        <input
          type="search" className="filter-search"
          value={search} onChange={(e) => setSearch(e.target.value)}
          placeholder="Search handle or request id…"
          aria-label="Search handle or request id"
        />
        <select value={session} onChange={(e) => setSession(e.target.value)}
          aria-label="Session">
          <option value="">All sessions</option>
          {facets.sessions.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={provider} onChange={(e) => setProvider(e.target.value)}
          aria-label="Provider">
          <option value="">All providers</option>
          {facets.providers.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        <label className="filter-date">
          From
          <input type="date" value={since} onChange={(e) => setSince(e.target.value)} />
        </label>
        <label className="filter-date">
          To
          <input type="date" value={until} onChange={(e) => setUntil(e.target.value)} />
        </label>
        <label className="filter-check">
          <input
            type="checkbox" checked={includeDemo}
            onChange={(e) => setIncludeDemo(e.target.checked)}
          />
          Show demo entries
        </label>
        {filtered && (
          <button className="btn btn-ghost filter-clear" onClick={clearFilters}>
            Clear
          </button>
        )}
      </div>

      <div className="filters-meta">
        <span className="empty-note">
          {entries === null
            ? 'Loading…'
            : `${entries.length} of ${total} ${total === 1 ? 'entry' : 'entries'}`}
        </span>
        <button
          className="btn btn-ghost" onClick={exportJson}
          disabled={!entries?.length}
        >
          Export as JSON
        </button>
      </div>

      <div className="panel">
        {entries === null ? (
          <p className="empty-note">Loading audit trail…</p>
        ) : (
          <>
            <AuditTimeline
              entries={entries}
              showEmptyState={!filtered}
              onCopyHandle={(h) => navigator.clipboard.writeText(h)}
            />
            {entries.length === 0 && filtered && (
              <p className="empty-note">
                No entries match these filters.{' '}
                <button className="link-btn" onClick={clearFilters}>Clear them</button>
              </p>
            )}
            {hasMore && (
              <button
                className="btn btn-ghost load-more"
                onClick={() => load(entries.length)}
                disabled={loading}
              >
                {loading ? 'Loading…' : `Load ${Math.min(PAGE_SIZE, total - entries.length)} more`}
              </button>
            )}
          </>
        )}
      </div>
    </>
  )
}
