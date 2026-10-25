<script setup>
import { ref, computed, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { formatTime, progressPct, testHref, episodeTrack } from '../lib/utils.js'
import { igdbUrl } from '../lib/igdbCdn.js'
import { usePlayerStore } from '../stores/player.js'
import { useGamesStore } from '../stores/games.js'
import TestCard from './TestCard.vue'
import { X } from 'lucide-vue-next'
import { testAt } from '../lib/timeline.js'

// The top of the Ludothèque (DECISIONS.md, « Interface »): the newest test in
// large (wide screens) and what was started. The podcasts and the games follow
// (« Les podcasts », then GameGrid), in the same scroll: the games, newest
// first, already show the new tests, so they have no row of their own. A search shows
// SearchResults instead: a test is found by its game or by its episode.

const router      = useRouter()
const gamesStore  = useGamesStore()
const playerStore = usePlayerStore()

const episodes = computed(() => gamesStore.episodes)
const error    = computed(() => gamesStore.episodesError)

// The newest test, shown large on a wide screen only: on a phone it would
// repeat the grid's first cover (DECISIONS.md, « Interface »).
const phoneQuery = typeof window !== 'undefined' && window.matchMedia ? window.matchMedia('(max-width: 767px)') : null
const isPhone = ref(phoneQuery?.matches ?? false)
const onPhoneChange = e => { isPhone.value = e.matches }
phoneQuery?.addEventListener('change', onPhoneChange)
onBeforeUnmount(() => phoneQuery?.removeEventListener('change', onPhoneChange))

const lead     = computed(() => gamesStore.newestTest)
const featured = computed(() => (isPhone.value ? null : lead.value))

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
// Each episode left partway, told by what it resumes on (DECISIONS.md,
// « Interface »): the test at the saved position (`testAt`), not the game the
// listening was started for — it goes on from test to test; outside a test, the
// episode with its image (its podcast's when it has none). × forgets it.
const bySlug = computed(() => new Map(episodes.value.map(ep => [ep.slug, ep])))

const resumeAll = computed(() => {
  // The listening in the mini player is not repeated here.
  const onAir = playerStore.current?.episodeSlug
  return playerStore.inProgress
    .filter(p => p.episodeSlug !== onAir)
    .map(p => {
      const ep = bySlug.value.get(p.episodeSlug)
      if (!ep) return null
      const test = testAt({ tests: ep.games ?? [], chapters: ep.chapters ?? [] }, p.currentTime)
      return {
        ep, test, entry: p,
        name:  test ? (test.resolvedName ?? test.name) : ep.title,
        image: test?.coverImageId ? igdbUrl(test.coverImageId, 't_cover_small') : (ep.imageUrl ?? ep.podcast?.imageUrl ?? null),
        pct:   progressPct(p.currentTime, p.ts ?? 0, p.chapterEnd),
      }
    })
    .filter(Boolean)
})
// The three most recent; « Tous · n » unfolds the others in place.
const RESUME_FIRST = 3
const resumeOpen   = ref(false)
const resumeItems  = computed(() => (resumeOpen.value ? resumeAll.value : resumeAll.value.slice(0, RESUME_FIRST)))

function resume({ ep, test, entry }) {
  playerStore.play(episodeTrack(ep, { test, ts: entry.currentTime }))
}
</script>

<template>
  <div class="home-top">
    <!-- The newest game's light over the top of the page (its colours: App.vue) -->
    <div class="halo" aria-hidden="true"></div>
    <div class="content feed">
      <div v-if="error" class="empty">
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

          <section v-if="resumeItems.length" class="resume section" aria-labelledby="h-resume">
            <div class="section-head">
              <h2 id="h-resume">Reprendre</h2>
              <button v-if="resumeAll.length > RESUME_FIRST" type="button" class="lab section-more" :aria-expanded="resumeOpen" @click="resumeOpen = !resumeOpen">
                {{ resumeOpen ? 'Moins' : `Tous · ${resumeAll.length}` }}
              </button>
            </div>
            <div v-for="item in resumeItems" :key="item.ep.slug" class="resume__row line" data-test="resume">
              <button type="button" class="resume__main" :aria-label="`Reprendre ${item.name}`" @click="resume(item)">
                <span class="resume__cover corners" :class="{ 'resume__cover--none': !item.image, 'resume__cover--ep': !item.test }">
                  <img v-if="item.image" :src="item.image" alt="" />
                </span>
                <span class="resume__text">
                  <span class="resume__name ellipsis">{{ item.name }}</span>
                  <span class="resume__meta ellipsis">{{ item.ep.podcast?.name }} · {{ formatTime(item.entry.currentTime) }}</span>
                  <span class="resume__bar"><span :style="{ width: item.pct + '%' }"></span></span>
                </span>
              </button>
              <button type="button" class="icon-action resume__forget" :aria-label="`Oublier l’écoute de ${item.name}`" title="Oublier cette écoute" @click="playerStore.forgetEpisode(item.ep.slug)">
                <X :size="16" :stroke-width="2" />
              </button>
            </div>
          </section>
        </div>

      </template>
    </div>
  </div>
</template>

<style scoped>
.feed { padding-top: 16px; }

.top { position: relative; display: grid; grid-template-columns: minmax(0, 1fr); gap: 28px; margin-bottom: 44px; }
.top .section { margin-bottom: 0; }
@media (min-width: 1200px) {
  .top.has-resume { grid-template-columns: minmax(0, 1fr) 380px; align-items: end; gap: 40px; }
}

.resume { position: relative; z-index: 1; }
/* The rows lie on the page, a rule between them, like a podcast's episodes. */
.resume__row {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 10px 0;
  color: var(--c-fg);
}
.resume__main {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.resume__main:hover .resume__name { text-decoration: underline; text-underline-offset: 3px; }
.resume__forget { color: var(--c-fg-2); }
.resume__cover { --corner: 9px; --corner-out: 4px; width: 36px; height: 48px; flex-shrink: 0; }
.resume__cover img { display: block; width: 100%; height: 100%; object-fit: cover; }
.resume__cover--none { background: var(--c-raised); }
.resume__cover--ep { height: 36px; margin: 6px 0; }
.resume__text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.resume__name { font-weight: 600; font-size: 15px; }
.resume__meta { color: var(--c-fg-2); font-size: 12px; }
.resume__bar { display: block; height: 3px; margin-top: 5px; background: var(--c-line-strong); }
.resume__bar span { display: block; height: 100%; background: var(--c-accent); }

.empty { padding: 64px 0; text-align: center; }
.empty__title { font-size: var(--text-2xl); margin: 0 0 8px; }
.empty__text { color: var(--c-fg-2); margin: 0; }
@media (max-width: 767px) {
  .feed { padding-top: 12px; }
}
</style>
