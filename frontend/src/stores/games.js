import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchCatalog, refreshCatalog } from '../lib/games.js'

const DEFAULT_ASC = { alpha: true, date: false, meta: false }

// One reusable collator — `String.localeCompare(s, 'fr', {…})` rebuilds a collator
// per call, which is costly when sorting ~1600 names on each keystroke.
const collator = new Intl.Collator('fr', { sensitivity: 'base' })

export const useGamesStore = defineStore('games', () => {
  const all             = ref([])
  const lastFetch       = ref(null)
  // Newest tests first by default: what's new is the first question.
  const sortMode        = ref(localStorage.getItem('soj-sort-mode') || 'date')
  const sortAsc         = ref(localStorage.getItem('soj-sort-asc') === 'true')
  const selectedPodcast = ref(localStorage.getItem('soj-podcast-filter') || 'all')
  const loading         = ref(false)
  const error           = ref(null)

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
  // No live updates: a refresh answers once the server has resolved the new
  // games (IGDB only, a few seconds), so one response is the whole story.
  const _inflight = {}
  function _populate(key, fetcher) {
    if (_inflight[key]) return _inflight[key]
    loading.value = true
    error.value   = null
    _inflight[key] = (async () => {
      try {
        const { games } = await fetcher()
        all.value       = games
        lastFetch.value = new Date().toISOString()
      } catch (err) {
        error.value = err.message
      } finally {
        loading.value = false
        _inflight[key] = null
      }
    })()
    return _inflight[key]
  }

  function load() { return _populate('load', fetchCatalog) }
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

  return { all, lastFetch, sortMode, sortAsc, selectedPodcast, loading, error, filtered, load, refresh, setSort, setPodcast }
})
