<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { usePlayerStore } from '../stores/player.js'
import { useGamesStore } from '../stores/games.js'
import { fetchEpisodeDetail } from '../lib/games.js'
import { episodeTrack, formatShortDate, formatTime, PROGRESS_MIN_PCT } from '../lib/utils.js'
import { episodeTimeline } from '../lib/timeline.js'
import { igdbUrl } from '../lib/igdbCdn.js'
import { podcastMeta } from '../lib/podcasts.js'
import BackBar from './BackBar.vue'
import VerdictMark from './VerdictMark.vue'
import { useProgress } from '../composables/useProgress.js'
import { useGameTheme, paletteFromAccent, themeStyle } from '../composables/useGameTheme.js'
import { Play, Pause, Check, ArrowUpRight } from 'lucide-vue-next'

// An episode's page — where the two ways in meet (DECISIONS.md, « Interface » :
// une seule écoute): from a game's page (`?game=`), its test first; from its
// podcast, the episode from its start or where it was left. Below, one
// timeline: the chapters in order, the tests among them, each once.
const route       = useRoute()
const router      = useRouter()
const playerStore = usePlayerStore()
const gamesStore  = useGamesStore()

const { episodeProgress } = useProgress()

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

const backLabel = computed(() =>
  fromGame ? (gamesStore.all.find(g => g.slug === fromGame)?.name ?? 'Retour') : 'Retour')

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

const tests    = computed(() => episode.value?.games ?? [])
const podcast  = computed(() => episode.value?.podcast ?? null)
const timeline = computed(() => episodeTimeline(episode.value?.chapters ?? [], tests.value))

// The test we came for, from a game's page.
const leadTest = computed(() => (fromGame ? tests.value.find(t => t.slug === fromGame) ?? null : null))

// Its game's colours when we came for a test; else the podcast's.
const { style: gameTheme } = useGameTheme(() => leadTest.value?.coverImageId ?? null)
const theme = computed(() => (leadTest.value ? gameTheme.value : themeStyle(paletteFromAccent(podcastMeta(podcast.value?.id)?.accent))))
const backdrop = computed(() => (leadTest.value?.coverImageId
  ? igdbUrl(leadTest.value.coverImageId, 't_cover_small')
  : podcast.value?.imageUrl ?? null))

const isThisTrack = computed(() =>
  !!playerStore.current && playerStore.current.url === episode.value?.audioUrl)
const activeChapter = computed(() => isThisTrack.value ? playerStore.currentChapter : null)
const activeTest    = computed(() => isThisTrack.value ? playerStore.currentTest : null)
const isActive = t => !!activeTest.value && activeTest.value.slug === t.slug && activeTest.value.timestampSeconds === t.timestampSeconds

function playFrom(ts, test = null) {
  const ep = episode.value
  if (!ep?.audioUrl) return
  playerStore.play(episodeTrack(ep, { test, ts }))
}

function playTest(t) {
  if (isActive(t)) playerStore.togglePlayback()
  // Resume from saved progress when partway through; untouched/finished starts at the test.
  else playFrom(playerStore.resumeTimeFor(episode.value.slug, t.timestampSeconds ?? 0), t)
}

function playChapter(ch) {
  playFrom(ch.timestampSeconds, tests.value.find(x => x.slug && x.slug === ch.slug) ?? null)
}

// ── The main button: our test, else where the episode was left, else its start
const resumeEntry = computed(() => (isThisTrack.value ? null : playerStore.resumeEntryFor(episode.value?.slug)))

const mainLabel = computed(() => {
  if (isThisTrack.value) return playerStore.paused ? 'Reprendre' : 'Pause'
  if (leadTest.value) return `Écouter le test${leadTest.value.timestamp ? ' · ' + leadTest.value.timestamp : ''}`
  if (resumeEntry.value) return `Reprendre à ${formatTime(resumeEntry.value.currentTime)}`
  return "Écouter l'épisode"
})
// From a game's page, the whole episode is one tap away.
const showFromStart = computed(() => !isThisTrack.value && !!leadTest.value)

function onMain() {
  if (isThisTrack.value) { playerStore.togglePlayback(); return }
  if (leadTest.value) { playTest(leadTest.value); return }
  playFrom(resumeEntry.value?.currentTime ?? 0)
}

const progressOf = ch => (ch ? episodeProgress(episode.value.slug, ch.timestampSeconds ?? 0) : null)
</script>

