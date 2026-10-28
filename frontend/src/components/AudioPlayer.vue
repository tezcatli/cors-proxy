<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { usePlayerStore } from '../stores/player.js'
import { igdbUrl } from '../lib/igdbCdn.js'
import { formatTime } from '../lib/utils.js'
import { podcastMeta } from '../lib/podcasts.js'
import { useMediaSession } from '../composables/useMediaSession.js'
import { useGameTheme } from '../composables/useGameTheme.js'
import { useSwipe } from '../composables/useSwipe.js'
import SeekBar from './SeekBar.vue'
import VerdictMark from './VerdictMark.vue'
import MarqueeText from './MarqueeText.vue'
import JumpIcon from './JumpIcon.vue'
import { Play, Pause, SkipBack, SkipForward, Volume2, VolumeX, X, Loader2, RefreshCw, ArrowUpRight } from 'lucide-vue-next'

// The mini player (a bar over the bottom of the base views) and, on a phone,
// the full « En lecture » sheet it opens into. All audio goes through the store.
const RATES = [1, 1.25, 1.5, 1.75, 2]

const router      = useRouter()
const route       = useRoute()
const playerStore = usePlayerStore()

const cur      = computed(() => playerStore.current)
const test     = computed(() => playerStore.currentTest)
const duration = computed(() => playerStore.audioDuration)
const show     = computed(() => cur.value?.podcast?.name ?? podcastMeta(cur.value?.podcast?.id)?.name ?? '')

// What is on air (the store's `onAir`, shared with the lock screen): the test
// being heard, else the episode's image and the chapter.
const title = computed(() => playerStore.onAir?.title ?? '')
const coverId = computed(() => playerStore.onAir?.coverImageId ?? null)
const coverSrc = computed(() => coverId.value ? igdbUrl(coverId.value, 't_cover_big') : (playerStore.onAir?.imageUrl ?? null))
// The player is lit by the game on air (its accent; the sheet, its halo).
const { style: theme } = useGameTheme(coverId)

const nextMark = computed(() => playerStore.marks.find(m => m.timestampSeconds > playerStore.currentTime + 1) ?? null)
const segmentLabel = computed(() => {
  const now  = test.value ? title.value : (playerStore.currentChapter?.title ?? '')
  const next = nextMark.value ? (nextMark.value.resolvedName ?? nextMark.value.name ?? nextMark.value.title) : null
  return next ? `${now} ▸ ${next}` : now
})

const showSpinner = computed(() => playerStore.buffering && !playerStore.failed)
const playLabel = computed(() => playerStore.failed ? 'Réessayer'
  : playerStore.restored && playerStore.paused ? 'Reprendre'
  : playerStore.paused ? 'Lire' : 'Pause')

function togglePlay() { playerStore.failed ? playerStore.retry() : playerStore.togglePlayback() }
function jump(d)      { playerStore.seek(Math.min(duration.value || Infinity, Math.max(0, playerStore.currentTime + d))) }
function cycleRate() {
  const i = RATES.indexOf(playerStore.rate)
  playerStore.setRate(RATES[(i + 1) % RATES.length])
}
function rateLabel(r) { return `${String(r).replace('.', ',')}×` }

// ── « En lecture » sheet (phone) ────────────────────────────────────────────
// A step of the way (DECISIONS.md, « Interface »): `?lecteur=1` on the page
// under it, pushed on opening and marked in the entry's state, so the system's
// back closes it like any screen. Leaving it for a page replaces its entry:
// back from there returns to the page under the sheet.
const SHEET = 'lecteur'
const isPhone  = () => !window.matchMedia('(min-width: 768px)').matches
const sheetAsked = computed(() => route.query[SHEET] !== undefined)
const expanded = computed(() => route.query[SHEET] === '1' && playerStore.visible && !!cur.value && isPhone())
const sheetPushed = () => !!router.options.history.state?.ludoSheet

function withoutSheet() {
  const { [SHEET]: _, ...query } = route.query
  return { path: route.path, query, hash: route.hash }
}
function openSheet() {
  if (!expanded.value)
    router.push({ path: route.path, query: { ...route.query, [SHEET]: '1' }, hash: route.hash, state: { ludoSheet: true } })
}
function closeSheet() {
  if (!sheetAsked.value) return
  if (sheetPushed()) router.back()
  else router.replace(withoutSheet())
}
function leaveSheetFor(to) {
  if (!sheetAsked.value) return router.push(to)
  if (sheetPushed()) return router.replace(to)
  return router.replace(withoutSheet()).then(() => router.push(to))   // opened as such (a reload)
}
// Asked with nothing to show (nothing playing, a desktop): the address is wrong.
watch(() => sheetAsked.value && !expanded.value, stale => { if (stale) router.replace(withoutSheet()) })

