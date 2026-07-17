import { ref } from 'vue'

const TOKEN_KEY = 'soj-auth-token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

// JWT payloads are base64url-encoded UTF-8 — atob only accepts standard base64
// (`-`/`_` throw, and only non-ASCII claim bytes can produce them), and returns
// a byte string that still needs UTF-8 decoding for accented emails.
function _claims() {
  const token = getToken()
  if (!token) return null
  try {
    const b64   = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0))
    return JSON.parse(new TextDecoder().decode(bytes))
  } catch {
    return null
  }
}

export function getUserEmail() {
  return _claims()?.email || null
}

export function isLoggedIn() {
  const exp = _claims()?.exp
  return !!exp && exp * 1000 > Date.now()
}

// Cosmetic only — decides whether to *show* the admin UI. Every admin endpoint
// re-checks the flag server-side, so a forged claim buys nothing.
export function isAdmin() {
  return _claims()?.admin === true
}

export const loggedIn = ref(isLoggedIn())

export function logout() {
  localStorage.removeItem(TOKEN_KEY)
  loggedIn.value = false
}

function _redirectToLogin() {
  // Lazy import avoids a circular dependency (router.js imports this module).
  import('../router.js')
    .then(({ default: router }) => {
      if (router.currentRoute.value.path !== '/login') router.push('/login')
    })
    .catch(() => {
      if (!location.pathname.endsWith('/login')) location.assign('/silence/login')
    })
}

export async function apiFetch(path, opts = {}) {
  const token = getToken()
  const headers = {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(opts.headers || {}),
  }
  const res = await fetch(path, { ...opts, headers })
  if (!res.ok) {
    // A 401 on a protected endpoint means the session expired — drop the token
    // and bounce to login. Auth endpoints (login/register/reset) legitimately
    // return 401 for bad credentials, so those surface the error normally.
    if (res.status === 401 && !path.startsWith('/silence/auth/')) {
      logout()
      _redirectToLogin()
    }
    let msg = `HTTP ${res.status}`
    try { msg = (await res.json()).error || msg } catch {}
    throw new Error(msg)
  }
  return res
}

async function post(path, body) {
  const res = await apiFetch('/silence/auth' + path, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(body),
  })
  return res.status === 204 ? null : res.json()
}

function setToken(data) {
  localStorage.setItem(TOKEN_KEY, data.access_token)
  loggedIn.value = true
}

export async function login(email, password) {
  setToken(await post('/login', { email, password }))
}

export async function register(email, password, invitationToken) {
  setToken(await post('/register', { email, password, invitation_token: invitationToken }))
}

export async function resetRequest(email) {
  await post('/reset-request', { email })
}

export async function resetConfirm(token, newPassword) {
  await post('/reset-confirm', { token, new_password: newPassword })
}

export async function refresh() {
  const res = await apiFetch('/silence/auth/refresh', { method: 'POST' })
  setToken(await res.json())
}
