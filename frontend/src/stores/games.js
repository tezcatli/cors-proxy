import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchCatalog, refreshCatalog, openResolutionStream } from '../lib/games.js'
import { usePlayerStore } from './player.js'

const DEFAULT_ASC = { alpha: true, date: false, meta: false }

// One reusable collator — `String.localeCompare(s, 'fr', {…})` rebuilds a collator
// per call, which is costly when sorting ~1600 names on each keystroke.
const collator = new Intl.Collator('fr', { sensitivity: 'base' })

export const useGamesStore = defineStore('games', () => {
  const all             = ref([])
  const lastFetch       = ref(null)
  const sortMode        = ref(localStorage.getItem('soj-sort-mode') || 'alpha')
  const sortAsc         = ref(localStorage.getItem('soj-sort-asc') !== 'false')
  const selectedPodcast = ref(localStorage.getItem('soj-podcast-filter') || 'all')
  const loading         = ref(false)
  const resolving       = ref(false)
  const error           = ref(null)

  let _sse = null

  async function _startSSE() {
    if (_sse) { _sse.close(); _sse = null }
    resolving.value = true
    try {
      _sse = await openResolutionStream()   // fetches a short-lived stream token first
    } catch (_) {
      resolving.value = false
      return
    }
    _sse.onmessage = (e) => {
      const event = JSON.parse(e.data)
      if (event.type === 'resolved' && event.igdbSlug) {
        const idx = all.value.findIndex(g => g.slug === event.nameSlug)
        if (idx !== -1) {
          all.value[idx] = { ...all.value[idx], slug: event.igdbSlug, igdb: event.igdb }
          usePlayerStore().updateGameSlug(event.nameSlug, event.igdbSlug)
        }
      }
      if (event.type === 'done') {
        _sse.close(); _sse = null
        resolving.value = false
        // Reconcile the catalog but DON'T re-arm SSE: a 'done' that still reports
        // pending>0 (e.g. IGDB failures) would otherwise reopen → instant done →
        // reopen … forever. Background retries are owned by the server's periodic
        // resolver; the next user-initiated load re-arms.
        load(false)
      }
    }
    _sse.onerror = () => {
      // Don't close() on a transient error — that disables EventSource's built-in
      // auto-reconnect (a Wi-Fi flap would otherwise strand live resolution).
      // Only finalize when the browser has marked the stream permanently CLOSED;
      // then reconcile whatever resolved while we were disconnected.
      if (_sse && _sse.readyState === EventSource.CLOSED) {
        _sse = null
        resolving.value = false
        load(false)
      }
    }
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
          return collator.compare(a.name, b.name)
        if (ma === null) return 1
        if (mb === null) return -1
        return dir * (ma - mb)
      }
      return dir * collator.compare(a.name, b.name)
    })
  }

  function filtered(query = '') {
    let games = all.value
    if (selectedPodcast.value !== 'all')
      games = games.filter(g => g.podcasts?.includes(selectedPodcast.value))
    if (query)
      games = games.filter(g => g.name.toLowerCase().includes(query.toLowerCase()))
    return _sort(games)
  }

  // In-flight guard so concurrent triggers (App onMounted + the route watch)
  // coalesce into a single fetch instead of double-fetching the catalog.
  const _inflight = {}
  function _populate(key, fetcher, armSSE = true) {
    if (_inflight[key]) return _inflight[key]
    loading.value = true
    error.value   = null
    _inflight[key] = (async () => {
      try {
        const { games, pending } = await fetcher()
        all.value       = games
        lastFetch.value = new Date().toISOString()
        if (pending > 0 && armSSE) await _startSSE()
      } catch (err) {
        error.value = err.message
      } finally {
        loading.value = false
        _inflight[key] = null
      }
    })()
    return _inflight[key]
  }

  function load(armSSE = true) { return _populate('load', fetchCatalog, armSSE) }
  function refresh() { return _populate('refresh', refreshCatalog) }

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

  function setPodcast(id) {
    selectedPodcast.value = id
    localStorage.setItem('soj-podcast-filter', id)
  }

  return { all, lastFetch, sortMode, sortAsc, selectedPodcast, loading, resolving, error, filtered, load, refresh, setSort, setPodcast }
})
