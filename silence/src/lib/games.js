import { apiFetch } from './auth.js'

export async function fetchCatalog() {
  const r = await apiFetch('/games')
  return r.json()
}

export async function fetchGameDetail(name) {
  const r = await apiFetch(`/games/${encodeURIComponent(name)}`)
  return r.json()
}

export async function refreshCatalog() {
  const r = await apiFetch('/games/refresh', { method: 'POST' })
  return r.json()
}

export async function refreshGameIgdb(name) {
  const r = await apiFetch(`/games/${encodeURIComponent(name)}/igdb-refresh`, { method: 'POST' })
  return r.json()
}

export async function fetchIgdb(names) {
  const params = new URLSearchParams(names.map(n => ['name', n]))
  const r = await apiFetch(`/games/igdb?${params}`)
  return r.json()
}