function onKey(e) { if (e.key === 'Escape' && expanded.value) closeSheet() }
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))

// Gestures: the sheet is pulled down to shrink it (from its top while its body
// is scrolled); the bar is swiped up to open it, aside to close the player.
const reduceMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
const sheetEl = ref(null)
const sheetBody = ref(null)
const barEl = ref(null)
const { offset: sheetOffset, dragging: sheetDragging, reset: resetSheet } = useSwipe(sheetEl, {
  directions: ['down'],
  commitAt: () => (sheetEl.value?.offsetHeight || window.innerHeight) * 0.25,
  ignore: '.seek',
  scroller: () => sheetBody.value,
  onCommit: closeSheet,
})
const barLeaving = ref(false)
const { offset: barOffset, dragging: barDragging, reset: resetBar } = useSwipe(barEl, {
  directions: ['left', 'right', 'up'],
  commitAt: dir => dir === 'up' ? 40 : (barEl.value?.offsetWidth || window.innerWidth) * 0.4,
  onCommit: dir => {
    if (dir === 'up') { resetBar(); openSheet(); return }
    barLeaving.value = true
    setTimeout(() => playerStore.close(), reduceMotion() ? 0 : 180)
  },
})
watch(expanded, v => { if (!v) resetSheet() })
watch(() => playerStore.visible, v => { if (v) { barLeaving.value = false; resetBar() } })

const sheetStyle = computed(() => sheetOffset.value.y
  ? { transform: `translateY(${sheetOffset.value.y}px)`, transition: sheetDragging.value ? 'none' : undefined }
  : {})
const barStyle = computed(() => {
  const x = barLeaving.value ? Math.sign(barOffset.value.x || 1) * window.innerWidth : barOffset.value.x
  const y = barOffset.value.y
  if (!x && !y) return {}
  const width = barEl.value?.offsetWidth || window.innerWidth
  return {
    transform: `translate(${x}px, ${y}px)`,
    opacity: x ? Math.max(0, 1 - Math.abs(x) / width) : 1,
    transition: barDragging.value ? 'none' : undefined,
  }
})

// The sheet's ↺ and ↻ jump a minute at once; quick taps add up, their sum
// shown in place of the bar's caption until a second after the last
// (DECISIONS.md, « Interface »). A tap the other way starts the sum anew.
const JUMP_S = 60
const JUMP_GAP_MS = 1000
const jumpSum = ref(0)               // minutes, signed
let jumpTimer = null
function jumpMinute(dir) {
  if (Math.sign(jumpSum.value) !== dir) jumpSum.value = 0
  jumpSum.value += dir
  jump(dir * JUMP_S)
  clearTimeout(jumpTimer)
  jumpTimer = setTimeout(() => { jumpSum.value = 0 }, JUMP_GAP_MS)
}
const sheetCaption = computed(() => (jumpSum.value
  ? `${jumpSum.value < 0 ? '−' : '+'}${Math.abs(jumpSum.value)} min`
  : segmentLabel.value))
onUnmounted(() => clearTimeout(jumpTimer))
function openInfo() {
  if (isPhone()) openSheet()
  else goEpisode()
}
function goEpisode() {
  const c = cur.value
  if (!c) return
  if (c.episodeUrlSlug || c.episodeSlug)
    leaveSheetFor({ path: `/episode/${encodeURIComponent(c.episodeUrlSlug ?? c.episodeSlug)}`, query: test.value?.slug ? { game: test.value.slug } : {} })
  else if (test.value?.slug)
    leaveSheetFor('/game/' + encodeURIComponent(test.value.slug))
}
function goPodcast() {
  const id = cur.value?.podcast?.id
  if (!id) return
  leaveSheetFor('/podcast/' + id)
}
function goGame() {
  const slug = test.value?.slug
  if (!slug) return
  leaveSheetFor('/game/' + encodeURIComponent(slug))
}

// ── MediaSession (lock-screen / OS controls) ─────────────────────────────────
const { initMediaSession, setMSState, updatePositionState } = useMediaSession(playerStore)

