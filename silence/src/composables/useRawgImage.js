import { ref, computed } from 'vue'
import { ensureRawgData } from '../lib/rawg.js'

export function useRawg() {
  const data       = ref(null)
  const imgFailed  = ref(false)
  const imgLoading = ref(false)

  const imgUrl = computed(() => data.value?.url ?? null)

  async function load(name) {
    data.value   = null
    imgFailed.value  = false
    imgLoading.value = true
    try {
      data.value = await ensureRawgData(name)
    } finally {
      imgLoading.value = false
    }
  }

  return { data, imgUrl, imgFailed, imgLoading, load }
}
