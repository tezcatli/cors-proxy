<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { usePlayerStore } from '../stores/player.js'
import { igdbUrl } from '../lib/igdbCdn.js'
import { useArtworkAccent } from '../composables/useArtworkAccent.js'
import { useMediaSession } from '../composables/useMediaSession.js'
import { useBottomSheetDrag } from '../composables/useBottomSheetDrag.js'
import { useMarquee } from '../composables/useMarquee.js'
import { Play, Pause, SkipBack, RotateCw, RotateCcw, ChevronRight, Volume2, VolumeX, Gamepad2, X } from 'lucide-vue-next'

const router      = useRouter()
const playerStore = usePlayerStore()
const audioEl     = ref(null)
const marqueeEl   = ref(null)
const playerEl    = ref(null)

// ── Per-track accent ────────────────────────────────────────────────────────
const currentCoverId = computed(() => playerStore.current?.coverImageId ?? null)
const { cssVars } = useArtworkAccent(currentCoverId)

const playerCoverSrc = computed(() => {
  const chapter = playerStore.currentChapter
  if (chapter) {
    return chapter.coverImageId
      ? igdbUrl(chapter.coverImageId, 't_cover_small')
      : (playerStore.current?.episodeImageUrl ?? null)
  }
  const id = playerStore.current?.coverImageId
  return id ? igdbUrl(id, 't_cover_small') : (playerStore.current?.episodeImageUrl ?? null)
})

// ── Player state ────────────────────────────────────────────────────────────
const collapsed = ref(true)
const duration  = ref(0)
const volume    = ref(1)

const seekProgress = computed(() =>
  duration.value > 0 ? (playerStore.currentTime / duration.value) * 100 : 0
)

const visibleChapters = computed(() =>
  (playerStore.current?.chapters ?? []).filter(c => c.timestampSeconds > 0)
)

// ── Audio play/pause (tolerant of the in-flight play() promise) ──────────────
let playPromise = null
let _lastHandledVersion = 0

function safePlay() {
  playPromise = audioEl.value?.play() ?? null
  playPromise
    ?.catch(err => { if (err.name !== 'AbortError') console.error(err) })
    .finally(() => { playPromise = null })
}

function safePause() {
  if (playPromise) {
    playPromise.then(() => { try { audioEl.value?.pause() } catch (_) {} }).catch(() => {})
  } else {
    try { audioEl.value?.pause() } catch (_) {}
  }
}

// ── MediaSession (lock-screen / OS controls) ─────────────────────────────────
const { initMediaSession, setMSState, updatePositionState } =
  useMediaSession(playerStore, audioEl, { safePlay, safePause })

// ── Controls ────────────────────────────────────────────────────────────────
function togglePlay()      { playerStore.paused ? safePlay() : safePause() }
function toggleCollapsed() { collapsed.value = !collapsed.value }
function closePlayer()     { safePause(); playerStore.close() }

function goToChapterStart() {
  if (!audioEl.value) return
  audioEl.value.currentTime = playerStore.currentChapter?.timestampSeconds ?? 0
}
function jumpForward() {
  if (!audioEl.value) return
  audioEl.value.currentTime = Math.min(duration.value, audioEl.value.currentTime + 30)
}
function jumpBack() {
  if (!audioEl.value) return
  audioEl.value.currentTime = Math.max(0, audioEl.value.currentTime - 30)
}
function onSeek(e)   { if (audioEl.value) audioEl.value.currentTime = parseFloat(e.target.value) }
function onVolume(e) { if (audioEl.value) audioEl.value.volume = parseFloat(e.target.value) }

function onArtInfoClick() {
  const chapter = playerStore.currentChapter
  if (chapter?.slug) router.push('/game/' + encodeURIComponent(chapter.slug))
  else navigateToEpisode()
}
function onArtKey(e) {
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onArtInfoClick() }
}

function navigateToEpisode() {
  const cur = playerStore.current
  if (!cur) return
  if (cur.episodeSlug)
    router.push({ path: `/episode/${encodeURIComponent(cur.episodeSlug)}`, query: cur.slug ? { game: cur.slug } : {} })
  else if (cur.slug)
    router.push('/game/' + encodeURIComponent(cur.slug))
}

// ── Alternating episode / chapter title ──────────────────────────────────────
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

// ── Marquee overflow detection ───────────────────────────────────────────────
const { needsScroll } = useMarquee(marqueeEl, currentLabel)

