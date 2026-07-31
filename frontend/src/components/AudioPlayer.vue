<script setup>
import { ref, computed, watch, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { usePlayerStore } from '../stores/player.js'
import { igdbUrl } from '../lib/igdbCdn.js'
import { useArtworkAccent } from '../composables/useArtworkAccent.js'
import { useMediaSession } from '../composables/useMediaSession.js'
import { useBottomSheetDrag } from '../composables/useBottomSheetDrag.js'
import Marquee from './Marquee.vue'
import SeekBar from './SeekBar.vue'
import { Play, Pause, SkipBack, RotateCw, RotateCcw, ChevronRight, Volume2, VolumeX, Gamepad2, X, Loader2, AlertTriangle, RefreshCw } from 'lucide-vue-next'

const router      = useRouter()
const playerStore = usePlayerStore()
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

// ── Player state (audio itself lives in the store's engine) ─────────────────
const collapsed = ref(true)
const duration  = computed(() => playerStore.audioDuration)
const volume    = computed(() => playerStore.volume)

// Spinner shows while playback is wanted but hasn't started; once the engine
// gives up, the retry affordance takes over instead of spinning forever.
const showSpinner = computed(() => playerStore.buffering && !playerStore.failed)

const seekProgress = computed(() =>
  duration.value > 0 ? (playerStore.currentTime / duration.value) * 100 : 0
)

const visibleChapters = computed(() =>
  (playerStore.current?.chapters ?? []).filter(c => c.timestampSeconds > 0)
)

// ── MediaSession (lock-screen / OS controls) ─────────────────────────────────
const { initMediaSession, setMSState, updatePositionState } = useMediaSession(playerStore)

// ── Controls ────────────────────────────────────────────────────────────────
function togglePlay() {
  playerStore.failed ? playerStore.retry() : playerStore.togglePlayback()
}
function toggleCollapsed() { collapsed.value = !collapsed.value }
function onGripKey(e) {
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleCollapsed() }
}
function closePlayer() { playerStore.close() }

function goToChapterStart() { playerStore.seek(playerStore.currentChapter?.timestampSeconds ?? 0) }
function jumpForward() { playerStore.seek(Math.min(duration.value || Infinity, playerStore.currentTime + 30)) }
function jumpBack()    { playerStore.seek(Math.max(0, playerStore.currentTime - 30)) }
function onSeek(time)  { playerStore.seek(time) }
function onVolume(e)   { playerStore.setVolume(parseFloat(e.target.value)) }

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
    router.push({ path: `/episode/${encodeURIComponent(cur.episodeUrlSlug ?? cur.episodeSlug)}`, query: cur.slug ? { game: cur.slug } : {} })
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

// ── Bottom-sheet swipe (mobile only) ─────────────────────────────────────────
const {
  dragExpand, isDragging, sheetStyle, reset: resetDrag,
  onPointerDown, onPointerMove, onPointerUp, onPointerCancel,
} = useBottomSheetDrag(playerEl, collapsed, closePlayer)

// ── Store-driven side effects ────────────────────────────────────────────────
watch(collapsed, v => {
  document.body.classList.toggle('player-expanded', !v)
}, { immediate: true })

// New track: restart the title flip and rebuild the OS media card.
watch(() => playerStore.current?.url, () => {
  const cur = playerStore.current
  if (!cur) { stopFlip(); return }
  resetDrag()
  cur.chapters?.length ? startFlip() : stopFlip()
  initMediaSession(cur)
}, { immediate: true })

watch(() => playerStore.status, s => {
  if (s === 'playing') {
    setMSState('playing')
    if (playerStore.current) initMediaSession(playerStore.current)
  } else {
    setMSState(s === 'idle' ? 'none' : 'paused')
  }
})

watch(() => playerStore.currentTime, () => updatePositionState())

onUnmounted(() => {
  stopFlip()
  document.body.classList.remove('player-expanded')
})

watch(() => playerStore.visible, visible => {
  if (!visible) {
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
    class="audio-player glass-chrome"
    :class="{ active: playerStore.visible, 'is-expanded': !collapsed, 'player--resume': playerStore.restored && playerStore.paused }"
    :style="[cssVars, sheetStyle]"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
    @pointercancel="onPointerCancel"
  >
    <template v-if="playerStore.current">
      <!-- Mobile grab handle: tap toggles expand/collapse (drag still works) -->
      <div class="player-grip" @click="toggleCollapsed" @keydown="onGripKey" :aria-label="collapsed ? 'Développer le lecteur' : 'Réduire le lecteur'" role="button" tabindex="0"></div>

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
        <div class="player-info" @click="onArtInfoClick" @keydown="onArtKey" role="button" tabindex="0" :aria-label="`Voir : ${playerStore.current.episode}`">
          <Transition name="player-tick">
            <Marquee
              :key="tickKey"
              :text="currentLabel"
              class="player-marquee"
              :inner-class="isShowingChapter ? 'player-chapter' : 'player-episode'"
            />
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
          <SeekBar :progress="seekProgress" :duration="duration" :chapters="visibleChapters" :current-time="playerStore.currentTime" @seek="onSeek" />
        </div>

        <!-- Play/pause: always visible. Becomes « Réessayer » once the engine
             has exhausted its recovery attempts. -->
        <button
          class="icon-action"
          :class="{ 'is-failed': playerStore.failed }"
          @click.stop="togglePlay"
          :aria-label="playerStore.failed ? 'Réessayer' : (playerStore.restored && playerStore.paused ? 'Reprendre' : (playerStore.paused ? 'Lire' : 'Pause'))"
        >
          <RefreshCw v-if="playerStore.failed" :size="18" :stroke-width="2" />
          <Loader2  v-else-if="showSpinner"   :size="18" :stroke-width="2" class="player-spin" />
          <Pause    v-else-if="!playerStore.paused" :size="18" :stroke-width="2" />
          <Play     v-else                    :size="18" :stroke-width="2" />
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

      <!-- Playback gave up: say so and offer the retry (never a stuck spinner) -->
      <button v-if="playerStore.failed" class="player-error" @click.stop="playerStore.retry()">
        <AlertTriangle :size="13" :stroke-width="2" />
        <span>Lecture interrompue — touchez pour réessayer</span>
      </button>

      <!-- Mobile seek bar (hidden when collapsed) -->
      <div class="player-mobile-seek"
        :style="dragExpand !== null ? { maxHeight: Math.round(52 * dragExpand) + 'px', opacity: dragExpand, ...(isDragging ? { transition: 'none' } : {}) } : {}">
        <SeekBar :progress="seekProgress" :duration="duration" :chapters="visibleChapters" :current-time="playerStore.currentTime" @seek="onSeek" />
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
      <!-- Collapsed-state progress hairline (mobile only) -->
      <div v-if="collapsed" class="player-hairline">
        <div class="player-hairline__fill" :style="{ width: seekProgress + '%' }"></div>
      </div>
    </template>
  </div>
</template>
