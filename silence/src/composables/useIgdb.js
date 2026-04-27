import { ref, computed } from 'vue'
import { ensureIgdbData } from '../lib/igdb.js'

export function useRawg() {
  const data       = ref(null)
  const imgFailed  = ref(false)
  const imgLoading = ref(false)

  const coverImageId = computed(() => data.value?.coverImageId ?? null)
  const bgImageId    = computed(() => data.value?.bgImageId    ?? null)

  async function load(name, year = null) {
    data.value       = null
    imgFailed.value  = false
    imgLoading.value = true
    try {
      data.value = await ensureIgdbData(name, year)
    } finally {
      imgLoading.value = false
    }
  }

  return { data, coverImageId, bgImageId, imgFailed, imgLoading, load }
}
