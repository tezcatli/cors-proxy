import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { fetchCatalog, refreshCatalog, fetchEpisodes } from '../lib/games.js'

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

  // The catalog, searched, narrowed to one podcast's games on its page.
  function filtered(query = '', podcast = null) {
    let games = all.value
    if (podcast)
      games = games.filter(g => g.podcasts?.includes(podcast))
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

  // ── Episodes: every podcast's, those that test nothing included ────────────
  // One list, read by the Ludothèque (its tests, its podcasts, the search) and
  // by the podcasts' pages. Kept on reload, so a refresh never empties it.
  const episodes        = ref([])
  const episodesLoading = ref(false)
  const episodesError   = ref(null)
  const episodesLoaded  = ref(false)
  let _episodesInflight = null
  function loadEpisodes() {
    if (_episodesInflight) return _episodesInflight
    episodesLoading.value = !episodesLoaded.value
    _episodesInflight = (async () => {
      try {
        episodes.value        = await fetchEpisodes()
        episodesError.value   = null
        episodesLoaded.value  = true
      } catch (err) {
        episodesError.value = err.message
      } finally {
        episodesLoading.value = false
        _episodesInflight     = null
      }
    })()
    return _episodesInflight
  }

  // The newest test ({ep, test}): the Ludothèque's showcase, and the colours
  // of its mark and its light (DECISIONS.md, « Interface »).
  const newestTest = computed(() => {
    const ep = episodes.value.find(e => e.games?.length)
    return ep ? { ep, test: ep.games[0] } : null
  })

  return {
    all, lastFetch, sortMode, sortAsc, loading, error, filtered, load, refresh, setSort,
    episodes, episodesLoading, episodesError, episodesLoaded, loadEpisodes, newestTest,
  }
})