// ── Bottom-sheet swipe (mobile only) ─────────────────────────────────────────
const {
  dragExpand, isDragging, dragX, sheetStyle, reset: resetDrag,
  onPointerDown, onPointerMove, onPointerUp, onPointerCancel,
} = useBottomSheetDrag(playerEl, collapsed, closePlayer)

// ── Audio element ↔ store sync ───────────────────────────────────────────────
watch(() => playerStore.paused, paused => {
  if (!audioEl.value || !playerStore.current) return
  if (playerStore.playVersion !== _lastHandledVersion) return
  if (paused && !audioEl.value.paused) safePause()
  else if (!paused && audioEl.value.paused) safePlay()
})

watch(collapsed, v => {
  document.body.classList.toggle('player-expanded', !v)
}, { immediate: true })

function onTimeUpdate() {
  playerStore.setCurrentTime(audioEl.value?.currentTime ?? 0)
  updatePositionState()
}
function onSeeked() {
  playerStore.setCurrentTime(audioEl.value?.currentTime ?? 0)
  updatePositionState()
}

// Named handlers for clean removal in onUnmounted
function onPlay()      { playerStore.setPaused(false); setMSState('playing'); if (playerStore.current) initMediaSession(playerStore.current) }
function onPause()     { playerStore.setPaused(true);  setMSState('paused')  }
function onEnded()     { playerStore.setPaused(true);  setMSState('none')    }
function onDurChange() {
  duration.value = audioEl.value?.duration || 0
  playerStore.setDuration(duration.value)
}
function onVolChange() { volume.value = audioEl.value?.volume ?? 1 }

onMounted(() => {
  const el = audioEl.value
  el.addEventListener('timeupdate',    onTimeUpdate)
  el.addEventListener('seeked',        onSeeked)
  el.addEventListener('play',          onPlay)
  el.addEventListener('pause',         onPause)
  el.addEventListener('ended',         onEnded)
  el.addEventListener('durationchange',onDurChange)
  el.addEventListener('volumechange',  onVolChange)
})

onUnmounted(() => {
  const el = audioEl.value
  el?.removeEventListener('timeupdate',    onTimeUpdate)
  el?.removeEventListener('seeked',        onSeeked)
  el?.removeEventListener('play',          onPlay)
  el?.removeEventListener('pause',         onPause)
  el?.removeEventListener('ended',         onEnded)
  el?.removeEventListener('durationchange',onDurChange)
  el?.removeEventListener('volumechange',  onVolChange)
  stopFlip()
  document.body.classList.remove('player-expanded')
})

watch(() => playerStore.playVersion, () => {
  resetDrag()
  _lastHandledVersion = playerStore.playVersion
  const cur = playerStore.current
  if (!cur || !audioEl.value) return

  playerStore.setCurrentTime(cur.ts ?? 0)
  cur.chapters?.length ? startFlip() : stopFlip()
  initMediaSession(cur)

  audioEl.value.src = cur.url
  audioEl.value.load()

  const ts              = cur.ts ?? 0
  const capturedVersion = playerStore.playVersion

  audioEl.value.addEventListener('loadedmetadata', () => {
    duration.value = audioEl.value.duration || 0
    if (playerStore.playVersion !== capturedVersion) return
    audioEl.value.currentTime = ts
    if (!playerStore.paused) safePlay()
  }, { once: true })
})

watch(() => playerStore.visible, visible => {
  if (!visible) {
    safePause()
    stopFlip()
    collapsed.value = true
    resetDrag()
    if ('mediaSession' in navigator) navigator.mediaSession.metadata = null
  }
})
</script>

