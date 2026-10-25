<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { usePlayerStore } from '../stores/player.js'
import { useGamesStore } from '../stores/games.js'
import { fetchEpisodeDetail } from '../lib/games.js'
import { episodeTrack, formatShortDate, formatTime, testHref, PROGRESS_MIN_PCT } from '../lib/utils.js'
import { episodeTimeline } from '../lib/timeline.js'
import { igdbUrl } from '../lib/igdbCdn.js'
import { podcastMeta } from '../lib/podcasts.js'
import BackBar from './BackBar.vue'
import { useProgress } from '../composables/useProgress.js'
import { useGameTheme, paletteFromAccent, themeStyle } from '../composables/useGameTheme.js'
import { Play, Pause, Check, ArrowUpRight } from 'lucide-vue-next'

// An episode's page — where the two ways in meet (DECISIONS.md, « Interface » :
// une seule écoute): from a game's page (`?game=`), its test first; from its
// podcast, the episode from its start or where it was left. Below, one list of
// moments, all alike: the chapters in order, the tests among them, each once,
// told by their cover. A test's verdict and opinions are on its game's page,
// one tap away — not repeated here.
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
  if (leadTest.value) return `Écouter le test${leadTest.value.timestamp != null ? ' · ' + formatTime(leadTest.value.timestampSeconds) : ''}`
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

// ── The moments: one shape for a chapter and a test ─────────────────────────
// A test's row plays from its start (or where it was left) and leads to its
// game's page, its test open; a test with no known start only leads there.
const rows = computed(() => {
  const ep = episode.value
  if (!ep) return []
  const testOn = timeline.value.find(r => r.kind === 'test' && isActive(r.test))
  return timeline.value.map(r => {
    if (r.kind === 'test') {
      const t    = r.test
      const name = t.resolvedName ?? t.name
      const href = t.slug ? testHref({ ep, test: t }) : null
      return {
        key:      `t|${name}|${t.timestampSeconds}`,
        ts:       t.timestamp != null ? formatTime(t.timestampSeconds) : '',
        title:    name,
        isTest:   true,
        cover:    t.coverImageId ?? null,
        href,
        on:       isActive(t),
        lead:     leadTest.value === t,
        progress: r.chapter ? episodeProgress(ep.slug, r.chapter.timestampSeconds ?? 0) : null,
        play:     t.timestamp != null ? () => playTest(t) : href ? () => router.push(href) : null,
        label:    t.timestamp != null ? `Écouter le test de ${name}` : `La fiche de ${name}`,
      }
    }
    const ch = r.chapter
    return {
      key:      `c|${ch.timestamp}`,
      ts:       formatTime(ch.timestampSeconds ?? 0),
      title:    ch.title,
      isTest:   false,
      on:       activeChapter.value?.timestamp === ch.timestamp && testOn?.chapter !== ch,
      progress: episodeProgress(ep.slug, ch.timestampSeconds ?? 0),
      play:     () => playChapter(ch),
      label:    `Écouter depuis ${formatTime(ch.timestampSeconds ?? 0)} : ${ch.title}`,
    }
  })
})
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

        <section v-if="rows.length" class="block" aria-labelledby="h-programme">
          <div class="section-head">
            <h2 id="h-programme">Au programme</h2>
          </div>
          <ol class="tl">
            <li v-for="row in rows" :key="row.key" class="mo" :class="{ 'is-on': row.on, 'is-lead': row.lead }">
              <button type="button" class="mo__btn" :title="row.title" :aria-label="row.label" :disabled="!row.play" @click="row.play?.()">
                <span class="mono mo__ts">{{ row.ts }}</span>
                <img v-if="row.cover" :src="igdbUrl(row.cover, 't_cover_small')" alt="" class="mo__cover" loading="lazy" />
                <span v-else class="mo__cover" :class="{ 'mo__cover--none': row.isTest }"></span>
                <span class="mo__title clamp-2" :class="{ 'mo__title--test': row.isTest }">{{ row.title }}</span>
                <span class="mo__state">
                  <Check v-if="row.progress?.done" :size="14" :stroke-width="3" class="mo__done" aria-label="Écouté" />
                  <span v-else-if="row.progress?.pct > PROGRESS_MIN_PCT" class="mo__bar"><span :style="{ width: row.progress.pct + '%' }"></span></span>
                </span>
              </button>
              <RouterLink v-if="row.href" :to="row.href" class="icon-action mo__go" :aria-label="`La fiche de ${row.title}`">
                <ArrowUpRight :size="16" :stroke-width="2" />
              </RouterLink>
              <span v-else class="mo__go" aria-hidden="true"></span>
            </li>
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

/* The moments: one panel, every row alike — time, a cover column (a test's
   cover, else empty, so the titles line up), the title on two lines at most,
   its state, and the way to a test's game. The time and the state sit on the
   title's first line. */
.block { margin-bottom: 32px; background: var(--c-surface); box-shadow: inset 0 0 0 1px var(--c-line); }
.block .section-head { margin: 0; padding: 14px 20px; border-bottom: 1px solid var(--c-line); }
.block .section-head h2 { font-size: 13px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; }
.tl { list-style: none; margin: 0; padding: 0; }

.mo { display: flex; align-items: flex-start; border-bottom: 1px solid var(--c-line); }
.mo:last-child { border-bottom: 0; }
.mo.is-lead { background: rgba(255, 255, 255, 0.03); }
.mo.is-on { background: rgba(255, 255, 255, 0.05); box-shadow: inset 3px 0 0 var(--c-accent); }
.mo__btn {
  flex: 1;
  min-width: 0;
  display: grid;
  grid-template-columns: 64px 28px minmax(0, 1fr) 48px;
  align-items: start;
  column-gap: 14px;
  min-height: 52px;
  padding: 8px 0 8px 20px;
  border: 0;
  background: transparent;
  color: var(--c-fg-2);
  text-align: left;
  cursor: pointer;
}
.mo__btn:hover:not(:disabled) { background: var(--c-raised); color: var(--c-fg); }
.mo__btn:disabled { cursor: default; }
.mo__ts { padding-top: 9px; color: var(--c-fg-3); }
.mo.is-on .mo__ts { color: var(--c-accent); }
.mo__cover { width: 28px; height: 37px; object-fit: cover; }
img.mo__cover { box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.16); }
.mo__cover--none { background: var(--c-raised); }
.mo__title { padding-top: 8px; line-height: 1.35; }
.mo__title--test { color: var(--c-fg); font-family: var(--font-display); font-weight: 600; }
.mo.is-on .mo__title { color: var(--c-fg); }
.mo__state { padding-top: 11px; display: flex; justify-content: flex-end; }
.mo__done { color: var(--c-fg-2); }
.mo__bar { width: 40px; height: 3px; margin-top: 6px; background: var(--c-line-strong); }
.mo__bar span { display: block; height: 100%; background: var(--c-accent); }
.mo__go { flex-shrink: 0; width: 52px; height: 52px; display: inline-flex; align-items: center; justify-content: center; }

/* Phone: a narrower time column; the title takes what is left. */
@media (max-width: 599px) {
  .mo__btn { grid-template-columns: 52px 28px minmax(0, 1fr) 24px; column-gap: 10px; padding-left: 12px; }
  .mo__ts { font-size: 12px; }
  .mo__go { width: 44px; }
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
