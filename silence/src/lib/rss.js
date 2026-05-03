import { apiFetch } from './auth.js'

export async function parseFeed() {
  const r = await apiFetch('/rss/games')
  if (!r.ok) throw new Error(`RSS ${r.status}`)
  return r.json()
}

export async function fetchGame(name) {
  const r = await apiFetch(`/rss/games/${encodeURIComponent(name)}`)
  if (!r.ok) throw new Error(`RSS ${r.status}`)
  return r.json()
}

export async function refreshFeed() {
  const r = await apiFetch('/rss/refresh', { method: 'POST' })
  if (!r.ok) throw new Error(`RSS refresh ${r.status}`)
  return r.json()
}

export async function refreshGameIgdb(name) {
  const r = await apiFetch(`/rss/games/${encodeURIComponent(name)}/igdb-refresh`, { method: 'POST' })
  if (!r.ok) throw new Error(`IGDB refresh ${r.status}`)
  return r.json()
}
