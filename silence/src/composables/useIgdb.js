import { ref, computed } from 'vue'
import { ensureIgdbData, hasCachedEntry, getCachedData } from '../lib/igdb.js'

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

  return { data, coverImageId, bgImageId, imgFailed, imgLoading, loadError, load }
}
