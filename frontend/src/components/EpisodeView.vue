<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { usePlayerStore } from '../stores/player.js'
import { useGamesStore } from '../stores/games.js'
import { fetchEpisodeDetail } from '../lib/games.js'
import { formatShortDate, formatTime, progressPct, PROGRESS_MIN_PCT, PROGRESS_DONE_PCT } from '../lib/utils.js'
import { igdbUrl } from '../lib/igdbCdn.js'
import BackBar from './BackBar.vue'
import VerdictMark from './VerdictMark.vue'
import { useProgress } from '../composables/useProgress.js'
import { useGameTheme } from '../composables/useGameTheme.js'
import { Play, Pause, Check, ArrowUpRight } from 'lucide-vue-next'

const route       = useRoute()
const router      = useRouter()
const playerStore = usePlayerStore()
const gamesStore  = useGamesStore()

const { episodeProgress } = useProgress()

// Opened from a game's page, `?game=` names that game: the back label and the
// main button follow it.
const fromGame    = route.query.game ?? null
const episodeSlug = route.params.episodeSlug

const episode = ref(null)
const loading = ref(true)
const error   = ref(null)

onMounted(async () => {
  document.body.style.overflow = 'hidden'
  document.addEventListener('keydown', onKeydown)
  try {
    episode.value = await fetchEpisodeDetail(episodeSlug)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

const fromGameName = computed(() =>
  fromGame ? (gamesStore.all.find(g => g.slug === fromGame)?.name ?? 'Retour') : 'Tests')

function back() {
  if (router.options.history.state?.back) router.back()
  else if (fromGame) router.push('/game/' + fromGame)
  else router.push('/')
}

function onKeydown(e) { if (e.key === 'Escape') back() }

onUnmounted(() => {
  document.body.style.overflow = ''
  document.removeEventListener('keydown', onKeydown)
})

const tests = computed(() => episode.value?.games ?? [])

// The test the main button plays: the game we came from, else the first.
const leadTest = computed(() =>
  tests.value.find(t => fromGame && t.slug === fromGame) ?? tests.value[0] ?? null)
// The page wears that game's colours, and its cover is the backdrop.
const leadCover = computed(() => leadTest.value?.coverImageId ?? null)
const { style: theme } = useGameTheme(leadCover)

const isThisTrack = computed(() =>
  !!playerStore.current && playerStore.current.url === episode.value?.audioUrl)
const activeChapter = computed(() => isThisTrack.value ? playerStore.currentChapter : null)
const activeTest    = computed(() => isThisTrack.value ? playerStore.currentTest : null)

function playFrom(ts, test = leadTest.value) {
  const ep = episode.value
  if (!ep?.audioUrl) return
  playerStore.play({
    game:            test ? (test.resolvedName ?? test.name) : ep.title,
    slug:            test?.slug ?? null,
    episode:         ep.title,
    url:             ep.audioUrl,
    // Resume from saved progress when partway through; untouched/finished starts at `ts`.
    ts:              playerStore.resumeTimeFor(ep.slug, ts),
    timestamp:       test?.timestamp ?? null,
    episodeImageUrl: ep.imageUrl,
    pubTs:           ep.pubTs,
    episodeSlug:     ep.slug,
    episodeUrlSlug:  ep.urlSlug,
    coverImageId:    test?.coverImageId ?? null,
    chapters:        ep.chapters ?? [],
    podcast:         ep.podcast ?? null,
    tests:           ep.games ?? [],
  })
}

function playTest(t) {
  if (isThisTrack.value && activeTest.value?.timestampSeconds === t.timestampSeconds) playerStore.togglePlayback()
  else playFrom(t.timestampSeconds ?? 0, t)
}

// The latest saved position in this episode, when partway: « Reprendre à … ».
const resumeEntry = computed(() => {
  if (isThisTrack.value) return null
  const e = playerStore.getEpisodeLatestProgress(episode.value?.slug)
  if (!e?.chapterEnd) return null
  const pct = progressPct(e.currentTime, e.ts ?? 0, e.chapterEnd)
  return (pct >= PROGRESS_MIN_PCT && pct < PROGRESS_DONE_PCT) ? e : null
})

const mainLabel = computed(() => {
  if (isThisTrack.value) return playerStore.paused ? 'Reprendre' : 'Pause'
  if (resumeEntry.value) return `Reprendre à ${formatTime(resumeEntry.value.currentTime)}`
  if (leadTest.value?.timestamp) return `Écouter le test · ${leadTest.value.timestamp}`
  return 'Écouter'
})

function onMain() {
  if (isThisTrack.value) { playerStore.togglePlayback(); return }
  if (resumeEntry.value) {
    const t = tests.value.find(x => x.slug && x.slug === resumeEntry.value.gameSlug) ?? leadTest.value
    playFrom(resumeEntry.value.ts ?? 0, t)
    return
  }
  playFrom(leadTest.value?.timestampSeconds ?? 0)
}

const chapterRows = computed(() =>
  (episode.value?.chapters ?? []).map(ch => ({
    ...ch,
    progress: episodeProgress(episode.value.slug, ch.timestampSeconds ?? 0),
  }))
)

function playChapter(ch) {
  const t = tests.value.find(x => x.slug && x.slug === ch.slug) ?? null
  playFrom(ch.timestampSeconds, t)
}
</script>

<template>
  <div class="overlay-page" :style="[theme, { zIndex: 'var(--z-episode)' }]">
    <BackBar :label="fromGameName" @back="back" />

    <div v-if="loading || error || !episode" class="state">
      <span v-if="loading" class="lab">Chargement…</span>
      <p v-else-if="error" class="state__text">Erreur : {{ error }}</p>
      <p v-else class="cond state__title">Épisode introuvable</p>
    </div>

    <div v-else class="scroll-area ep-scroll">
      <div v-if="leadCover" class="backdrop" aria-hidden="true"><img :src="igdbUrl(leadCover, 't_cover_small')" alt="" /></div>
      <div class="content ep">
        <header class="ep__head">
          <div class="ep__show">
            <img v-if="episode.imageUrl" :src="episode.imageUrl" alt="" class="ep__art" />
            <span class="lab">{{ episode.podcast?.name }} · {{ formatShortDate(episode.pubTs) }}</span>
          </div>
          <h1 class="ep__title cond">{{ episode.title }}</h1>
          <button v-if="episode.audioUrl" type="button" class="btn-play ep__main" @click="onMain">
            <Pause v-if="isThisTrack && !playerStore.paused" :size="14" fill="currentColor" :stroke-width="0" />
            <Play v-else :size="14" fill="currentColor" :stroke-width="0" />
            {{ mainLabel }}
          </button>
        </header>

        <section v-if="tests.length" class="block" aria-labelledby="h-tests">
          <div class="section-head">
            <h2 id="h-tests">Les tests de l'épisode</h2>
            <span class="lab">{{ tests.length }}</span>
          </div>
          <article
            v-for="t in tests"
            :key="t.name + t.timestampSeconds"
            class="t"
            :class="{ 'is-playing': activeTest && activeTest.timestampSeconds === t.timestampSeconds }"
          >
            <div class="t__row">
              <img v-if="t.coverImageId" :src="igdbUrl(t.coverImageId, 't_cover_big')" alt="" class="t__cover" />
              <span v-else class="t__cover t__cover--none"></span>
              <div class="t__main">
                <span class="t__name cond clamp-2">{{ t.resolvedName ?? t.name }}</span>
                <span class="t__meta">
                  <VerdictMark :verdict="t.critique?.verdict ?? null" />
                  <span class="mono t__start">{{ t.timestamp ?? '0:00' }}</span>
                </span>
              </div>
              <div class="t__actions">
                <button
                  type="button"
                  class="icon-action"
                  :class="activeTest && activeTest.timestampSeconds === t.timestampSeconds ? 't__play is-on' : 't__play'"
                  :disabled="!episode.audioUrl"
                  :aria-label="`Écouter le test de ${t.resolvedName ?? t.name}`"
                  @click="playTest(t)"
                >
                  <Pause v-if="activeTest && activeTest.timestampSeconds === t.timestampSeconds && !playerStore.paused" :size="16" fill="currentColor" :stroke-width="0" />
                  <Play v-else :size="16" fill="currentColor" :stroke-width="0" />
                </button>
                <RouterLink v-if="t.slug" :to="`/game/${encodeURIComponent(t.slug)}`" class="icon-action icon-action--boxed" :aria-label="`La fiche de ${t.resolvedName ?? t.name}`">
                  <ArrowUpRight :size="16" :stroke-width="2" />
                </RouterLink>
              </div>
            </div>
            <div v-if="t.critique?.pros?.length || t.critique?.cons?.length" class="t__opinion">
              <ul v-if="t.critique.pros?.length"><li v-for="p in t.critique.pros" :key="p"><span class="mono sign">+</span>{{ p }}</li></ul>
              <ul v-if="t.critique.cons?.length"><li v-for="c in t.critique.cons" :key="c"><span class="mono sign sign--minus">−</span>{{ c }}</li></ul>
            </div>
          </article>
        </section>

        <section v-if="chapterRows.length" class="block" aria-labelledby="h-chapters">
          <div class="section-head">
            <h2 id="h-chapters">Chapitres</h2>
            <span class="lab">{{ chapterRows.length }}</span>
          </div>
          <ol class="tracks">
            <li v-for="ch in chapterRows" :key="ch.timestamp" class="track" :class="{ 'is-on': activeChapter?.timestamp === ch.timestamp }">
              <button type="button" class="track__btn" :disabled="!episode.audioUrl" @click="playChapter(ch)">
                <span class="mono track__ts">{{ ch.timestamp }}</span>
                <span class="track__title ellipsis">{{ ch.title }}</span>
                <Check v-if="ch.progress.done" :size="14" :stroke-width="3" class="track__done" aria-label="Écouté" />
                <span v-if="ch.progress.pct > PROGRESS_MIN_PCT && !ch.progress.done" class="track__bar"><span :style="{ width: ch.progress.pct + '%' }"></span></span>
              </button>
              <RouterLink v-if="ch.slug" :to="`/game/${encodeURIComponent(ch.slug)}`" class="icon-action" :aria-label="`La fiche de ${ch.resolvedName ?? ch.title}`">
                <ArrowUpRight :size="16" :stroke-width="2" />
              </RouterLink>
            </li>
          </ol>
        </section>

        <details v-if="episode.description" class="about">
          <summary class="lab">Description de l'émission</summary>
          <div class="about__body" v-html="episode.description" />
        </details>
      </div>
    </div>
  </div>
</template>

<style scoped>
.state { flex: 1; display: flex; align-items: center; justify-content: center; }
.state__title { font-size: var(--text-2xl); }
.state__text { color: var(--c-fg-2); }

.ep-scroll { position: relative; }
.backdrop { position: absolute; left: 0; right: 0; top: 0; height: 640px; overflow: hidden; pointer-events: none; }
.backdrop img { position: absolute; inset: -120px; width: calc(100% + 240px); height: calc(100% + 240px); object-fit: cover; filter: blur(60px) saturate(1.3); opacity: 0.45; }
.backdrop::after { content: ''; position: absolute; inset: 0; background: linear-gradient(180deg, rgba(0, 0, 0, 0.15) 0%, var(--game-veil) 55%, var(--c-bg) 100%); }
.ep { position: relative; max-width: 1040px; }
.ep__head { padding: 28px 0 40px; display: flex; flex-direction: column; align-items: flex-start; gap: 16px; }
.ep__show { display: flex; align-items: center; gap: 12px; }
.ep__art { width: 48px; height: 48px; object-fit: cover; }
.ep__title { margin: 0; font-size: clamp(28px, 5vw, 56px); line-height: 1.05; overflow-wrap: anywhere; }
.ep__main { min-width: 200px; }

/* The tests and the chapters: panels, like the game page's journal. */
.block { margin-bottom: 32px; background: var(--c-surface); box-shadow: inset 0 0 0 1px var(--c-line); }
.block .section-head { margin: 0; padding: 14px 20px; border-bottom: 1px solid var(--c-line); }
.block .section-head h2 { font-size: 13px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; }

.t { border-bottom: 1px solid var(--c-line); padding: 14px 20px; }
.t:last-child { border-bottom: 0; }
.t.is-playing { background: rgba(255, 255, 255, 0.04); box-shadow: inset 3px 0 0 var(--c-accent); }
.t__row { display: flex; align-items: center; gap: 14px; }
.t__cover { width: 72px; height: 96px; object-fit: cover; flex-shrink: 0; box-shadow: 0 0 0 1px var(--c-line), 0 10px 24px rgba(0, 0, 0, 0.5); }
.t__cover--none { background: var(--c-surface); box-shadow: inset 0 0 0 1px var(--c-line); }
.t__main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.t__name { font-size: 20px; line-height: 1.1; }
.t__meta { display: flex; align-items: center; gap: 16px; }
.t__start { color: var(--c-fg-2); }
.t__actions { display: flex; gap: 6px; }
.t__play { box-shadow: inset 0 0 0 1px var(--c-line-strong); }
.t__play.is-on { background: var(--c-accent); color: var(--c-accent-fg); box-shadow: none; }
.t__opinion { display: grid; grid-template-columns: minmax(0, 1fr); gap: 8px; padding: 12px 0 0 86px; }
@media (min-width: 768px) { .t__opinion { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 32px; } .t__name { font-size: 24px; } }
.t__opinion ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.t__opinion li { display: flex; gap: 10px; color: var(--c-fg-2); line-height: 1.45; }
.sign { color: var(--c-accent); font-weight: 700; }
.sign--minus { color: var(--c-fg); }

.tracks { list-style: none; margin: 0; padding: 0; }
.track { display: flex; align-items: center; border-bottom: 1px solid var(--c-line); }
.track:last-child { border-bottom: 0; }
.track.is-on { background: rgba(255, 255, 255, 0.04); box-shadow: inset 3px 0 0 var(--c-accent); }
.track__btn {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 16px;
  min-height: 48px;
  padding: 0 20px;
  border: 0;
  background: transparent;
  color: var(--c-fg);
  text-align: left;
  cursor: pointer;
}
.track__btn:hover:not(:disabled) { background: var(--c-raised); }
.track__ts { width: 72px; flex-shrink: 0; color: var(--c-fg-3); }
.track.is-on .track__ts { color: var(--c-accent); }
.track__title { flex: 1; min-width: 0; }
.track__done { color: var(--c-fg-2); flex-shrink: 0; }
.track__bar { width: 48px; height: 3px; background: var(--c-line-strong); flex-shrink: 0; }
.track__bar span { display: block; height: 100%; background: var(--c-accent); }

.about { box-shadow: inset 0 0 0 1px var(--c-line); padding: 0 16px; margin-bottom: 40px; }
.about summary { min-height: 44px; display: flex; align-items: center; cursor: pointer; }
.about__body { color: var(--c-fg-2); padding-bottom: 16px; max-width: 75ch; overflow-wrap: anywhere; }
.about__body :deep(a) { color: var(--c-fg); text-decoration: underline; text-underline-offset: 2px; }
.about__body :deep(p) { margin: 0 0 0.7rem; }
.about__body :deep(ul), .about__body :deep(ol) { padding-left: 1.25rem; margin-bottom: 0.7rem; }
.about__body :deep(ul) { list-style: disc; }
.about__body :deep(ol) { list-style: decimal; }
.about__body :deep(strong), .about__body :deep(b) { font-weight: 600; color: var(--c-fg); }
.about__body :deep(em), .about__body :deep(i) { font-style: italic; }
</style>
