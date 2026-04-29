import { ref, computed } from 'vue'
import { ensureIgdbData, hasCachedEntry, getCachedData, clearCacheEntry } from '../lib/igdb.js'

export function useRawg() {
  const data       = ref(null)
  const imgFailed  = ref(false)
  const imgLoading = ref(false)
  const loadError  = ref(false)

  const coverImageId = computed(() => data.value?.coverImageId ?? null)
  const bgImageId    = computed(() => data.value?.bgImageId    ?? null)

  async function load(name, year = null) {
    imgFailed.value = false
    loadError.value = false

    if (hasCachedEntry(name)) {
      data.value       = getCachedData(name)
      imgLoading.value = false
      return
    }

    data.value       = null
    imgLoading.value = true
    try {
      data.value = await ensureIgdbData(name, year)
    } catch {
      loadError.value = true
    } finally {
      imgLoading.value = false
    }
  }

  async function refresh(name, year = null) {
    clearCacheEntry(name)
    await load(name, year)
  }

  return { data, coverImageId, bgImageId, imgFailed, imgLoading, loadError, load, refresh }
}
