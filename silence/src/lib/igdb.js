import { ref } from 'vue'
import { apiFetch } from './auth.js'

const MAX_CACHE = 500
const _cache = new Map()
export const igdbCacheVersion = ref(0)
export function clearCache() { _cache.clear() }

export async function ensureIgdbData(name, year = null) {
  const key = name.toLowerCase()
  if (_cache.has(key)) return _cache.get(key)
  const url = `/igdb/game?name=${encodeURIComponent(name)}${year ? `&year=${year}` : ''}`
  const data = await apiFetch(url).then(r => r.json())
  if (_cache.size >= MAX_CACHE) _cache.delete(_cache.keys().next().value)
  _cache.set(key, data)
  igdbCacheVersion.value++
  return data
}

export function getCachedMeta(name) {
  return _cache.get(name.toLowerCase())?.metacritic ?? null
}

export function getCachedData(name) {
  return _cache.get(name.toLowerCase()) ?? null
}
