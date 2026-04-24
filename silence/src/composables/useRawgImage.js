import { ref } from 'vue'
import { fetchImage } from '../lib/rawg.js'

export function useRawgImage() {
  const imgUrl     = ref(null)
  const imgFailed  = ref(false)
  const imgLoading = ref(false)

  async function load(name) {
    imgUrl.value     = null
    imgFailed.value  = false
    imgLoading.value = true
    try {
      imgUrl.value = await fetchImage(name)
    } finally {
      imgLoading.value = false
    }
  }

  return { imgUrl, imgFailed, imgLoading, load }
}
