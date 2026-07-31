import { apiFetch } from './auth.js'

// Client for the account-administration endpoints (`/silence/auth/*`). Kept out
// of `auth.js` — which every session loads — so it code-splits with the lazy
// admin page. All of these are admin-gated server-side (403 otherwise), and the
// guards they can hit (409 self / last admin) come back as `error` messages that
// the UI shows verbatim rather than restating.

// apiFetch attaches the Bearer token but no content type; Flask's get_json()
// silently returns nothing without it.
const JSON_HEADERS = { 'Content-Type': 'application/json' }

export async function fetchUsers() {
  const r = await apiFetch('/silence/auth/users')
  return (await r.json()).users
}

export async function setUserAdmin(id, isAdmin) {
  const r = await apiFetch(`/silence/auth/users/${id}`, {
    method:  'PATCH',
    headers: JSON_HEADERS,
    body:    JSON.stringify({ is_admin: isAdmin }),
  })
  return r.json()
}

export async function deleteUser(id) {
  await apiFetch(`/silence/auth/users/${id}`, { method: 'DELETE' })
}

export async function fetchInvitations() {
  const r = await apiFetch('/silence/auth/invitations')
  return (await r.json()).invitations
}

// The response carries `invite_url`: SMTP is optional in this deployment, so
// when it isn't configured that link *is* how the invitation gets delivered.
export async function sendInvitation(email, isAdmin = false) {
  const r = await apiFetch('/silence/auth/invite', {
    method:  'POST',
    headers: JSON_HEADERS,
    body:    JSON.stringify({ email, is_admin: isAdmin }),
  })
  return r.json()
}

export async function revokeInvitation(token) {
  await apiFetch(`/silence/auth/invitations/${encodeURIComponent(token)}`, { method: 'DELETE' })
}
