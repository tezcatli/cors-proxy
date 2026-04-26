import { apiFetch } from './auth.js'

const MAX_CACHE = 500
const _cache = new Map()
export function clearCache() { _cache.clear() }

export async function ensureIgdbData(name, year = null) {
  const key = year ? `${name.toLowerCase()}_${year}` : name.toLowerCase()
  if (_cache.has(key)) return _cache.get(key)
  const url = `/igdb/game?name=${encodeURIComponent(name)}${year ? `&year=${year}` : ''}`
  const data = await apiFetch(url).then(r => r.json())
  if (_cache.size >= MAX_CACHE) _cache.delete(_cache.keys().next().value)
  _cache.set(key, data)
  return data
}

export function getCachedMeta(name, year = null) {
  const key = year ? `${name.toLowerCase()}_${year}` : name.toLowerCase()
  return _cache.get(key)?.metacritic ?? null
}

export function getCachedData(name, year = null) {
  const key = year ? `${name.toLowerCase()}_${year}` : name.toLowerCase()
  return _cache.get(key) ?? null
}
