import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'

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

  function restore(savedState) {
    const t           = savedState.currentTime ?? 0
    current.value     = { ...savedState.current, ts: t }
    currentTime.value = t
    visible.value     = true
    paused.value      = true
    playVersion.value++
  }

  // ── Persistence ─────────────────────────────────────────────────────────────
  const STORAGE_KEY = 'soj-player'

  function _save() {
    if (!current.value) localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, JSON.stringify({
      current:     current.value,
      currentTime: currentTime.value,
    }))
  }

  let _saveTimer = null
  watch(current, () => { clearTimeout(_saveTimer); _save() })
  watch(currentTime, () => {
    clearTimeout(_saveTimer)
    _saveTimer = setTimeout(_save, 5000)
  })
  function _saveNow() { clearTimeout(_saveTimer); _save() }
  window.addEventListener('pagehide', _saveNow)
  window.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') _saveNow()
  })

  return { current, visible, paused, currentTime, playVersion, currentChapter, play, close, restore, setPaused, setCurrentTime, setEpisodeImageUrl }
})
