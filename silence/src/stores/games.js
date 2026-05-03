import { defineStore } from 'pinia'
import { ref } from 'vue'
import { parseFeed, refreshFeed } from '../lib/rss.js'

const DEFAULT_ASC = { alpha: true, date: false, meta: false }

export const useGamesStore = defineStore('games', () => {
  const all       = ref([])
  const lastFetch = ref(null)
  const sortMode  = ref('alpha')
  const sortAsc   = ref(true)
  const loading   = ref(false)
  const error     = ref(null)

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
      all.value      = await parseFeed()
      lastFetch.value = new Date().toISOString()
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
      all.value       = await refreshFeed()
      lastFetch.value = new Date().toISOString()
    } catch (err) {
      error.value = err.message
    } finally {
      loading.value = false
    }
  }

  function setSort(mode) {
    if (mode === sortMode.value) {
      sortAsc.value = !sortAsc.value
    } else {
      sortMode.value = mode
      sortAsc.value  = DEFAULT_ASC[mode]
    }
  }

  return { all, lastFetch, sortMode, sortAsc, loading, error, filtered, load, refresh, setSort }
})
