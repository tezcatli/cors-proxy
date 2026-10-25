<script setup>
import { ref, computed, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { formatTime, progressPct, testHref, episodeTrack } from '../lib/utils.js'
import { igdbUrl } from '../lib/igdbCdn.js'
import { usePlayerStore } from '../stores/player.js'
import { useGamesStore } from '../stores/games.js'
import TestCard from './TestCard.vue'
import { Play } from 'lucide-vue-next'

// The top of the Ludothèque (DECISIONS.md, « Interface »): the newest test in
// large (wide screens), what was started, then the newest tests in a row to
// swipe, one card each — a game an episode tests, told by its cover. The games
// follow (« Les podcasts », then GameGrid), in the same scroll. A search shows
// SearchResults instead: a test is found by its game or by its episode.

const router      = useRouter()
const gamesStore  = useGamesStore()
const playerStore = usePlayerStore()

const episodes = computed(() => gamesStore.episodes)
const loading  = computed(() => gamesStore.episodesLoading)
const error    = computed(() => gamesStore.episodesError)

// One card per test; an episode that tests nothing has no card.
const tests = computed(() => episodes.value.flatMap(ep => (ep.games ?? []).map(test => ({ ep, test }))))

// The newest test leads. It is shown large on a wide screen only: on a phone it would
// repeat the grid's first card (DECISIONS.md, « Interface »).
const phoneQuery = typeof window !== 'undefined' && window.matchMedia ? window.matchMedia('(max-width: 767px)') : null
const isPhone = ref(phoneQuery?.matches ?? false)
const onPhoneChange = e => { isPhone.value = e.matches }
phoneQuery?.addEventListener('change', onPhoneChange)
onBeforeUnmount(() => phoneQuery?.removeEventListener('change', onPhoneChange))

const lead     = computed(() => tests.value[0] ?? null)
const featured = computed(() => (isPhone.value ? null : lead.value))
const rest     = computed(() => (featured.value ? tests.value.slice(1) : tests.value))

// The row: the newest tests; the rest of the history is reached by its games.
const ROW_MAX = 30
const rowTests = computed(() => rest.value.slice(0, ROW_MAX))

function isPlaying({ ep, test }) {
  const cur = playerStore.current
  return !!cur && cur.url === ep.audioUrl && cur.slug === (test.slug ?? null)
}

function play({ ep, test }) {
  // Resume from saved progress when partway through; untouched/finished starts at the test.
  playerStore.play(episodeTrack(ep, { test, ts: playerStore.resumeTimeFor(ep.slug, test.timestampSeconds || 0) }))
}

function view(item) {
  router.push(testHref(item))
}

// ── Reprendre ────────────────────────────────────────────────────────────────
const bySlug = computed(() => new Map(episodes.value.map(ep => [ep.slug, ep])))

const resumeItems = computed(() => {
  // The listening in the mini player is not repeated here.
  const onAir = playerStore.current?.episodeSlug
  return playerStore.inProgress
    .filter(p => p.episodeSlug !== onAir)
    .map(p => {
      const ep = bySlug.value.get(p.episodeSlug)
      if (!ep) return null
      const test = ep.games?.find(g => g.slug && g.slug === p.gameSlug) ?? ep.games?.[0] ?? null
      return {
        ep, test, entry: p,
        name:  test ? (test.resolvedName ?? test.name) : ep.title,
        cover: test?.coverImageId ?? null,
        pct:   progressPct(p.currentTime, p.ts ?? 0, p.chapterEnd),
      }
    })
    .filter(Boolean)
    .slice(0, 3)
})

function resume({ ep, test, entry }) {
  playerStore.play(episodeTrack(ep, { test, ts: entry.currentTime }))
}
</script>

<template>
  <div class="home-top">
    <!-- The newest test's cover, blurred, behind the top of the page -->
    <div v-if="lead?.test.coverImageId" class="backdrop" aria-hidden="true">
      <img :src="igdbUrl(lead.test.coverImageId, 't_cover_small')" alt="" />
    </div>
    <div class="content feed">
      <div v-if="loading" aria-hidden="true" class="row">
        <div v-for="i in 8" :key="i" class="skeleton-shimmer skel" />
      </div>

      <div v-else-if="error" class="empty">
        <p class="cond empty__title">Hors antenne</p>
        <p class="empty__text">{{ error }}</p>
      </div>

      <template v-else>
        <div v-if="featured || resumeItems.length" class="top" :class="{ 'has-resume': resumeItems.length }">
          <TestCard
            v-if="featured"
            :item="featured"
            featured
            :is-playing="isPlaying(featured)"
            :is-paused="playerStore.paused"
            @play="play"
            @toggle-pause="playerStore.togglePlayback()"
            @view="view"
          />

          <section v-if="resumeItems.length" class="resume" aria-labelledby="h-resume">
            <h2 id="h-resume" class="lab resume__title"><span class="onair" aria-hidden="true"></span> Reprendre</h2>
            <div class="resume__list">
            <button v-for="item in resumeItems" :key="item.ep.slug" type="button" class="resume__row" @click="resume(item)">
              <img v-if="item.cover" :src="igdbUrl(item.cover, 't_cover_small')" alt="" class="resume__cover" />
              <span v-else class="resume__cover resume__cover--none"></span>
              <span class="resume__text">
                <span class="resume__name ellipsis">{{ item.name }}</span>
                <span class="resume__meta ellipsis">{{ item.ep.podcast?.name }} · {{ formatTime(item.entry.currentTime) }}</span>
                <span class="resume__bar"><span :style="{ width: item.pct + '%' }"></span></span>
              </span>
              <span class="resume__go" aria-hidden="true"><Play :size="14" fill="currentColor" :stroke-width="0" /></span>
            </button>
            </div>
          </section>
        </div>

        <section aria-labelledby="h-latest" class="latest">
          <div class="section-head">
            <h2 id="h-latest">Nouveaux tests</h2>
          </div>
          <div v-if="rowTests.length" class="row">
            <TestCard
              v-for="item in rowTests"
              :key="item.ep.slug + '|' + (item.test.slug ?? item.test.name)"
              :item="item"
              :is-playing="isPlaying(item)"
              :is-paused="playerStore.paused"
              @play="play"
              @toggle-pause="playerStore.togglePlayback()"
              @view="view"
            />
          </div>
          <p v-else class="empty__text">Aucun test.</p>
        </section>
      </template>
    </div>
  </div>
</template>

<style scoped>

.backdrop { position: absolute; left: 0; right: 0; top: 0; height: 720px; overflow: hidden; pointer-events: none; }
.backdrop img { position: absolute; inset: -120px; width: calc(100% + 240px); height: calc(100% + 240px); object-fit: cover; filter: blur(70px) saturate(1.3); opacity: 0.45; }
.backdrop::after { content: ''; position: absolute; inset: 0; background: linear-gradient(180deg, rgba(9, 9, 12, 0.2) 0%, var(--c-bg) 100%); }
.feed { padding-top: 16px; position: relative; }

.top { position: relative; display: grid; grid-template-columns: minmax(0, 1fr); gap: 28px; margin-bottom: 40px; }
@media (min-width: 1200px) {
  .top.has-resume { grid-template-columns: minmax(0, 1fr) 380px; align-items: end; gap: 40px; }
}

.resume {
  position: relative;
  z-index: 1;
  background: var(--c-surface);
  box-shadow: inset 0 0 0 1px var(--c-line-strong);
}
.resume__title { display: flex; align-items: center; gap: 10px; margin: 0; padding: 12px 16px; border-bottom: 1px solid var(--c-line); color: var(--c-fg); }
.resume__row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px 16px;
  border: 0;
  border-bottom: 1px solid var(--c-line);
  background: transparent;
  color: var(--c-fg);
  text-align: left;
  cursor: pointer;
}
.resume__row:last-child { border-bottom: 0; }
/* Phone: a row to swipe, so the tests stay on the first screen. */
@media (max-width: 767px) {
  .resume { background: transparent; box-shadow: none; }
  .resume__title { padding: 0 0 10px; border-bottom: 0; }
  .resume__list { display: flex; gap: 10px; overflow-x: auto; scroll-snap-type: x mandatory; scrollbar-width: none; margin: 0 calc(var(--gutter) * -1); padding: 0 var(--gutter) 4px; }
  .resume__list::-webkit-scrollbar { display: none; }
  .resume__row { flex: 0 0 78%; scroll-snap-align: start; border-bottom: 0; background: var(--c-surface); box-shadow: inset 0 0 0 1px var(--c-line-strong); }
  .resume__row:last-child { border-bottom: 0; }
}
.resume__row:hover { background: var(--c-raised); }
.resume__cover { width: 36px; height: 48px; object-fit: cover; flex-shrink: 0; }
.resume__cover--none { background: var(--c-raised); }
.resume__text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.resume__name { font-weight: 600; font-size: 14px; }
.resume__meta { color: var(--c-fg-2); font-size: 12px; }
.resume__bar { display: block; height: 4px; margin-top: 4px; background: var(--c-line-strong); }
.resume__bar span { display: block; height: 100%; background: var(--c-accent); }
.resume__go {
  width: 40px;
  height: 40px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--c-accent);
  color: var(--c-accent-fg);
}