<template>
  <div class="overlay-page" :style="[theme, { zIndex: 'var(--z-episode)' }]">
    <BackBar :label="backLabel" @back="back" />

    <div v-if="loading || error || !episode" class="state">
      <span v-if="loading" class="lab">Chargement…</span>
      <p v-else-if="error" class="state__text">Erreur : {{ error }}</p>
      <p v-else class="cond state__title">Épisode introuvable</p>
    </div>

    <div v-else class="scroll-area ep-scroll">
      <div v-if="backdrop" class="backdrop" aria-hidden="true"><img :src="backdrop" alt="" /></div>
      <div class="content ep">
        <header class="ep__head">
          <RouterLink v-if="podcast" :to="`/podcast/${podcast.id}`" class="ep__show">
            <img v-if="podcast.imageUrl" :src="podcast.imageUrl" alt="" class="ep__art" />
            <span class="lab">{{ podcast.name }} · {{ formatShortDate(episode.pubTs) }}</span>
          </RouterLink>
          <h1 class="ep__title cond">{{ episode.title }}</h1>
          <div v-if="episode.audioUrl" class="ep__actions">
            <button type="button" class="btn-play ep__main" @click="onMain">
              <Pause v-if="isThisTrack && !playerStore.paused" :size="14" fill="currentColor" :stroke-width="0" />
              <Play v-else :size="14" fill="currentColor" :stroke-width="0" />
              {{ mainLabel }}
            </button>
            <button v-if="showFromStart" type="button" class="btn-line" @click="playFrom(0)">Depuis le début</button>
          </div>
        </header>

        <section v-if="timeline.length" class="block" aria-labelledby="h-programme">
          <div class="section-head">
            <h2 id="h-programme">Au programme</h2>
            <span v-if="tests.length" class="lab">{{ tests.length }} test{{ tests.length > 1 ? 's' : '' }}</span>
          </div>
          <ol class="tl">
            <template v-for="row in timeline" :key="row.kind + (row.kind === 'test' ? row.test.name + row.test.timestampSeconds : row.chapter.timestamp)">
              <li v-if="row.kind === 'test'" class="t" :class="{ 'is-playing': isActive(row.test), 'is-lead': leadTest === row.test }">
                <div class="t__row">
                  <span class="mono t__ts">{{ row.test.timestamp ?? '—' }}</span>
                  <img v-if="row.test.coverImageId" :src="igdbUrl(row.test.coverImageId, 't_cover_big')" alt="" class="t__cover" />
                  <span v-else class="t__cover t__cover--none"></span>
                  <div class="t__main">
                    <RouterLink v-if="row.test.slug" :to="`/game/${encodeURIComponent(row.test.slug)}`" class="t__name cond clamp-2">{{ row.test.resolvedName ?? row.test.name }}</RouterLink>
                    <span v-else class="t__name cond clamp-2">{{ row.test.resolvedName ?? row.test.name }}</span>
                    <span class="t__meta">
                      <VerdictMark :verdict="row.test.critique?.verdict ?? null" />
                      <Check v-if="progressOf(row.chapter)?.done" :size="14" :stroke-width="3" class="track__done" aria-label="Écouté" />
                    </span>
                  </div>
                  <div class="t__actions">
                    <button
                      type="button"
                      class="icon-action t__play"
                      :class="{ 'is-on': isActive(row.test) }"
                      :aria-label="`Écouter le test de ${row.test.resolvedName ?? row.test.name}`"
                      @click="playTest(row.test)"
                    >
                      <Pause v-if="isActive(row.test) && !playerStore.paused" :size="16" fill="currentColor" :stroke-width="0" />
                      <Play v-else :size="16" fill="currentColor" :stroke-width="0" />
                    </button>
                    <RouterLink v-if="row.test.slug" :to="`/game/${encodeURIComponent(row.test.slug)}`" class="icon-action icon-action--boxed" :aria-label="`La fiche de ${row.test.resolvedName ?? row.test.name}`">
                      <ArrowUpRight :size="16" :stroke-width="2" />
                    </RouterLink>
                  </div>
                </div>
                <details v-if="row.test.critique?.pros?.length || row.test.critique?.cons?.length" class="t__opinion" :open="leadTest === row.test">
                  <summary class="lab">Pour et contre</summary>
                  <div class="t__lists">
                    <ul v-if="row.test.critique.pros?.length"><li v-for="p in row.test.critique.pros" :key="p"><span class="mono sign">+</span>{{ p }}</li></ul>
                    <ul v-if="row.test.critique.cons?.length"><li v-for="c in row.test.critique.cons" :key="c"><span class="mono sign sign--minus">−</span>{{ c }}</li></ul>
                  </div>
                </details>
              </li>
              <li v-else class="track" :class="{ 'is-on': activeChapter?.timestamp === row.chapter.timestamp }">
                <button type="button" class="track__btn" @click="playChapter(row.chapter)">
                  <span class="mono track__ts">{{ row.chapter.timestamp }}</span>
                  <span class="track__title ellipsis">{{ row.chapter.title }}</span>
                  <Check v-if="progressOf(row.chapter).done" :size="14" :stroke-width="3" class="track__done" aria-label="Écouté" />
                  <span v-else-if="progressOf(row.chapter).pct > PROGRESS_MIN_PCT" class="track__bar"><span :style="{ width: progressOf(row.chapter).pct + '%' }"></span></span>
                </button>
              </li>
            </template>
          </ol>
        </section>

        <details v-if="episode.description" class="about">
          <summary class="lab">Description de l'épisode</summary>
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
.ep__show { display: flex; align-items: center; gap: 12px; min-height: 44px; text-decoration: none; }
.ep__show .lab { color: var(--c-accent); }
.ep__show:hover .lab { text-decoration: underline; text-underline-offset: 3px; }
.ep__art { width: 48px; height: 48px; object-fit: cover; }
.ep__title { margin: 0; font-size: clamp(26px, 5vw, 56px); line-height: 1.05; overflow-wrap: anywhere; }
.ep__actions { display: flex; flex-wrap: wrap; gap: 8px; }
.ep__main { min-width: 200px; }