watch(() => cur.value?.url, () => { if (cur.value) initMediaSession(cur.value) }, { immediate: true })
watch(() => playerStore.status, s => {
  if (s === 'playing') {
    setMSState('playing')
    if (cur.value) initMediaSession(cur.value)
  } else {
    setMSState(s === 'idle' ? 'none' : 'paused')
  }
})
watch(() => playerStore.currentTime, () => updatePositionState())
watch(() => playerStore.visible, v => {
  if (!v) {
    closeSheet()
    if ('mediaSession' in navigator) navigator.mediaSession.metadata = null
  }
})
watch(expanded, v => document.body.classList.toggle('player-expanded', v))
onUnmounted(() => document.body.classList.remove('player-expanded'))
</script>

<template>
  <div v-if="playerStore.visible && cur" class="player" :style="theme" :class="{ 'is-resume': playerStore.restored && playerStore.paused }">
    <!-- Above the bar: below it would sit in the system's gesture area. -->
    <button v-if="playerStore.failed" type="button" class="failed lab" @click="playerStore.retry()">Lecture interrompue — toucher pour réessayer</button>
    <!-- Mini bar -->
    <div ref="barEl" class="bar" :style="barStyle">
      <button type="button" class="bar__info" :aria-label="`En lecture : ${title}. Ouvrir`" @click="openInfo">
        <span class="onair" :class="{ 'is-off': playerStore.paused }" aria-hidden="true"></span>
        <img v-if="coverSrc" :src="coverSrc" alt="" class="bar__cover" />
        <span class="bar__text">
          <MarqueeText class="cond bar__title" :text="title" />
          <span class="mono bar__sub ellipsis">{{ show }} · {{ formatTime(playerStore.currentTime) }}<span class="bar__ep"> · {{ cur.episode }}</span></span>
        </span>
      </button>

      <div class="bar__controls">
        <button type="button" class="icon-action desk" aria-label="Test précédent" @click="playerStore.skip(-1)"><SkipBack :size="18" :stroke-width="2" /></button>
        <button type="button" class="bar__play" :class="{ 'is-failed': playerStore.failed }" :aria-label="playLabel" @click="togglePlay">
          <RefreshCw v-if="playerStore.failed" :size="18" :stroke-width="2" />
          <Loader2 v-else-if="showSpinner" :size="18" :stroke-width="2" class="animate-spin" />
          <Pause v-else-if="!playerStore.paused" :size="18" fill="currentColor" :stroke-width="0" />
          <Play v-else :size="18" fill="currentColor" :stroke-width="0" />
        </button>
        <button type="button" class="icon-action" aria-label="Test suivant" :disabled="!nextMark" @click="playerStore.skip(1)"><SkipForward :size="18" :stroke-width="2" /></button>
      </div>

      <div class="bar__seek desk">
        <SeekBar :duration="duration" :current-time="playerStore.currentTime" :marks="playerStore.marks" :label="segmentLabel" @seek="playerStore.seek" />
      </div>

      <div class="bar__tools desk">
        <button type="button" class="bar__rate mono" :aria-label="`Vitesse ${rateLabel(playerStore.rate)}, changer`" @click="cycleRate">{{ rateLabel(playerStore.rate) }}</button>
        <label class="bar__vol">
          <component :is="playerStore.volume === 0 ? VolumeX : Volume2" :size="16" :stroke-width="2" aria-hidden="true" />
          <input type="range" min="0" max="1" step="0.01" :value="playerStore.volume" aria-label="Volume" @input="playerStore.setVolume(parseFloat($event.target.value))" />
        </label>
        <button type="button" class="icon-action" aria-label="Fermer le lecteur" @click="playerStore.close()"><X :size="16" :stroke-width="2" /></button>
      </div>

      <!-- Collapsed phone bar: a hairline of progress along the top edge -->
      <span class="bar__hair" aria-hidden="true"><span :style="{ width: (duration ? playerStore.currentTime / duration * 100 : 0) + '%' }"></span></span>
    </div>


    <!-- « En lecture » sheet (phone). Teleported: the bar's entry transform
         would otherwise be the containing block of its `position: fixed`. -->
    <Teleport to="body">
    <Transition name="sheet">
    <div v-if="expanded" ref="sheetEl" class="sheet" :style="[theme, sheetStyle]" role="dialog" aria-modal="true" aria-label="En lecture">
      <span class="sheet__grip" aria-hidden="true"></span>
      <!-- No buttons: back and the pull down shrink it (DECISIONS, frontend). -->
      <div class="sheet__top">
        <span class="lab"><span class="onair" :class="{ 'is-off': playerStore.paused }"></span> En lecture</span>
      </div>

      <div class="halo" aria-hidden="true"></div>
      <div ref="sheetBody" class="sheet__body">
        <!-- Every element keeps its place whatever is on air, a chapter or a
             test: only its content changes, so nothing moves under the thumb. -->
        <span class="sheet__cover corners">
          <img v-if="coverSrc" :src="coverSrc" alt="" />
          <span v-else class="sheet__cover-none cond">{{ show }}</span>
        </span>
        <div class="sheet__titles">
          <h2 class="cond sheet__title"><MarqueeText :text="title" /></h2>
          <p class="sheet__verdict"><VerdictMark v-if="test" :verdict="test.critique?.verdict ?? test.verdict ?? null" /></p>
          <p class="mono sheet__ep clamp-2">{{ show }} · {{ cur.episode }}</p>
        </div>

        <SeekBar :duration="duration" :current-time="playerStore.currentTime" :marks="playerStore.marks" :label="sheetCaption" @seek="playerStore.seek" />

        <!-- One row: the tests at its ends, time beside ▶. -->
        <div class="sheet__controls">
          <button type="button" class="icon-action" aria-label="Test précédent" @click="playerStore.skip(-1)"><SkipBack :size="24" :stroke-width="2" /></button>
          <button type="button" class="icon-action" aria-label="Reculer d’une minute" @click="jumpMinute(-1)"><JumpIcon :dir="-1" :n="60" /></button>
          <button type="button" class="sheet__play" :aria-label="playLabel" @click="togglePlay">
            <RefreshCw v-if="playerStore.failed" :size="26" :stroke-width="2" />
            <Loader2 v-else-if="showSpinner" :size="26" :stroke-width="2" class="animate-spin" />
            <Pause v-else-if="!playerStore.paused" :size="26" fill="currentColor" :stroke-width="0" />
            <Play v-else :size="26" fill="currentColor" :stroke-width="0" />
          </button>
          <button type="button" class="icon-action" aria-label="Avancer d’une minute" @click="jumpMinute(1)"><JumpIcon :dir="1" :n="60" /></button>
          <button type="button" class="icon-action" aria-label="Test suivant" :disabled="!nextMark" @click="playerStore.skip(1)"><SkipForward :size="24" :stroke-width="2" /></button>
        </div>

        <!-- Where it comes from: one line each -->
        <div class="sheet__links lines">
          <button type="button" class="sheet__link line" :disabled="!test?.slug" @click="goGame">La fiche du jeu <ArrowUpRight :size="16" :stroke-width="2" /></button>
          <button type="button" class="sheet__link line" @click="goEpisode">L'épisode <ArrowUpRight :size="16" :stroke-width="2" /></button>
          <button v-if="cur.podcast?.id" type="button" class="sheet__link line" @click="goPodcast">Le podcast <ArrowUpRight :size="16" :stroke-width="2" /></button>
        </div>
      </div>
    </div>
    </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.player {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: var(--z-player);
  animation: slideUpPlayer var(--dur-med) var(--ease-out-soft) both;
}
.onair.is-off { background: var(--c-fg-3); box-shadow: none; }

