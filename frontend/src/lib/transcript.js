/* Per-session chat transcripts, kept in the browser and nowhere else.

   StateJar never stores a raw transcript server-side. That is not an oversight
   to be fixed with a messages table — it is the claim the product is built on
   (patent module 5; `storage._assert_no_transcript` refuses transcripts at
   write time; the landing page says "Raw transcripts are never stored or
   sent"). So the words have exactly one home: the tab that typed them, which
   is this module.

   The server keeps the other half — which handle was current on each turn and
   what was disclosed from it — at `GET /sessions/{id}/turns`. Joining the two
   is the client's job, and that separation is the whole point.

   Consequences worth knowing, rather than discovering on stage:
     • history is per browser. Another device shows the same *memory* and an
       empty transcript, because only the state travels.
     • clearing site data clears the transcript. The state survives.
     • logging out wipes every stored transcript (`clearAll`), because a shared
       machine must not hand the next person the last person's conversation. */

import { getToken } from './api.js'

const PREFIX = 'statejar_chat:v1:'
const ACTIVE_KEY = 'statejar_active_session'
const MAX_MESSAGES = 300      // ~40 turns of demo; older ones drop off the top

/* Which account a stored transcript belongs to.

   Read from the JWT's `sub` (the account id), which is stable across logins —
   keying on the token itself would orphan every transcript at each refresh.
   This is a namespace, never an authorization check: nothing here is trusted,
   and a forged value can only reach transcripts already in this browser. */
function accountKey() {
  const token = getToken()
  if (!token) return 'anon'
  try {
    const [, payload] = token.split('.')
    const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/'))
    return String(JSON.parse(json).sub ?? 'anon')
  } catch {
    return 'anon'
  }
}

const keyFor = (tag) => `${PREFIX}${accountKey()}:${tag}`

const ours = () => {
  const out = []
  for (let i = 0; i < localStorage.length; i += 1) {
    const k = localStorage.key(i)
    if (k?.startsWith(PREFIX)) out.push(k)
  }
  return out
}

/* Transcripts are the largest thing this app stores, and localStorage has no
   quota API worth trusting. When a write is refused, drop the least recently
   saved sessions until it fits — losing old history beats losing the turn the
   presenter just typed. */
function writeWithEviction(key, value) {
  for (let attempt = 0; attempt < 6; attempt += 1) {
    try {
      localStorage.setItem(key, value)
      return true
    } catch {
      const others = ours()
        .filter((k) => k !== key)
        .map((k) => {
          let savedAt = 0
          try {
            savedAt = JSON.parse(localStorage.getItem(k))?.savedAt || 0
          } catch { /* unreadable entry: evict it first */ }
          return { k, savedAt }
        })
        .sort((a, b) => a.savedAt - b.savedAt)
      if (!others.length) {
        localStorage.removeItem(key)
        return false
      }
      localStorage.removeItem(others[0].k)
    }
  }
  return false
}

/* Everything the chat column and the run panels need to come back exactly as
   they were left. `ui` carries the tier chips, the pipeline stages and the
   last retrieval, so a switch back does not show another session's run. */
export function saveSession(tag, { messages = [], ui = {} } = {}) {
  if (!tag) return
  const trimmed = messages.length > MAX_MESSAGES
    ? messages.slice(messages.length - MAX_MESSAGES)
    : messages
  if (!trimmed.length && !Object.keys(ui).length) {
    clearSession(tag)
    return
  }
  writeWithEviction(
    keyFor(tag),
    JSON.stringify({ savedAt: Date.now(), messages: trimmed, ui }),
  )
}

export function loadSession(tag) {
  if (!tag) return { messages: [], ui: {} }
  try {
    const raw = localStorage.getItem(keyFor(tag))
    if (!raw) return { messages: [], ui: {} }
    const parsed = JSON.parse(raw)
    return {
      messages: Array.isArray(parsed.messages) ? parsed.messages : [],
      ui: parsed.ui && typeof parsed.ui === 'object' ? parsed.ui : {},
    }
  } catch {
    return { messages: [], ui: {} }
  }
}

export function clearSession(tag) {
  if (tag) localStorage.removeItem(keyFor(tag))
}

/* Called on logout. Clears every account's transcripts in this browser, not
   just the current one — the point is that the machine is being handed over. */
export function clearAll() {
  ours().forEach((k) => localStorage.removeItem(k))
  localStorage.removeItem(ACTIVE_KEY)
}

/* The session a reload should return to. Stored per account so two accounts
   on one machine do not drag each other into the wrong session. */
export function loadActiveSession(available = []) {
  try {
    const saved = JSON.parse(localStorage.getItem(ACTIVE_KEY) || '{}')
    const tag = saved[accountKey()]
    if (tag && (!available.length || available.includes(tag))) return tag
  } catch { /* fall through to the default */ }
  return available[0]
}

export function saveActiveSession(tag) {
  if (!tag) return
  let saved = {}
  try {
    saved = JSON.parse(localStorage.getItem(ACTIVE_KEY) || '{}')
  } catch { /* overwrite a corrupt entry */ }
  saved[accountKey()] = tag
  try {
    localStorage.setItem(ACTIVE_KEY, JSON.stringify(saved))
  } catch { /* a lost preference is not worth failing a render over */ }
}
