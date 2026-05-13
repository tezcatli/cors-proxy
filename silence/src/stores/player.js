import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const usePlayerStore = defineStore('player', () => {
  const current     = ref(null)
  const visible     = ref(false)
  const paused      = ref(true)
  const currentTime = ref(0)
  const playVersion = ref(0)   // incremented on every play() call, not on metadata updates

  function play({ game, slug, episode, url, ts = 0, timestamp = null, episodeImageUrl = null, pubTs = null, episodeSlug = null, coverImageId = null, chapters = null }) {
    playVersion.value++
    current.value = { game, slug: slug ?? game, episode, url, ts, timestamp, episodeImageUrl, pubTs, episodeSlug, coverImageId, chapters: chapters ?? [] }
    console.log('Playing:', current.value)
    visible.value = true
    paused.value  = false
  }

  function close() {
    current.value     = null
    visible.value     = false
    paused.value      = true
    currentTime.value = 0
  }

  function setPaused(v)      { paused.value = v }
  function setCurrentTime(t) { currentTime.value = t }

  const currentChapter = computed(() => {
    const chs = current.value?.chapters
    if (!chs?.length) return null
    let active = null
    for (const ch of chs) {
      if (ch.timestampSeconds <= currentTime.value) active = ch
      else break
    }
    return active
  })

  function setEpisodeImageUrl(url) {
    if (current.value) current.value = { ...current.value, episodeImageUrl: url }
  }

  return { current, visible, paused, currentTime, playVersion, currentChapter, play, close, setPaused, setCurrentTime, setEpisodeImageUrl }
})
