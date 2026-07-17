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

export async function fetchEpisodes() {
  const r = await apiFetch('/silence/games/episodes')
  return r.json()
}

export async function fetchEpisodeDetail(episodeSlug) {
  const r = await apiFetch(`/silence/games/episode?slug=${encodeURIComponent(episodeSlug)}`)
  return r.json()
}

// ── Admin: resolution stats & corrections ───────────────────────────────────
// All of these are admin-gated server-side (403 for a non-admin session).

export async function fetchResolutionStats() {
  const r = await apiFetch('/silence/games/resolution-stats')
  return r.json()
}

export async function searchIgdb(query) {
  const r = await apiFetch(`/silence/games/igdb-search?q=${encodeURIComponent(query)}`)
  return (await r.json()).results
}

// Writes backend/corrections.json — the git-tracked source of truth. Only works
// where that file is writable (dev); prod answers 409 and the UI goes read-only.
// podcastId null/undefined pins the game across every podcast; pass an id to pin
// it for that podcast only (the two shows can cover different games of one name).
// igdbId and displayName are independent: send either or both. An omitted
// displayName leaves the current one alone; '' clears it.
function correctionBody({ nameSlug, igdbId, displayName, podcastId }) {
  return {
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({
      nameSlug,
      podcastId: podcastId || undefined,
      ...(igdbId != null ? { igdbId } : {}),
      ...(displayName !== undefined ? { displayName } : {}),
    }),
  }
}

export async function setCorrection(target) {
  const r = await apiFetch('/silence/games/corrections', { method: 'PUT', ...correctionBody(target) })
  return r.json()
}

export async function deleteCorrection(target) {
  const r = await apiFetch('/silence/games/corrections', { method: 'DELETE', ...correctionBody(target) })
  return r.json()
}

export async function refreshPodcastIgdb(podcastId) {
  const r = await apiFetch(`/silence/games/podcasts/${encodeURIComponent(podcastId)}/igdb-refresh`,
                           { method: 'POST' })
  return r.json()
}

// A short-lived, stream-scoped token (not the session JWT) for the SSE URL.
async function fetchStreamToken() {
  const r = await apiFetch('/silence/auth/stream-token')
  return (await r.json()).token
}

export async function openResolutionStream() {
  const token = await fetchStreamToken()
  return new EventSource(`/silence/games/resolution-stream?token=${encodeURIComponent(token)}`)
}
