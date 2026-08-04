/* Help content: one markdown file per entry, loaded at build time.

   The entries are data, not JSX, for one reason that matters: a test can read
   them. `backend/tests/test_help_coverage.py` enumerates the product's real
   surfaces — routes, settings, providers, tiers, decline reasons, value types —
   and fails the build when one has no entry here. That only works if the
   content is a directory of parseable files rather than a component.

   The frontmatter parser is deliberately minimal (`key: value` scalars, no
   nesting). It is mirrored by `parse_entry` in that test, so if this format
   ever grows, both change together. */

const FILES = import.meta.glob('../content/help/*.md', {
  query: '?raw', import: 'default', eager: true,
})

/* Categories in reading order. A user arriving with no question should be able
   to start at the top and end up informed; a user with a question searches. */
export const CATEGORIES = [
  { id: 'getting-started', label: 'Getting started' },
  { id: 'concepts', label: 'Concepts' },
  { id: 'interface', label: 'The interface' },
  { id: 'providers', label: 'Providers' },
  { id: 'api', label: 'Working with the API' },
  { id: 'settings', label: 'Settings' },
  { id: 'demo', label: 'The demo' },
  { id: 'troubleshooting', label: 'Troubleshooting' },
  { id: 'faq', label: 'FAQ' },
  { id: 'reference', label: 'Reference' },
]

const ORDER = new Map(CATEGORIES.map((c, i) => [c.id, i]))

function parse(raw, path) {
  const match = /^---\r?\n([\s\S]*?)\r?\n---\r?\n/.exec(raw)
  if (!match) return null
  const meta = {}
  for (const line of match[1].split(/\r?\n/)) {
    if (!line.trim()) continue
    const at = line.indexOf(':')
    if (at < 0) continue
    meta[line.slice(0, at).trim()] = line.slice(at + 1).trim().replace(/^"|"$/g, '')
  }
  if (!meta.id) return null
  return { ...meta, body: raw.slice(match[0].length), path }
}

export const ENTRIES = Object.entries(FILES)
  .map(([path, raw]) => parse(raw, path))
  .filter(Boolean)
  .sort((a, b) => {
    const byCategory = (ORDER.get(a.category) ?? 99) - (ORDER.get(b.category) ?? 99)
    return byCategory || a.title.localeCompare(b.title)
  })

export const BY_ID = new Map(ENTRIES.map((e) => [e.id, e]))

export function entriesByCategory() {
  return CATEGORIES
    .map((c) => ({ ...c, entries: ENTRIES.filter((e) => e.category === c.id) }))
    .filter((c) => c.entries.length)
}

/* Ranked search over titles, summaries, keywords and bodies.

   Weighted rather than flat, because the useful answer to "handle" is the
   entry called Handle, not the twenty entries that mention one. A term in the
   title outranks the same term buried in a body by an order of magnitude.

   Stop words are stripped so a natural question ("why wasn't this stored")
   matches on its content words instead of scoring every entry containing
   "this". */
const STOP = new Set([
  'a', 'an', 'and', 'are', 'as', 'at', 'be', 'but', 'by', 'can', 'did', 'do',
  'does', 'for', 'from', 'has', 'have', 'how', 'i', 'if', 'in', 'is', 'it',
  'its', 'me', 'my', 'no', 'not', 'of', 'on', 'or', 'so', 'that', 'the',
  'their', 'them', 'there', 'this', 'to', 'was', 'wasn', 'were', 'what',
  'when', 'where', 'which', 'why', 'will', 'with', 'you', 'your', 't',
])

const terms = (q) =>
  q.toLowerCase().split(/[^a-z0-9_]+/).filter((w) => w.length > 1 && !STOP.has(w))

function score(entry, words) {
  const title = entry.title.toLowerCase()
  const id = entry.id.toLowerCase()
  const summary = (entry.summary || '').toLowerCase()
  const keywords = (entry.keywords || '').toLowerCase()
  const body = entry.body.toLowerCase()

  let total = 0
  for (const w of words) {
    let hit = 0
    if (title.includes(w)) hit += title.startsWith(w) ? 60 : 40
    if (id.includes(w)) hit += 25
    if (keywords.includes(w)) hit += 20
    if (summary.includes(w)) hit += 12
    if (body.includes(w)) hit += 3
    if (!hit) return 0        // every term must appear somewhere
    total += hit
  }
  return total
}

export function search(query, limit = 25) {
  const words = terms(query || '')
  if (!words.length) return []
  return ENTRIES
    .map((entry) => ({ entry, score: score(entry, words) }))
    .filter((r) => r.score > 0)
    .sort((a, b) => b.score - a.score || a.entry.title.localeCompare(b.entry.title))
    .slice(0, limit)
    .map((r) => r.entry)
}

/* `#concept.handle` in a body is an internal jump, not a web link. Rewritten
   to the help route so it works from a deep link and from a fresh page load,
   rather than resolving against whatever page happens to be open. */
export function resolveHref(href) {
  if (href?.startsWith('#') && BY_ID.has(href.slice(1))) {
    return { internal: true, id: href.slice(1) }
  }
  return { internal: false, href }
}
