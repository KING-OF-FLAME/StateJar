/* Browser-direct Ollama.
 *
 * A hosted StateJar backend can never reach http://localhost:11434 — that
 * address exists on the user's machine, not on Railway. So for a local
 * daemon the browser talks to Ollama itself and the prompt never leaves the
 * user's computer. StateJar's server still does the memory work (retrieval,
 * handles, audit); it just never sees the conversation.
 *
 * Ollama refuses cross-origin browser requests unless it is started with
 * OLLAMA_ORIGINS, and the failure surfaces as an opaque TypeError, so
 * classifyError() turns it into the one instruction that fixes it.
 */

export const DEFAULT_OLLAMA_URL = 'http://localhost:11434'

/* Ollama's own docs write the cloud endpoint as `https://ollama.com/api/chat`
   and the OpenAI-compatible one as `http://localhost:11434/v1/`, so a user
   copying from the docs pastes a base that already carries the path. Appending
   `/api/tags` to that gave `/api/api/tags`, which the real service answers
   with `path "/api/api/tags" not found`. Both forms normalise to the host. */
export function normaliseBase(url) {
  const trimmed = (url || '').trim().replace(/\/+$/, '').replace(/\/(?:api|v1)$/i, '')
  return trimmed || DEFAULT_OLLAMA_URL
}

/* A localhost daemon is only reachable from the browser; anything else can
   be reached by our backend too, which is the only way an API key helps. */
export function isLocalHost(url) {
  try {
    const { hostname } = new URL(normaliseBase(url))
    return ['localhost', '127.0.0.1', '0.0.0.0', '[::1]', '::1'].includes(hostname)
  } catch {
    return false
  }
}

export function modeFor({ baseUrl, apiKey }) {
  return !apiKey && isLocalHost(baseUrl) ? 'browser-direct' : 'server-side'
}

const ORIGIN = typeof window !== 'undefined' ? window.location.origin : 'https://statejar.com'

export const originsFix = {
  unix: `OLLAMA_ORIGINS=${ORIGIN} ollama serve`,
  windows: `set OLLAMA_ORIGINS=${ORIGIN}\nollama serve`,
  powershell: `$env:OLLAMA_ORIGINS="${ORIGIN}"; ollama serve`,
}

/* fetch() hides CORS detail from script for security, so a blocked request
   and a dead daemon both arrive as the same TypeError. Distinguish them by
   whether anything is listening at all. */
export function classifyError(err, baseUrl) {
  const base = normaliseBase(baseUrl)
  if (err?.name === 'AbortError') {
    return { kind: 'timeout', message: `${base} did not respond in time.` }
  }
  if (err instanceof TypeError) {
    // fetch() deliberately hides the reason, so a blocked request and a dead
    // daemon are indistinguishable from script. Name both rather than assert
    // the wrong one — the fix below is harmless if it is simply not running.
    return {
      kind: 'cors',
      message:
        `The browser could not reach ${base}. Either Ollama is not running, ` +
        'or it is refusing browser requests — it blocks cross-origin calls ' +
        'unless started with OLLAMA_ORIGINS.',
    }
  }
  return { kind: 'error', message: err?.message || String(err) }
}

async function call(baseUrl, path, { method = 'GET', body, timeout = 60000 } = {}) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)
  try {
    const resp = await fetch(`${normaliseBase(baseUrl)}${path}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    })
    if (!resp.ok) {
      const detail = await resp.text().catch(() => '')
      throw new Error(`Ollama returned HTTP ${resp.status}${detail ? `: ${detail.slice(0, 160)}` : ''}`)
    }
    return await resp.json()
  } finally {
    clearTimeout(timer)
  }
}

/** The user's actually-installed models, not a hardcoded list. */
export async function listLocalModels(baseUrl) {
  const data = await call(baseUrl, '/api/tags', { timeout: 8000 })
  return (data.models || [])
    .filter((m) => m.name)
    .map((m) => ({
      id: `ollama/${m.name}`,
      name: m.name,
      context_length: m.details?.parameter_size ? null : null,
      is_free: true,
    }))
}

export async function testConnection(baseUrl) {
  try {
    const models = await listLocalModels(baseUrl)
    return { ok: true, count: models.length, models }
  } catch (err) {
    return { ok: false, ...classifyError(err, baseUrl) }
  }
}

/** One turn, straight from this browser to the user's daemon. */
export async function chatLocal({ baseUrl, model, systemContext, userMessage }) {
  const started = performance.now()
  const data = await call(baseUrl, '/api/chat', {
    method: 'POST',
    body: {
      model,
      messages: [
        { role: 'system', content: systemContext },
        { role: 'user', content: userMessage },
      ],
      stream: false,
    },
  })
  return {
    text: data.message?.content || '',
    model: data.model || model,
    tokens_in: data.prompt_eval_count || 0,
    tokens_out: data.eval_count || 0,
    latency_ms: Math.round(performance.now() - started),
  }
}
