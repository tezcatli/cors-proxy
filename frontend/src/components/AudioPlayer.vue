<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { usePlayerStore } from '../stores/player.js'
import { igdbUrl } from '../lib/igdbCdn.js'
import { useArtworkAccent } from '../composables/useArtworkAccent.js'
import ArtworkBackdrop from './ArtworkBackdrop.vue'
import { X, Gamepad2 } from 'lucide-vue-next'
import Plyr from 'plyr'
import 'plyr/dist/plyr.css'

const isTouchDevice = 'ontouchstart' in window || navigator.maxTouchPoints > 0

const router      = useRouter()
const playerStore = usePlayerStore()
const audioEl     = ref(null)
const plyrWrapEl  = ref(null)
const marqueeEl   = ref(null)
const playerEl    = ref(null)
const needsScroll = ref(false)

// ── Per-track accent ────────────────────────────────────────────────────────
const currentCoverId = computed(() => playerStore.current?.coverImageId ?? null)
const { cssVars } = useArtworkAccent(currentCoverId)

const playerCoverSrc = computed(() => {
  const id = playerStore.current?.coverImageId
  return id ? igdbUrl(id, 't_cover_small') : (playerStore.current?.episodeImageUrl ?? null)
})

// Plain variable — Plyr's proxy breaks Vue reactivity if stored in a ref
let plyrInstance     = null
let currentLoadedUrl = null
let playPromise      = null

function safePlay() {
  playPromise = plyrInstance?.play() ?? null
  playPromise
    ?.catch(err => { if (err.name !== 'AbortError') console.error(err) })
    .finally(() => { playPromise = null })
}

function safePause() {
  if (playPromise) {
    playPromise.then(() => { try { plyrInstance?.pause() } catch (_) {} }).catch(() => {})
  } else {
    try { plyrInstance?.pause() } catch (_) {}
  }
}

function destroyPlyr() {
  if (plyrInstance) {
    try { plyrInstance.destroy() } catch (_) {}
    plyrInstance = null
  }
  if (!plyrWrapEl.value || !audioEl.value) return
  plyrWrapEl.value.appendChild(audioEl.value)
  ;[...plyrWrapEl.value.children].forEach(c => { if (c !== audioEl.value) c.remove() })
}

function fixTimeDisplayWidth() {
  const durationEl = plyrWrapEl.value?.querySelector('.plyr__time--duration')
  const currentEl  = plyrWrapEl.value?.querySelector('.plyr__time--current')
  if (!durationEl || !currentEl) return
  const orig = currentEl.textContent
  currentEl.textContent = durationEl.textContent
  currentEl.style.minWidth = currentEl.offsetWidth + 'px'
  currentEl.textContent = orig
}

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

// ── Alternating episode / chapter title ────────────────────────────────────
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

watch(() => playerStore.paused, paused => {
  if (!plyrInstance || !playerStore.current) return
  if (paused && !plyrInstance.paused) safePause()
  else if (!paused && plyrInstance.paused) safePlay()
})

watch(() => playerStore.currentChapter, () => {
  if (!('mediaSession' in navigator) || !navigator.mediaSession.metadata) return
  syncMediaSessionMeta()
})

function updatePositionState() {
  const el = audioEl.value
  if (!('mediaSession' in navigator) || !el || !isFinite(el.duration) || el.duration <= 0) return
  try {
    navigator.mediaSession.setPositionState({
      duration:     el.duration,
      playbackRate: el.playbackRate,
      position:     el.currentTime,
    })
  } catch (_) {}
}

function onTimeUpdate() {
  playerStore.setCurrentTime(audioEl.value?.currentTime ?? 0)
  updatePositionState()
}
function onSeeked() {
  playerStore.setCurrentTime(audioEl.value?.currentTime ?? 0)
  updatePositionState()
}

// ── Bottom-sheet drag-to-dismiss (mobile only) ─────────────────────────────
const dragY = ref(0)
let dragStartY = 0
let dragActive = false

