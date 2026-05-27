import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchCatalog, refreshCatalog, fetchIgdb, openResolutionStream } from '../lib/games.js'

let _igdbQueue = new Set()
let _igdbTimer = null

const DEFAULT_ASC = { alpha: true, date: false, meta: false }

export const useGamesStore = defineStore('games', () => {
  const all       = ref([])
  const lastFetch = ref(null)
  const sortMode  = ref(localStorage.getItem('soj-sort-mode') || 'alpha')
  const sortAsc   = ref(localStorage.getItem('soj-sort-asc') !== 'false')
  const loading   = ref(false)
  const resolving = ref(false)
  const error     = ref(null)

  let _sse = null

  function _startSSE() {
    if (_sse) { _sse.close(); _sse = null }
    resolving.value = true
    _sse = openResolutionStream()
    _sse.onmessage = (e) => {
      const event = JSON.parse(e.data)
      if (event.type === 'resolved' && event.igdbSlug) {
        const idx = all.value.findIndex(g => g.slug === event.nameSlug)
        if (idx !== -1)
          all.value[idx] = { ...all.value[idx], slug: event.igdbSlug, igdb: event.igdb }
      }
      if (event.type === 'done') {
        _sse.close(); _sse = null
        resolving.value = false
        load()
      }
    }
    _sse.onerror = () => { _sse?.close(); _sse = null; resolving.value = false }
  }

  function _sort(games) {
    const dir = sortAsc.value ? 1 : -1
    return [...games].sort((a, b) => {
      if (sortMode.value === 'date')
        return dir * ((a.latestPubTs ?? 0) - (b.latestPubTs ?? 0))
      if (sortMode.value === 'meta') {
        const ma = a.igdb?.metacritic ?? null
        const mb = b.igdb?.metacritic ?? null
        if (ma === null && mb === null)
          return a.name.localeCompare(b.name, 'fr', { sensitivity: 'base' })
        if (ma === null) return 1
        if (mb === null) return -1
        return dir * (ma - mb)
      }
      return dir * a.name.localeCompare(b.name, 'fr', { sensitivity: 'base' })
    })
  }

  function filtered(query = '') {
    const games = query
      ? all.value.filter(g => g.name.toLowerCase().includes(query.toLowerCase()))
      : all.value
    return _sort(games)
  }

  async function load() {
    loading.value = true
    error.value   = null
    try {
      const { games, pending } = await fetchCatalog()
      all.value       = games
      lastFetch.value = new Date().toISOString()
      if (pending > 0) _startSSE()
    } catch (err) {
      error.value = err.message
    } finally {
      loading.value = false
    }
  }

  async function refresh() {
    loading.value = true
    error.value   = null
    try {
      const { games, pending } = await refreshCatalog()
      all.value       = games
      lastFetch.value = new Date().toISOString()
      if (pending > 0) _startSSE()
    } catch (err) {
      error.value = err.message
    } finally {
      loading.value = false
    }
  }

  async function _flushIgdbQueue() {
    const slugs = [..._igdbQueue]
    _igdbQueue.clear()
    _igdbTimer = null
    try {
      const map = await fetchIgdb(slugs)
      for (const [slug, igdb] of Object.entries(map)) {
        const idx = all.value.findIndex(g => g.slug === slug)
        if (idx !== -1) all.value[idx].igdb = igdb
      }
    } catch (_) { /* silent — card stays with placeholder */ }
  }

  function queueIgdb(slug) {
    if (_igdbQueue.has(slug)) return
    _igdbQueue.add(slug)
    clearTimeout(_igdbTimer)
    _igdbTimer = setTimeout(_flushIgdbQueue, 50)
  }

  function setSort(mode) {
    if (mode === sortMode.value) {
      sortAsc.value = !sortAsc.value
    } else {
      sortMode.value = mode
      sortAsc.value  = DEFAULT_ASC[mode]
    }
    localStorage.setItem('soj-sort-mode', sortMode.value)
    localStorage.setItem('soj-sort-asc', String(sortAsc.value))
  }

  return { all, lastFetch, sortMode, sortAsc, loading, resolving, error, filtered, load, refresh, setSort, queueIgdb }
})