/* The newest tests: a row to swipe, the next card peeking at the edge. */
.latest { margin-bottom: 36px; }
.row {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: 40%;
  gap: 14px;
  overflow-x: auto;
  scroll-snap-type: x proximity;
  scrollbar-width: none;
  margin: 0 calc(var(--gutter) * -1);
  padding: 4px var(--gutter) 8px;
  scroll-padding: 0 var(--gutter);
}
.row::-webkit-scrollbar { display: none; }
.row > * { scroll-snap-align: start; }
@media (min-width: 600px) { .row { grid-auto-columns: 26%; } }
@media (min-width: 900px) { .row { grid-auto-columns: 180px; gap: 24px; } }
.skel { aspect-ratio: 3 / 4; }

.empty { padding: 64px 0; text-align: center; }
.empty__title { font-size: var(--text-2xl); margin: 0 0 8px; }
.empty__text { color: var(--c-fg-2); margin: 0; }
/* Phone: compact, so the tests start on the first screen — the whole card
   resumes, the cover is small, less air. */
@media (max-width: 767px) {
  .feed { padding-top: 12px; }
  .top { margin-bottom: 20px; }
  .resume__row { flex-basis: 64%; padding: 8px 10px; gap: 10px; }
  .resume__cover { width: 32px; height: 43px; }
  .resume__go { display: none; }
}
</style>