.bar {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  /* Down to the screen's edge; its content above the system's gesture area. */
  height: calc(var(--player-h) + env(safe-area-inset-bottom, 0px));
  padding: 0 4px env(safe-area-inset-bottom, 0px) 12px;
  box-sizing: border-box;
  background: var(--c-surface);
  border-top: 1px solid var(--c-line);
  touch-action: none;      /* its swipes are its own (useSwipe) */
  transition: transform var(--dur-fast, 150ms) var(--ease-out-soft), opacity var(--dur-fast, 150ms);
}
.bar__info {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  height: 100%;
  border: 0;
  background: transparent;
  color: var(--c-fg);
  text-align: left;
  cursor: pointer;
  padding: 0;
}
.bar__cover { width: 36px; height: 48px; object-fit: cover; flex-shrink: 0; }
.bar__text { min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.bar__title { font-size: 19px; line-height: 1; }
.bar__sub { color: var(--c-fg-3); font-size: var(--text-xs); }
.bar__ep { display: none; }
.bar__controls { display: flex; align-items: center; gap: 2px; flex-shrink: 0; }
.bar__play {
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 0;
  background: var(--c-accent);
  color: var(--c-accent-fg);
  cursor: pointer;
}
.bar__play.is-failed { background: var(--c-danger); }
.player.is-resume .bar__play { animation: resumePulse 1.6s ease-in-out infinite; }
@keyframes resumePulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(255, 210, 63, 0.5); }
  50%      { box-shadow: 0 0 0 6px rgba(255, 210, 63, 0); }
}
.bar__hair { position: absolute; left: 0; right: 0; top: -1px; height: 2px; background: transparent; }
.bar__hair span { display: block; height: 100%; background: var(--c-accent); }
.desk { display: none !important; }

