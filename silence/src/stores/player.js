import { defineStore } from 'pinia'
import { ref } from 'vue'

export const usePlayerStore = defineStore('player', () => {
  const current = ref(null)   // { game, episode, url, ts, timestamp }
  const visible = ref(false)
  const paused  = ref(true)

  function play({ game, episode, url, ts = 0, timestamp = null, coverImageId = null }) {
    current.value = { game, episode, url, ts, timestamp, coverImageId }
    visible.value = true
    paused.value  = false
  }

  function close() {
    current.value = null
    visible.value = false
    paused.value  = true
  }

  function setPaused(v) { paused.value = v }

  function setCoverImageId(id) {
    if (current.value) current.value = { ...current.value, coverImageId: id }
  }

  return { current, visible, paused, play, close, setPaused, setCoverImageId }
})
