import { ref, computed } from 'vue'
import { ensureIgdbData } from '../lib/igdb.js'

export function useRawg() {
  const data       = ref(null)
  const imgFailed  = ref(false)
  const imgLoading = ref(false)

  const imgUrl = computed(() => data.value?.url ?? null)

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

  return { data, imgUrl, imgFailed, imgLoading, load }
}
