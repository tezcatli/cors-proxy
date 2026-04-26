import { describe, it, expect } from 'vitest'

const BASE      = process.env.BACKEND_URL || 'http://corsproxy-test:5000'
const ADMIN_KEY = process.env.ADMIN_KEY   || 'test-admin-key'

let counter = 0
function uniqueEmail() {
  return `integration_${++counter}_${Date.now()}@example.com`
}

async function invite(email) {
  const r = await fetch(`${BASE}/auth/invite`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json', 'X-Admin-Key': ADMIN_KEY },
    body:    JSON.stringify({ email }),
  })
  expect(r.status).toBe(201)
  const { invite_url } = await r.json()
  return new URL(invite_url).searchParams.get('invite')
}

async function register(email, password, inviteToken) {
  return fetch(`${BASE}/auth/register`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ email, password, invitation_token: inviteToken }),
  })
}

async function login(email, password) {
  return fetch(`${BASE}/auth/login`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ email, password }),
  })
}

// ── invite → register → login ─────────────────────────────────────────────

describe('full auth flow', () => {
  it('invite → register → login returns a valid JWT', async () => {
    const email = uniqueEmail()
    const token = await invite(email)
    expect(token).toBeTruthy()

    const regRes = await register(email, 'password123', token)
    expect(regRes.status).toBe(201)
    expect(await regRes.json()).toHaveProperty('access_token')

    const loginRes = await login(email, 'password123')
    expect(loginRes.status).toBe(200)
    const { access_token } = await loginRes.json()

    const parts   = access_token.split('.')
    expect(parts).toHaveLength(3)
    const payload = JSON.parse(Buffer.from(parts[1], 'base64').toString('utf8'))
    expect(payload.email).toBe(email)
    expect(payload.exp).toBeGreaterThan(Math.floor(Date.now() / 1000))
  })

  it('registered user can use token to call protected endpoint', async () => {
    const email = uniqueEmail()
    const token = await invite(email)
    const regRes = await register(email, 'password123', token)
    const { access_token } = await regRes.json()

    const r = await fetch(`${BASE}/igdb/game?name=zelda`, {
      headers: { Authorization: `Bearer ${access_token}` },
    })
    // 200 (cached or upstream) or 502/503 (no IGDB creds / upstream down) — anything but 401
    expect(r.status).not.toBe(401)
  })
})

// ── login failures ────────────────────────────────────────────────────────

describe('login failures', () => {
  it('wrong password returns 401', async () => {
    const email = uniqueEmail()
    await register(email, 'correct', await invite(email))

    const r = await login(email, 'wrong')
    expect(r.status).toBe(401)
    expect(await r.json()).toHaveProperty('error')
  })

  it('unknown email returns 401', async () => {
    const r = await login('nobody@nowhere.example.com', 'anything')
    expect(r.status).toBe(401)
  })
})

// ── register failures ─────────────────────────────────────────────────────

describe('register failures', () => {
  it('bad invite token returns 400', async () => {
    const r = await register(uniqueEmail(), 'password123', 'totally-fake-token')
    expect(r.status).toBe(400)
    expect(await r.json()).toHaveProperty('error')
  })

  it('duplicate email returns 409', async () => {
    const email = uniqueEmail()
    const token1 = await invite(email)
    await register(email, 'password123', token1)

    const token2 = await invite(email)
    const r = await register(email, 'password456', token2)
    expect(r.status).toBe(409)
    expect(await r.json()).toHaveProperty('error')
  })

  it('weak password returns 400', async () => {
    const email = uniqueEmail()
    const token = await invite(email)
    const r = await register(email, '123', token)
    expect(r.status).toBe(400)
    expect(await r.json()).toHaveProperty('error')
  })
})
