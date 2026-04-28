<script setup>
import { ref, watch } from 'vue'
import { usePlayerStore } from '../stores/player.js'
import { igdbUrl } from '../lib/igdbCdn.js'

const playerStore = usePlayerStore()
const audioEl     = ref(null)

watch(() => playerStore.current, cur => {
  if (!cur || !audioEl.value) return
  const el = audioEl.value
  if (el.src === cur.url) {
    seekAndPlay(el, cur.ts)
    return
  }
  el.src = cur.url
  el.load()
  el.addEventListener('canplay', () => seekAndPlay(el, cur.ts), { once: true })
  el.play().catch(() => {})
  setMediaSession(cur)
})

function seekAndPlay(el, ts) {
  if (ts > 0) {
    if (isFinite(el.duration)) el.currentTime = ts
    else el.addEventListener('durationchange', () => { el.currentTime = ts }, { once: true })
  }
  el.play().catch(() => {})
}

function setMediaSession(cur) {
  if (!('mediaSession' in navigator)) return
  const artwork = cur.coverImageId ? [
    { src: igdbUrl(cur.coverImageId, 't_cover_big'),    sizes: '264x374', type: 'image/jpeg' },
    { src: igdbUrl(cur.coverImageId, 't_cover_big_2x'), sizes: '528x748', type: 'image/jpeg' },
  ] : []
  navigator.mediaSession.metadata = new MediaMetadata({
    title:  cur.episode,
    artist: cur.game,
    album:  'Silence on Joue',
    artwork,
  })
  navigator.mediaSession.setActionHandler('play',  () => audioEl.value?.play())
  navigator.mediaSession.setActionHandler('pause', () => audioEl.value?.pause())
}

function close() {
  if (audioEl.value) { audioEl.value.pause(); audioEl.value.src = '' }
  if ('mediaSession' in navigator) navigator.mediaSession.metadata = null
  playerStore.close()
}

function onPause() {
  playerStore.setPaused(true)
  if ('mediaSession' in navigator) navigator.mediaSession.playbackState = 'paused'
}
function onPlay() {
  playerStore.setPaused(false)
  if ('mediaSession' in navigator) navigator.mediaSession.playbackState = 'playing'
}
</script>

<template>
  <div class="audio-player" :class="{ active: playerStore.visible }">
    <template v-if="playerStore.current">
      <div class="player-info">
        <span class="player-game">{{ playerStore.current.game }}</span>
        <span class="player-sep">·</span>
        <span class="player-episode">{{ playerStore.current.episode }}</span>
        <span v-if="playerStore.current.timestamp" class="player-ts">
          ⏱ {{ playerStore.current.timestamp }}
        </span>
      </div>
      <button class="btn btn-circle btn-ghost !size-9 !min-h-9 text-[1.1rem] [grid-area:close] self-center" @click="close" aria-label="Fermer le lecteur">✕</button>
    </template>
    <audio
      id="audioEl"
      ref="audioEl"
      controls
      @pause="onPause"
      @play="onPlay"
    ></audio>
  </div>
</template>
