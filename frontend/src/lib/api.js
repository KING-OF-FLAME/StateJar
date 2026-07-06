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

// Production: set VITE_API_URL to the backend origin (e.g. https://statejar-api.up.railway.app).
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
    throw new Error(
      `Could not reach the StateJar API (${err.message}). ` +
        'Check your connection and try again.',
    )
  }
  if (resp.status === 401 && !path.startsWith('/auth/')) {
    setToken(null)
    window.location.href = '/login'
    throw new Error('session expired')
  }
  const data = await resp.json().catch(() => ({}))
  if (!resp.ok) {
    throw new Error(data.detail || `request failed (${resp.status})`)
  }
  return data
}
