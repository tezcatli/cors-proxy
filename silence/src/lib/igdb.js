import { ref } from 'vue'
import { apiFetch } from './auth.js'

const MAX_CACHE = 500
const _cache    = new Map()
const _inFlight = new Map()
export const igdbCacheVersion = ref(0)

export function clearCache() { _cache.clear(); _inFlight.clear() }

export function hasCachedEntry(name) {
  return _cache.has(name.toLowerCase())
}

export async function ensureIgdbData(name, year = null) {
  const key = name.toLowerCase()
  if (_cache.has(key))    return _cache.get(key)
  if (_inFlight.has(key)) return _inFlight.get(key)

  const url = `/igdb/game?name=${encodeURIComponent(name)}${year ? `&year=${year}` : ''}`
  const promise = apiFetch(url)
    .then(r => r.json())
    .then(data => {
      if (_cache.size >= MAX_CACHE) _cache.delete(_cache.keys().next().value)
      _cache.set(key, data)
      igdbCacheVersion.value++
      _inFlight.delete(key)
      return data
    })
    .catch(err => {
      _inFlight.delete(key)
      throw err
    })

  _inFlight.set(key, promise)
  return promise
}

export function getCachedMeta(name) {
  return _cache.get(name.toLowerCase())?.metacritic ?? null
}

export function getCachedData(name) {
  return _cache.get(name.toLowerCase()) ?? null
}
