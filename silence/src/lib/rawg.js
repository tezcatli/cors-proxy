import { apiFetch } from './auth.js'
import { norm } from './utils.js'

const MAX_CACHE = 500
const _cache = new Map()
export function clearCache() { _cache.clear() }

const normKey = s => norm(s).replaceAll(' ', '')

async function rawgSearch(query) {
  const r = await apiFetch(`/rawg/games?search=${encodeURIComponent(query)}&page_size=10`)
  const data = await r.json()
  return data.results || []
}

export function rankResults(results, gameName) {
  const q    = normKey(gameName)
  const base = normKey(gameName.replace(/\s*[:\-–].+$/, '').trim())
  return [...results].sort((a, b) => {
    const score = r => {
      const n = normKey(r.name)
      if (n === q)                              return 4
      if (n === base)                           return 3
      if (n.startsWith(q) || q.startsWith(n))  return 2
      if (n.startsWith(base) || base.startsWith(n)) return 1
      return 0
    }
    return score(b) - score(a)
  })
}

export function simplifyPlatform(name) {
  if (/playstation/i.test(name))      return 'PlayStation'
  if (/xbox/i.test(name))             return 'Xbox'
  if (/switch|nintendo/i.test(name))  return 'Switch'
  if (/pc|windows/i.test(name))       return 'PC'
  if (/mac/i.test(name))              return 'Mac'
  if (/ios|iphone/i.test(name))       return 'iOS'
  if (/android/i.test(name))          return 'Android'
  return null
}

async function fetchRawgData(gameName) {
  try {
    let results = await rawgSearch(gameName)
    const baseName = gameName.replace(/\s*[:\-–].+$/, '').trim()
    if ((!results.length || normKey(results[0]?.name) !== normKey(gameName)) && baseName !== gameName) {
      const baseResults = await rawgSearch(baseName)
      if (baseResults.length) results = [...results, ...baseResults]
    }
    if (!results.length) return null

    const ranked  = rankResults(results, gameName)
    const best    = ranked[0]
    const withImg = ranked.find(r => r.background_image)

    const metacritic = best.metacritic || null
    const genres     = (best.genres || []).slice(0, 3).map(g => g.name)
    const released   = best.released ? best.released.slice(0, 4) : null
    const platforms  = [...new Set((best.platforms || [])
      .map(p => simplifyPlatform(p.platform.name)).filter(Boolean))].slice(0, 4)
    const rating     = best.rating   ? parseFloat(best.rating.toFixed(1)) : null
    const esrb       = best.esrb_rating?.name || null
    const playtime   = best.playtime ? Math.round(best.playtime) : null

    let url         = withImg?.background_image || best.background_image || null
    let description = null
    let developer   = null

    if (best?.slug) {
      try {
        const detail = await apiFetch(`/rawg/games/${encodeURIComponent(best.slug)}`).then(r => r.json())
        if (!url) url = detail.background_image || detail.background_image_additional || null
        developer = detail.developers?.[0]?.name || null
        const rawDesc = (detail.description_raw || '').trim()
        if (rawDesc) description = rawDesc.split(/\n\n/)[0].trim().slice(0, 500)
      } catch {}
    }

    return { url, metacritic, genres, released, platforms, rating, esrb, playtime, description, developer }
  } catch (err) {
    console.warn(`[RAWG] ${gameName}: ${err.message}`)
    return undefined
  }
}

export async function ensureRawgData(name) {
  const key = name.toLowerCase()
  if (_cache.has(key)) return _cache.get(key)
  const result = await fetchRawgData(name)
  if (result === undefined) return null
  if (_cache.size >= MAX_CACHE) _cache.delete(_cache.keys().next().value)
  _cache.set(key, result)
  return result
}

export function getCachedMeta(name) {
  return _cache.get(name.toLowerCase())?.metacritic || null
}

export function getCachedData(name) {
  return _cache.get(name.toLowerCase()) || null
}
