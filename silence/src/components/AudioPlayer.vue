<script setup>
import { ref, computed, watch, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { usePlayerStore } from '../stores/player.js'
import { igdbUrl } from '../lib/igdbCdn.js'
import Plyr from 'plyr'
import 'plyr/dist/plyr.css'

const isTouchDevice = 'ontouchstart' in window || navigator.maxTouchPoints > 0

const router      = useRouter()
const playerStore = usePlayerStore()
const audioEl     = ref(null)
const plyrWrapEl  = ref(null)
const marqueeEl   = ref(null)
const needsScroll = ref(false)

// Plain variable — Plyr's proxy breaks Vue reactivity if stored in a ref
let plyrInstance    = null
let currentLoadedUrl = null   // the URL currently in the <audio> element

function destroyPlyr() {
  if (plyrInstance) {
    try { plyrInstance.destroy() } catch (_) {}
    plyrInstance = null
  }
  if (!plyrWrapEl.value || !audioEl.value) return
  plyrWrapEl.value.appendChild(audioEl.value)
  ;[...plyrWrapEl.value.children].forEach(c => { if (c !== audioEl.value) c.remove() })
}

// Plyr is kept alive across source changes — update markers manually in its progress bar.
function updatePlyrMarkers(chapters) {
  const progress = plyrWrapEl.value?.querySelector('.plyr__progress')
  if (!progress) return
  progress.querySelectorAll('.plyr__progress__marker').forEach(el => el.remove())
  const duration = audioEl.value?.duration
  if (!duration || !chapters?.length) return
  for (const ch of chapters) {
    const span = document.createElement('span')
    span.className = 'plyr__progress__marker'
    span.style.left = `${(ch.timestampSeconds / duration) * 100}%`
    progress.appendChild(span)
  }
}

// Alternating episode title / chapter name display
const showEpisode = ref(true)
let flipTimer = null

function startFlip() {
  clearInterval(flipTimer)
  showEpisode.value = true
  flipTimer = setInterval(() => { showEpisode.value = !showEpisode.value }, 5000)
}
function stopFlip() {
  clearInterval(flipTimer)
  flipTimer = null
  showEpisode.value = true
}

const currentLabel = computed(() => {
  if (!playerStore.current) return ''
  return (showEpisode.value || !playerStore.currentChapter)
    ? playerStore.current.episode
    : playerStore.currentChapter.title
})

const tickKey          = computed(() => showEpisode.value ? 'ep' : 'ch')
const isShowingChapter = computed(() => !showEpisode.value && !!playerStore.currentChapter)

// Overflow detection for marquee auto-scroll
async function checkScroll() {
  await nextTick()
  if (!marqueeEl.value) { needsScroll.value = false; return }
  const inner = marqueeEl.value.firstElementChild
  needsScroll.value = inner ? inner.offsetWidth > marqueeEl.value.clientWidth : false
}

let resizeObs = null
watch(marqueeEl, el => {
  resizeObs?.disconnect()
  resizeObs = null
  if (el) {
    resizeObs = new ResizeObserver(checkScroll)
    resizeObs.observe(el)
    checkScroll()
  }
})
watch(currentLabel, checkScroll)
onUnmounted(() => { destroyPlyr(); resizeObs?.disconnect(); stopFlip() })

function navigateToEpisode() {
  const cur = playerStore.current
  if (!cur) return
  if (cur.pubTs) router.push(`/game/${encodeURIComponent(cur.slug)}/episode/${cur.pubTs}`)
  else           router.push('/game/' + encodeURIComponent(cur.slug))
}

function setMSState(state) {
  if ('mediaSession' in navigator) navigator.mediaSession.playbackState = state
}

function setMediaSession(cur) {
  if (!('mediaSession' in navigator)) {
    console.log('MediaSession not supported in this browser')
    return
  }

  const metadata = new MediaMetadata({
    title:  cur.episode,
    album:  'Silence on Joue',
    //artist: cur.game,
    artwork: cur.coverImageId ? [
      { src: igdbUrl(cur.coverImageId, 't_cover_big_2x'), sizes: '512x512', type: 'image/jpeg' }
    ] : [cur.episodeImageUrl ? { src: cur.episodeImageUrl, sizes: '512x512', type: 'image/jpeg' } : null].filter(Boolean),
  })

  navigator.mediaSession.metadata = metadata
  
  navigator.mediaSession.setActionHandler('play',  () => {
    console.log('MediaSession play handler called')
    plyrInstance?.play()
  })
  navigator.mediaSession.setActionHandler('pause', () => {
    console.log('MediaSession pause handler called')
    plyrInstance?.pause()
  })
}

// ── Play commands (fired on every playerStore.play() call) ───────────────────
watch(() => playerStore.playVersion, () => {
  const cur = playerStore.current
  if (!cur || !audioEl.value) return

  // Set immediately so chapter highlighting in EpisodeView is correct before audio seeks
  playerStore.setCurrentTime(cur.ts ?? 0)
  cur.chapters?.length ? startFlip() : stopFlip()

  // Same audio already loaded — just seek
  if (plyrInstance && currentLoadedUrl === cur.url) {
    audioEl.value.currentTime = cur.ts ?? 0
    plyrInstance.play()
    return
  }

  // Different episode — update the source directly on the <audio> element.
  // Plyr stays alive; its UI adapts automatically via the media events it already listens to.
  audioEl.value.src = cur.url
  currentLoadedUrl  = cur.url
  audioEl.value.load()

  const ts              = cur.ts ?? 0
  const capturedVersion = playerStore.playVersion

  audioEl.value.addEventListener('loadedmetadata', () => {
    if (playerStore.playVersion !== capturedVersion) return  // superseded by a newer play()

    // Create Plyr once per player session (destroyed only when the player closes)
    if (!plyrInstance) {
      plyrInstance = new Plyr(audioEl.value, {
        controls: isTouchDevice
          ? ['play', 'progress', 'current-time', 'duration']
          : ['play', 'progress', 'current-time', 'duration', 'mute', 'volume'],
        resetOnEnd: false,
      })
      plyrInstance.on('play',  () => {
        playerStore.setPaused(false)
        setMSState('playing')
        // Set MediaSession after audio starts playing
        if (playerStore.current) setMediaSession(playerStore.current)
      })
    }

    updatePlyrMarkers(cur.chapters)  // inject chapter ticks now that duration is known
    if (ts > 0) audioEl.value.currentTime = ts
    plyrInstance.play()
  }, { once: true })

  setMediaSession(cur)
})

// ── Player closed ────────────────────────────────────────────────────────────
watch(() => playerStore.visible, visible => {
  if (!visible) {
    // Pause without destroying — recreating Plyr on every reopen causes UI regression
    // (custom controls lost, no chapter markers). Destroy happens only on unmount.
    try { plyrInstance?.pause() } catch (_) {}
    stopFlip()
    if ('mediaSession' in navigator) navigator.mediaSession.metadata = null
  }
})

// ── Cover image lazy-loaded after initial play ───────────────────────────────
watch(() => playerStore.current?.coverImageId, id => {
  if (id && playerStore.current) {
    console.log('Cover image loaded, updating MediaSession')
    setMediaSession(playerStore.current)
  }
})

function close() {
  playerStore.close()
}
</script>

<template>
  <div class="audio-player" :class="{ active: playerStore.visible }">
    <template v-if="playerStore.current">

      <!-- Info: episode title / current chapter alternating marquee -->
      <div class="player-info" @click="navigateToEpisode">
        <Transition name="player-tick">
          <div :key="tickKey" class="player-marquee" ref="marqueeEl" :class="{ 'player-marquee--on': needsScroll }" style="line-height: 1.0;padding:0;margin:0;">
            <div class="player-marquee-inner" :class="isShowingChapter ? 'player-chapter' : 'player-episode'">{{ currentLabel }}</div>
            <div v-if="needsScroll" class="player-marquee-inner" :class="isShowingChapter ? 'player-chapter' : 'player-episode'" aria-hidden="true">{{ currentLabel }}</div>
          </div>
        </Transition>
      </div>

      <!-- Close -->
      <button
        class="btn btn-circle btn-ghost !size-5 !min-h-5 text-[1.0rem] [grid-area:close] self-center"
        aria-label="Fermer le lecteur" style="line-height: 1.0;padding:0;margin:0;"
        @click="close"
      >✕</button>

    </template>

    <!-- Plyr wraps this element; the wrapper div holds the grid-area -->
    <div class="player-plyr-wrap" ref="plyrWrapEl">
      <audio ref="audioEl"></audio>
    </div>
  </div>
</template>