<template>
  <div
    ref="playerEl"
    class="audio-player"
    :class="{ active: playerStore.visible, 'is-expanded': !collapsed }"
    :style="[cssVars, sheetStyle]"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
    @pointercancel="onPointerCancel"
  >
    <template v-if="playerStore.current">
      <!-- Row 1: always visible -->
      <div class="player-row1">
        <!-- Cover thumb -->
        <div class="player-art" @click="onArtInfoClick" @keydown="onArtKey" role="button" tabindex="0" :aria-label="`Voir : ${playerStore.current.episode}`">
          <img v-if="playerCoverSrc" :src="playerCoverSrc" :alt="playerStore.current.episode" />
          <div v-else class="w-full h-full flex items-center justify-center text-white/40">
            <Gamepad2 :size="20" :stroke-width="1.75" />
          </div>
        </div>

        <!-- Info -->
        <div class="player-info" @click="onArtInfoClick">
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

        <!-- Desktop-only controls -->
        <div class="player-desktop-controls">
          <button class="player-ctrl-btn" @click.stop="goToChapterStart" aria-label="Début du chapitre">
            <SkipBack :size="15" :stroke-width="2" />
          </button>
          <button class="player-ctrl-btn" @click.stop="jumpBack" aria-label="Reculer 30 secondes">
            <RotateCcw :size="15" :stroke-width="2" /><span class="player-ctrl-label">30</span>
          </button>
          <button class="player-ctrl-btn" @click.stop="jumpForward" aria-label="Avancer 30 secondes">
            <RotateCw :size="15" :stroke-width="2" /><span class="player-ctrl-label">30</span>
          </button>
          <button class="player-ctrl-btn" @click.stop="navigateToEpisode" aria-label="Aller à l'épisode">
            <ChevronRight :size="15" :stroke-width="2" />
          </button>
        </div>

        <!-- Desktop-only seek -->
        <div class="player-desktop-seek">
          <div class="seek-wrap">
            <div class="seek-track">
              <div class="seek-fill" :style="{ width: seekProgress + '%' }"></div>
              <span
                v-for="ch in visibleChapters"
                :key="ch.timestampSeconds"
                class="seek-marker"
                :style="{ left: (ch.timestampSeconds / (duration || 1) * 100) + '%' }"
              />
            </div>
            <div class="seek-thumb" :style="{ left: seekProgress + '%' }"></div>
            <input
              type="range" class="seek-input"
              min="0" :max="duration || 100"
              :value="playerStore.currentTime"
              @input="onSeek"
              aria-label="Position"
            />
          </div>
        </div>

        <!-- Play/pause: always visible -->
        <button class="icon-action" @click.stop="togglePlay" :aria-label="playerStore.paused ? 'Lire' : 'Pause'">
          <Pause v-if="!playerStore.paused" :size="18" :stroke-width="2" />
          <Play  v-else                     :size="18" :stroke-width="2" />
        </button>

        <!-- Desktop-only volume -->
        <div class="player-desktop-volume">
          <component :is="volume === 0 ? VolumeX : Volume2" :size="14" :stroke-width="2" class="flex-shrink-0 opacity-60" />
          <input
            type="range" class="volume-input"
            min="0" max="1" step="0.01"
            :value="volume"
            @input="onVolume"
            aria-label="Volume"
          />
        </div>

        <!-- Desktop-only close -->
        <button class="player-close-btn" @click.stop="closePlayer" aria-label="Fermer le lecteur">
          <X :size="14" :stroke-width="2" />
        </button>
      </div>

      <!-- Mobile seek bar (hidden when collapsed) -->
      <div class="player-mobile-seek"
        :style="dragExpand !== null ? { maxHeight: Math.round(42 * dragExpand) + 'px', opacity: dragExpand, ...(isDragging ? { transition: 'none' } : {}) } : {}">
        <div class="seek-wrap">
          <div class="seek-track">
            <div class="seek-fill" :style="{ width: seekProgress + '%' }"></div>
            <span
              v-for="ch in visibleChapters"
              :key="ch.timestampSeconds"
              class="seek-marker"
              :style="{ left: (ch.timestampSeconds / (duration || 1) * 100) + '%' }"
            />
          </div>
          <div class="seek-thumb" :style="{ left: seekProgress + '%' }"></div>
          <input
            type="range" class="seek-input"
            min="0" :max="duration || 100"
            :value="playerStore.currentTime"
            @input="onSeek"
            aria-label="Position"
          />
        </div>
      </div>

      <!-- Mobile controls row (hidden when collapsed) -->
      <div class="player-mobile-controls"
        :style="dragExpand !== null ? { maxHeight: Math.round(62 * dragExpand) + 'px', opacity: dragExpand, ...(isDragging ? { transition: 'none' } : {}) } : {}">
        <div class="player-controls-inner">
          <button class="player-ctrl-btn" @click="goToChapterStart" aria-label="Début du chapitre">
            <SkipBack :size="18" :stroke-width="2" />
          </button>
          <button class="player-ctrl-btn" @click="jumpBack" aria-label="Reculer 30 secondes">
            <RotateCcw :size="18" :stroke-width="2" /><span class="player-ctrl-label">30</span>
          </button>
          <button class="player-ctrl-btn" @click="jumpForward" aria-label="Avancer 30 secondes">
            <RotateCw :size="18" :stroke-width="2" /><span class="player-ctrl-label">30</span>
          </button>
          <button class="player-ctrl-btn" @click="navigateToEpisode" aria-label="Aller à l'épisode">
            <ChevronRight :size="18" :stroke-width="2" />
          </button>
        </div>
      </div>
    </template>

    <audio ref="audioEl" style="display:none"></audio>
  </div>
</template>
