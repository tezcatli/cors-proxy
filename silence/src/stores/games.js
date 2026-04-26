import { defineStore } from 'pinia'
import { ref } from 'vue'
import { parseFeed } from '../lib/rss.js'
import { getCachedMeta, igdbCacheVersion } from '../lib/igdb.js'
import { latestDate } from '../lib/utils.js'

const DEFAULT_ASC = { alpha: true, date: false, meta: false }

export const useGamesStore = defineStore('games', () => {
  const all       = ref([])
  const lastFetch = ref(null)
  const sortMode  = ref('alpha')
  const sortAsc   = ref(true)
  const loading   = ref(false)
  const error     = ref(null)

  function _sort(games) {
    void igdbCacheVersion.value
    const dir = sortAsc.value ? 1 : -1
    return [...games].sort((a, b) => {
      if (sortMode.value === 'date')
        return dir * (latestDate(a) - latestDate(b))
      if (sortMode.value === 'meta') {
        const ma = getCachedMeta(a.name), mb = getCachedMeta(b.name)
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

  function setSort(mode) {
    if (mode === sortMode.value) {
      sortAsc.value = !sortAsc.value
    } else {
      sortMode.value = mode
      sortAsc.value  = DEFAULT_ASC[mode]
    }
  }

  return { all, lastFetch, sortMode, sortAsc, loading, error, filtered, load, setSort }
})
