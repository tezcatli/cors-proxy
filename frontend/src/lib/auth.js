import { ref } from 'vue'

const TOKEN_KEY = 'soj-auth-token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function getUserEmail() {
  const token = getToken()
  if (!token) return null
  try {
    return JSON.parse(atob(token.split('.')[1])).email || null
  } catch {
    return null
  }
}

export function isLoggedIn() {
  const token = getToken()
  if (!token) return false
  try {
    const { exp } = JSON.parse(atob(token.split('.')[1]))
    return exp * 1000 > Date.now()
  } catch {
    return false
  }
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
