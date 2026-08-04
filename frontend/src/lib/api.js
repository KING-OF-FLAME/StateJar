// JWT kept in memory, mirrored to localStorage for refresh survival.
let _token = localStorage.getItem('statejar_token') || null

export function setToken(token) {
  _token = token
  if (token) localStorage.setItem('statejar_token', token)
  else localStorage.removeItem('statejar_token')
}

export function getToken() {
  return _token
}

export function isAuthed() {
  return Boolean(_token)
}

// Production: set VITE_API_URL to the backend origin (https://api.statejar.com).
// Vite bakes it in at build time, so changing it needs a redeploy.
// Dev: leave unset — the Vite proxy forwards /api to localhost:8000.
// Strip any trailing slash so we never trigger a redirect (Safari drops CORS on redirects).
const API_BASE = (import.meta.env.VITE_API_URL || '').replace(/\/+$/, '')

export async function api(path, { method = 'GET', body } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (_token) headers.Authorization = `Bearer ${_token}`
  let resp
  try {
    resp = await fetch(`${API_BASE}/api/v1${path}`, {
      method,
      headers,
      mode: 'cors',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch (err) {
    // Safari reports network/CORS failures as an opaque "Load failed" TypeError.
    const netErr = new Error(
      `Could not reach the StateJar API (${err.message}). ` +
        'Check your connection and try again.',
    )
    netErr.isNetwork = true // callers may retry once (e.g. Railway cold start)
    throw netErr
  }
  if (resp.status === 401 && !path.startsWith('/auth/')) {
    setToken(null)
    window.location.href = '/login'
    throw new Error('session expired')
  }
  const data = await resp.json().catch(() => ({}))
  if (!resp.ok) {
    /* A `detail` can be a string or a structured rejection. Passing an object
       to `new Error` renders it "[object Object]", which threw away exactly the
       part worth showing — the per-field reasons the API returns instead of
       coercing a bad value. Keep the object on the error for callers that can
       render it, and give the message a readable fallback for those that
       cannot. */
    const { detail } = data
    const structured = detail && typeof detail === 'object'
    const err = new Error(
      (structured ? detail.error : detail) || `request failed (${resp.status})`,
    )
    if (structured) err.detail = detail
    err.status = resp.status
    throw err
  }
  return data
}
