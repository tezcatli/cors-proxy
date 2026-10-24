<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { fetchEpisodes } from '../lib/games.js'
import { formatTime, progressPct, testHref } from '../lib/utils.js'
import { igdbUrl } from '../lib/igdbCdn.js'
import { useInfiniteScroll } from '../composables/useInfiniteScroll.js'
import { usePlayerStore } from '../stores/player.js'
import { useGamesStore } from '../stores/games.js'
import { podcastMeta } from '../lib/podcasts.js'
import TestCard from './TestCard.vue'
import { Play } from 'lucide-vue-next'

// The home (« Tests »): the newest test in large, what was started, then every
// test newest first, one card each — a game an episode tests, told by its cover.
// Shares `selectedPodcast` with the catalog: one choice of show, applied wherever
// the user is.
const props = defineProps({
  searchQuery:   String,
  refreshSignal: { type: Number, default: 0 },
})

const router      = useRouter()
const gamesStore  = useGamesStore()
const playerStore = usePlayerStore()

const episodes = ref([])
const loading  = ref(true)
const error    = ref(null)

async function load() {
  try { episodes.value = await fetchEpisodes(); error.value = null }
  catch (e) { error.value = e.message }
  finally   { loading.value = false }
}

onMounted(load)
// Reload when the pull-to-refresh signal bumps (keeps the existing list visible).
watch(() => props.refreshSignal, (v, prev) => { if (v !== prev) load() })

const filteredEpisodes = computed(() => {
  const q       = props.searchQuery?.trim().toLowerCase()
  const podcast = gamesStore.selectedPodcast
  let list = episodes.value
  if (podcast !== 'all')
    list = list.filter(ep => ep.podcast?.id === podcast)
  if (q)
    list = list.filter(ep =>
      ep.title.toLowerCase().includes(q) ||
      ep.games?.some(g => (g.resolvedName ?? g.name).toLowerCase().includes(q) || g.name.toLowerCase().includes(q))
    )
  return list
})

// One card per test; an episode that tests nothing has no card.
const tests = computed(() => filteredEpisodes.value.flatMap(ep => (ep.games ?? []).map(test => ({ ep, test }))))
// The newest test leads, unless the list is a search's results.
const featured = computed(() => (props.searchQuery?.trim() ? null : tests.value[0] ?? null))
const rest     = computed(() => (featured.value ? tests.value.slice(1) : tests.value))

// The show the list is narrowed to, said in the heading (the choice is kept
// across visits, so it must not go unnoticed).
const showName = computed(() => (gamesStore.selectedPodcast !== 'all' ? podcastMeta(gamesStore.selectedPodcast)?.name ?? '' : ''))

const { visibleItems: visibleTests, sentinel } = useInfiniteScroll(rest, { pageSize: 48 })

function isPlaying({ ep, test }) {
  const cur = playerStore.current
  return !!cur && cur.url === ep.audioUrl && cur.slug === (test.slug ?? null)
}

function play({ ep, test }) {
  playerStore.play({
    game:            test.resolvedName ?? test.name,
    slug:            test.slug ?? null,
    episode:         ep.title,
    url:             ep.audioUrl,
    // Resume from saved progress when partway through; untouched/finished starts at the test.
    ts:              playerStore.resumeTimeFor(ep.slug, test.timestampSeconds || 0),
    timestamp:       test.timestamp || null,
    episodeImageUrl: ep.imageUrl ?? null,
    pubTs:           ep.pubTs,
    episodeSlug:     ep.slug,
    episodeUrlSlug:  ep.urlSlug ?? null,
    coverImageId:    test.coverImageId ?? null,
    podcast:         ep.podcast ?? null,
    tests:           ep.games ?? [],
  })
}

function view(item) {
  router.push(testHref(item))
}

// ── Reprendre ────────────────────────────────────────────────────────────────
const bySlug = computed(() => new Map(episodes.value.map(ep => [ep.slug, ep])))

const resumeItems = computed(() => {
  if (props.searchQuery?.trim()) return []
  return playerStore.inProgress
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

function resume(item) {
  const { ep, test, entry } = item
  playerStore.play({
    game:            item.name,
    slug:            test?.slug ?? entry.gameSlug ?? null,
    episode:         ep.title,
    url:             ep.audioUrl,
    ts:              entry.currentTime,
    episodeImageUrl: ep.imageUrl ?? null,
    pubTs:           ep.pubTs,
    episodeSlug:     ep.slug,
    episodeUrlSlug:  ep.urlSlug ?? null,
    coverImageId:    item.cover,
    podcast:         ep.podcast ?? null,
    tests:           ep.games ?? [],
  })
}
</script>

<template>
  <div class="scroll-area feed-scroll">
    <!-- The newest test's cover, blurred, behind the top of the page -->
    <div v-if="featured?.test.coverImageId" class="backdrop" aria-hidden="true">
      <img :src="igdbUrl(featured.test.coverImageId, 't_cover_small')" alt="" />
    </div>
    <div class="content feed">
      <div v-if="loading" aria-hidden="true" class="grid">
        <div v-for="i in 12" :key="i" class="skeleton-shimmer skel" />
      </div>

      <div v-else-if="error" class="empty">
        <p class="cond empty__title">Hors antenne</p>
        <p class="empty__text">{{ error }}</p>
      </div>

      <div v-else-if="!tests.length" class="empty">
        <p class="cond empty__title">Rien ici</p>
        <p class="empty__text">Aucun test trouvé.</p>
      </div>

      <template v-else>
        <div class="top" :class="{ 'has-resume': resumeItems.length }">
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
            <h2 id="h-latest">{{ searchQuery?.trim() ? 'Résultats' : 'Derniers tests' }}<span v-if="showName" class="filter-name"> · {{ showName }}</span></h2>
            <span class="head-side">
              <button v-if="showName" type="button" class="chip-btn" @click="gamesStore.setPodcast('all')">✕ Toutes les émissions</button>
              <span class="lab">{{ tests.length }} tests</span>
            </span>
          </div>
          <div class="grid">
            <TestCard
              v-for="item in visibleTests"
              :key="item.ep.slug + '|' + (item.test.slug ?? item.test.name)"
              :item="item"
              :is-playing="isPlaying(item)"
              :is-paused="playerStore.paused"
              @play="play"
              @toggle-pause="playerStore.togglePlayback()"
              @view="view"
            />
          </div>
          <div ref="sentinel" class="h-1" />
        </section>
      </template>
    </div>
  </div>
</template>

<style scoped>
.feed-scroll { position: relative; }
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

.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px 14px;
}
@media (min-width: 600px) { .grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (min-width: 900px) { .grid { grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 28px 24px; } }
.skel { aspect-ratio: 3 / 4; }

.filter-name { color: var(--c-fg-2); }
.head-side { display: flex; align-items: center; gap: 12px; }
/* Phone: the heading on its own line, the filter and the count beneath. */
@media (max-width: 767px) {
  .latest .section-head { flex-wrap: wrap; }
  .latest .section-head h2 { flex-basis: 100%; }
  .head-side { flex: 1; justify-content: space-between; }
}
.empty { padding: 64px 0; text-align: center; }
.empty__title { font-size: var(--text-2xl); margin: 0 0 8px; }
.empty__text { color: var(--c-fg-2); margin: 0; }
</style>