/* The timeline: one panel, like the game page's journal. */
.block { margin-bottom: 32px; background: var(--c-surface); box-shadow: inset 0 0 0 1px var(--c-line); }
.block .section-head { margin: 0; padding: 14px 20px; border-bottom: 1px solid var(--c-line); }
.block .section-head h2 { font-size: 13px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; }
.tl { list-style: none; margin: 0; padding: 0; }

.t { border-bottom: 1px solid var(--c-line); padding: 12px 20px; background: rgba(255, 255, 255, 0.025); }
.t:last-child { border-bottom: 0; }
.t.is-lead { box-shadow: inset 0 0 0 1px var(--c-accent); }
.t.is-playing { background: rgba(255, 255, 255, 0.05); box-shadow: inset 3px 0 0 var(--c-accent); }
.t__row { display: flex; align-items: center; gap: 14px; }
.t__ts { width: 64px; flex-shrink: 0; color: var(--c-accent); }
.t__cover { width: 54px; height: 72px; object-fit: cover; flex-shrink: 0; box-shadow: 0 0 0 1px var(--c-line), 0 10px 24px rgba(0, 0, 0, 0.5); }
.t__cover--none { background: var(--c-raised); box-shadow: inset 0 0 0 1px var(--c-line); }
.t__main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.t__name { font-size: 18px; line-height: 1.15; color: var(--c-fg); text-decoration: none; }
a.t__name:hover { color: var(--c-accent); }
.t__meta { display: flex; align-items: center; gap: 12px; }
.t__actions { display: flex; gap: 6px; }
.t__play { box-shadow: inset 0 0 0 1px var(--c-line-strong); }
.t__play.is-on { background: var(--c-accent); color: var(--c-accent-fg); box-shadow: none; }
.t__opinion { padding: 8px 0 0 78px; }
.t__opinion summary { min-height: 36px; display: flex; align-items: center; cursor: pointer; }
.t__lists { display: grid; grid-template-columns: minmax(0, 1fr); gap: 8px; padding-bottom: 4px; }
@media (min-width: 768px) {
  .t__lists { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 32px; }
  .t__name { font-size: 22px; }
  .t__opinion { padding-left: 146px; }
}
.t__opinion ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.t__opinion li { display: flex; gap: 10px; color: var(--c-fg-2); line-height: 1.45; }
.sign { color: var(--c-accent); font-weight: 700; }
.sign--minus { color: var(--c-fg); }

.track { display: flex; align-items: center; border-bottom: 1px solid var(--c-line); }
.track:last-child { border-bottom: 0; }
.track.is-on { background: rgba(255, 255, 255, 0.04); box-shadow: inset 3px 0 0 var(--c-accent); }
.track__btn {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 14px;
  min-height: 48px;
  padding: 0 20px;
  border: 0;
  background: transparent;
  color: var(--c-fg-2);
  text-align: left;
  cursor: pointer;
}
.track__btn:hover { background: var(--c-raised); color: var(--c-fg); }
.track__ts { width: 64px; flex-shrink: 0; color: var(--c-fg-3); }
.track.is-on .track__ts { color: var(--c-accent); }
.track__title { flex: 1; min-width: 0; }
.track__done { color: var(--c-fg-2); flex-shrink: 0; }
.track__bar { width: 48px; height: 3px; background: var(--c-line-strong); flex-shrink: 0; }
.track__bar span { display: block; height: 100%; background: var(--c-accent); }

/* Phone: the time above nothing — a narrower column. */
@media (max-width: 599px) {
  .t, .track__btn { padding-left: 12px; padding-right: 12px; }
  .t__ts, .track__ts { width: 52px; font-size: 12px; }
  .t__cover { width: 40px; height: 53px; }
  .t__name { font-size: 15px; }
  .t__opinion { padding-left: 0; }
  .t__actions .icon-action--boxed { display: none; }   /* the name leads to the game's page */
}

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
