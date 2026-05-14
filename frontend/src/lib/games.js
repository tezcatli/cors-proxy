import { apiFetch } from './auth.js'

export async function fetchCatalog() {
  const r = await apiFetch('/silence/games')
  return r.json()
}

export async function fetchGameDetail(slug) {
  const r = await apiFetch(`/silence/games/${encodeURIComponent(slug)}`)
  return r.json()
}

export async function refreshCatalog() {
  const r = await apiFetch('/silence/games/refresh', { method: 'POST' })
  return r.json()
}

export async function refreshGameIgdb(slug) {
  const r = await apiFetch(`/silence/games/${encodeURIComponent(slug)}/igdb-refresh`, { method: 'POST' })
  return r.json()
}

export async function fetchIgdb(slugs) {
  const params = new URLSearchParams(slugs.map(s => ['slug', s]))
  const r = await apiFetch(`/silence/games/igdb?${params}`)
  return r.json()
}

export async function fetchEpisodes() {
  const r = await apiFetch('/silence/games/episodes')
  return r.json()
}

export async function fetchEpisodeDetail(episodeSlug) {
  const r = await apiFetch(`/silence/games/episode?slug=${encodeURIComponent(episodeSlug)}`)
  return r.json()
} 