.bar__tools { align-items: center; gap: 4px; }
.bar__rate {
  min-width: 56px;
  height: 32px;
  border: 0;
  background: var(--c-raised);
  color: var(--c-fg);
  cursor: pointer;
  font-weight: 700;
}
.bar__vol { display: flex; align-items: center; gap: 8px; color: var(--c-fg-2); padding: 0 8px; }
.bar__vol input { width: 80px; accent-color: var(--c-accent); }

.failed {
  display: block;
  width: 100%;
  min-height: 36px;
  border: 0;
  background: var(--c-danger);
  color: var(--c-accent-fg);
  cursor: pointer;
}

@media (min-width: 768px) {
  .bar { gap: 20px; padding: 0 12px 0 var(--gutter); }
  .bar__info { flex: 0 1 300px; }
  .bar__ep { display: inline; }
  .desk { display: flex !important; }
  .bar__seek.desk { display: block !important; flex: 1; min-width: 160px; }
  .bar__hair { display: none; }
}

/* ─── Sheet ───────────────────────────────────────────────────────────── */
.sheet {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  display: flex;
  flex-direction: column;
  background: var(--c-bg);
  padding: env(safe-area-inset-top, 0px) 0 env(safe-area-inset-bottom, 0px);
  transition: transform var(--dur-med) var(--ease-out-soft);
}
/* Up on opening, down on closing — from wherever a pull left it. */
.sheet-enter-from, .sheet-leave-to { transform: translateY(100%) !important; }
.sheet-enter-active, .sheet-leave-active { transition: transform var(--dur-med) var(--ease-out-soft); }
.sheet__grip {
  position: absolute;
  z-index: 2;
  top: calc(env(safe-area-inset-top, 0px) + 5px);
  left: 50%;
  width: 36px;
  height: 4px;
  margin-left: -18px;
  border-radius: 2px;
  background: var(--c-fg-3);
}
@media (prefers-reduced-motion: reduce) {
  .bar, .sheet, .sheet-enter-active, .sheet-leave-active { transition: none; }
}
.sheet__top { position: relative; z-index: 1; display: flex; align-items: center; justify-content: center; min-height: 44px; padding: 8px 4px 4px; border-bottom: 1px solid var(--c-line); }
.sheet__top .lab { display: inline-flex; align-items: center; gap: 8px; color: var(--c-accent); }
.sheet__body { position: relative; flex: 1; overflow-y: auto; overscroll-behavior: contain; display: flex; flex-direction: column; gap: 22px; padding: 24px var(--gutter); }
.sheet__cover { --corner: 16px; display: block; width: min(56vw, 240px); aspect-ratio: 3 / 4; align-self: center; box-shadow: var(--shadow-cover); }
.sheet__cover img { display: block; width: 100%; height: 100%; object-fit: cover; }
.sheet__cover-none { display: flex; align-items: flex-end; height: 100%; padding: 14px; box-sizing: border-box; background: var(--c-surface); color: var(--c-fg-2); font-size: 22px; }
.sheet__verdict { margin: 0; min-height: 16px; line-height: 16px; display: flex; align-items: center; }
.sheet__titles { display: flex; flex-direction: column; gap: 8px; }
.sheet__title { margin: 0; font-size: 40px; font-weight: 700; line-height: 1.1; }
.sheet__ep { margin: 0; color: var(--c-fg-3); font-size: var(--text-xs); }
.sheet__controls { display: flex; align-items: center; justify-content: space-between; }
.sheet__play {
  width: 72px;
  height: 72px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 0;
  background: var(--c-accent);
  color: var(--c-accent-fg);
  cursor: pointer;
}
.sheet__link {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  min-height: 48px;
  padding: 0;
  border-left: 0;
  border-right: 0;
  border-bottom: 0;
  background: transparent;
  color: var(--c-fg);
  font-family: var(--font-display);
  font-size: var(--text-md);
  font-weight: 600;
  text-align: left;
  cursor: pointer;
}
.sheet__link svg { color: var(--c-accent); }
.sheet__link:disabled { color: var(--c-fg-3); cursor: default; }
.sheet__link:disabled svg { color: var(--c-fg-3); }
</style>