function onPointerDown(e) {
  if (!isTouchDevice) return
  if (window.matchMedia('(min-width: 900px)').matches) return
  if (e.target.closest('.plyr')) return
  dragStartY = e.clientY
  dragActive = true
  playerEl.value?.setPointerCapture?.(e.pointerId)
}
function onPointerMove(e) {
  if (!dragActive) return
  const dy = e.clientY - dragStartY
  if (dy <= 0) { dragY.value = 0; return }
  dragY.value = dy
}
function onPointerUp(e) {
  if (!dragActive) return
  dragActive = false
  playerEl.value?.releasePointerCapture?.(e.pointerId)
  if (dragY.value > 100) { close(); dragY.value = 0 }
  else { dragY.value = 0 }
}
const sheetStyle = computed(() => ({
  transform: dragY.value > 0 ? `translateY(${dragY.value}px)` : '',
  transition: dragY.value > 0 ? 'none' : 'transform var(--dur-med) var(--ease-out-soft)',
}))

onMounted(() => {
  audioEl.value?.addEventListener('timeupdate', onTimeUpdate)
  audioEl.value?.addEventListener('seeked', onSeeked)
})

onUnmounted(() => {
  audioEl.value?.removeEventListener('timeupdate', onTimeUpdate)
  audioEl.value?.removeEventListener('seeked', onSeeked)
  destroyPlyr()
  resizeObs?.disconnect()
  stopFlip()
})

function navigateToEpisode() {
  const cur = playerStore.current
  if (!cur) return
  if (cur.episodeSlug)
    router.push(`/episode/${encodeURIComponent(cur.episodeSlug)}/game/${encodeURIComponent(cur.slug)}`)
  else
    router.push('/game/' + encodeURIComponent(cur.slug))
}

function setMSState(state) {
  if ('mediaSession' in navigator) navigator.mediaSession.playbackState = state
}

function syncMediaSessionMeta() {
  if (!('mediaSession' in navigator)) return
  const meta = navigator.mediaSession.metadata
  if (!meta || !playerStore.current) return
  const cur     = playerStore.current
  const chapter = playerStore.currentChapter
  if (chapter) {
    meta.title   = chapter.title
    meta.artist  = cur.episode
    meta.artwork = chapter.coverImageId
      ? [{ src: igdbUrl(chapter.coverImageId, 't_cover_big_2x'), sizes: '512x512', type: 'image/jpeg' }]
      : cur.episodeImageUrl ? [{ src: cur.episodeImageUrl, sizes: '512x512', type: 'image/jpeg' }] : []
  } else {
    meta.title   = cur.episode
    meta.artist  = ''
    meta.artwork = cur.episodeImageUrl
      ? [{ src: cur.episodeImageUrl, sizes: '512x512', type: 'image/jpeg' }]
      : []
  }
}

function initMediaSession(cur) {
  if (!('mediaSession' in navigator)) return

  const episodeArt = cur.episodeImageUrl
    ? [{ src: cur.episodeImageUrl, sizes: '512x512', type: 'image/jpeg' }]
    : []

  const metadata = new MediaMetadata({
    title:   cur.episode,
    album:   'Silence on Joue',
    artwork: episodeArt,
  })

  try {
    if (cur.chapters?.length) {
      metadata.chapterInformation = cur.chapters.map(ch => ({
        title:     ch.title,
        startTime: ch.timestampSeconds,
        artwork:   ch.coverImageId
          ? [{ src: igdbUrl(ch.coverImageId, 't_cover_big_2x'), sizes: '512x512', type: 'image/jpeg' }]
          : episodeArt,
      }))
    }
  } catch (_) {}

  navigator.mediaSession.metadata = metadata

  navigator.mediaSession.setActionHandler('play',  () => safePlay())
  navigator.mediaSession.setActionHandler('pause', () => safePause())
  navigator.mediaSession.setActionHandler('seekto', details => {
    if (details.seekTime == null || !audioEl.value) return
    if (details.fastSeek && 'fastSeek' in audioEl.value) {
      audioEl.value.fastSeek(details.seekTime)
    } else {
      audioEl.value.currentTime = details.seekTime
    }
    updatePositionState()
  })

  if (cur.chapters?.length) {
    navigator.mediaSession.setActionHandler('previoustrack', () => {
      const chapters = playerStore.current?.chapters
      const t = audioEl.value?.currentTime ?? 0
      if (!chapters?.length) { if (audioEl.value) audioEl.value.currentTime = 0; return }
      let idx = -1
      for (let i = 0; i < chapters.length; i++) {
        if (chapters[i].timestampSeconds <= t) idx = i
        else break
      }
      if (idx >= 0 && t - chapters[idx].timestampSeconds > 3) {
        audioEl.value.currentTime = chapters[idx].timestampSeconds
      } else if (idx > 0) {
        audioEl.value.currentTime = chapters[idx - 1].timestampSeconds
      } else {
        audioEl.value.currentTime = 0
      }
    })
    navigator.mediaSession.setActionHandler('nexttrack', () => {
      const chapters = playerStore.current?.chapters
      const t = audioEl.value?.currentTime ?? 0
      if (!chapters?.length) return
      const next = chapters.find(ch => ch.timestampSeconds > t)
      if (next && audioEl.value) audioEl.value.currentTime = next.timestampSeconds
    })
  } else {
    navigator.mediaSession.setActionHandler('previoustrack', null)
    navigator.mediaSession.setActionHandler('nexttrack', null)
  }

  syncMediaSessionMeta()
}

