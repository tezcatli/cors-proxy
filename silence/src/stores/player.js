import { defineStore } from 'pinia'
import { ref } from 'vue'

export const usePlayerStore = defineStore('player', () => {
  const current = ref(null)   // { game, episode, url, ts, timestamp }
  const visible = ref(false)
  const paused  = ref(true)

  function play({ game, episode, url, ts = 0, timestamp = null }) {
    current.value = { game, episode, url, ts, timestamp }
    visible.value = true
    paused.value  = false
  }

  function close() {
    current.value = null
    visible.value = false
    paused.value  = true
  }

  function setPaused(v) { paused.value = v }

  return { current, visible, paused, play, close, setPaused }
})