watch(() => playerStore.playVersion, () => {
  const cur = playerStore.current
  if (!cur || !audioEl.value) return

  playerStore.setCurrentTime(cur.ts ?? 0)
  cur.chapters?.length ? startFlip() : stopFlip()
  initMediaSession(cur)

  if (plyrInstance && currentLoadedUrl === cur.url) {
    audioEl.value.currentTime = cur.ts ?? 0
    if (!playerStore.paused) safePlay()
    return
  }

  audioEl.value.src = cur.url
  currentLoadedUrl  = cur.url
  audioEl.value.load()

  const ts              = cur.ts ?? 0
  const capturedVersion = playerStore.playVersion

  audioEl.value.addEventListener('loadedmetadata', () => {
    if (playerStore.playVersion !== capturedVersion) return

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
        if (playerStore.current) initMediaSession(playerStore.current)
      })
      plyrInstance.on('pause', () => {
        playerStore.setPaused(true)
        setMSState('paused')
      })
      plyrInstance.on('ended', () => {
        playerStore.setPaused(true)
        setMSState('none')
      })
    }

    updatePlyrMarkers(cur.chapters)
    fixTimeDisplayWidth()
    if (ts > 0) audioEl.value.currentTime = ts
    if (!playerStore.paused) safePlay()
  }, { once: true })
})

watch(() => playerStore.visible, visible => {
  if (!visible) {
    safePause()
    stopFlip()
    if ('mediaSession' in navigator) navigator.mediaSession.metadata = null
  }
})

watch(() => playerStore.current?.episodeImageUrl, url => {
  if (url && playerStore.current) initMediaSession(playerStore.current)
})

function close() { playerStore.close() }
</script>

<template>
  <div
    ref="playerEl"
    class="audio-player"
    :class="{ active: playerStore.visible }"
    :style="[cssVars, sheetStyle]"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
    @pointercancel="onPointerUp"
  >
    <template v-if="playerStore.current">
      <!-- Cover thumb -->
      <div class="player-art" @click="navigateToEpisode" role="button" :aria-label="playerStore.current.episode">
        <img v-if="playerCoverSrc" :src="playerCoverSrc" :alt="playerStore.current.episode" />
        <div v-else class="w-full h-full flex items-center justify-center text-white/40">
          <Gamepad2 :size="20" :stroke-width="1.75" />
        </div>
      </div>

      <!-- Info -->
      <div class="player-info" @click="navigateToEpisode">
        <Transition name="player-tick">
          <div
            :key="tickKey"
            ref="marqueeEl"
            class="player-marquee"
            :class="{ 'player-marquee--on': needsScroll }"
            style="line-height: 1.2; padding: 0; margin: 0;"
          >
            <div
              class="player-marquee-inner"
              :class="isShowingChapter ? 'player-chapter' : 'player-episode'"
            >{{ currentLabel }}</div>
            <div
              v-if="needsScroll"
              class="player-marquee-inner"
              :class="isShowingChapter ? 'player-chapter' : 'player-episode'"
              aria-hidden="true"
            >{{ currentLabel }}</div>
          </div>
        </Transition>
      </div>

      <!-- Close -->
      <button
        class="btn btn-circle btn-ghost !size-7 !min-h-7 [grid-area:close] self-center hover:bg-white/10"
        aria-label="Fermer le lecteur"
        @click="close"
      ><X :size="14" :stroke-width="2.25" /></button>
    </template>

    <div class="player-plyr-wrap" ref="plyrWrapEl">
      <audio ref="audioEl"></audio>
    </div>
  </div>
</template>
