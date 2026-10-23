<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { fetchEpisodes } from '../lib/games.js'
import { formatTime, progressPct } from '../lib/utils.js'
import { igdbUrl } from '../lib/igdbCdn.js'
import { podcastMeta } from '../lib/podcasts.js'
import { useEpisodePlayer } from '../composables/useEpisodePlayer.js'
import { useInfiniteScroll } from '../composables/useInfiniteScroll.js'
import { useGamesStore } from '../stores/games.js'
import EpisodeFeedCard from './EpisodeFeedCard.vue'
import { Play } from 'lucide-vue-next'

// The home (« Tests »): what was started, then every episode newest first, each
// told by its tests. Shares `selectedPodcast` with the catalog: one choice of
// show, applied wherever the user is.
const props = defineProps({
  searchQuery:   String,
  refreshSignal: { type: Number, default: 0 },
})

const router     = useRouter()
const gamesStore = useGamesStore()
const { playerStore, isEpPlaying, playEp, togglePause } = useEpisodePlayer()

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

const { visibleItems: visibleEpisodes, sentinel } = useInfiniteScroll(
  filteredEpisodes,
  { pageSize: 50 },
)

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

// The feed plays an episode from its first test, not from its intro.
function playFromFirstTest(ep) {
  const first = ep.games?.find(g => g.timestampSeconds != null)
  playEp(first ? { ...ep, timestampSeconds: first.timestampSeconds, timestamp: first.timestamp } : ep)
}

function viewEp(ep) {
  router.push('/episode/' + encodeURIComponent(ep.urlSlug))
}
</script>

<template>
  <div class="scroll-area feed-scroll">
    <div class="content feed">
      <section v-if="resumeItems.length" class="resume" aria-labelledby="h-resume">
        <div class="section-head"><h2 id="h-resume"><span class="onair" aria-hidden="true"></span> Reprendre</h2></div>
        <div class="resume__list">
          <button v-for="item in resumeItems" :key="item.ep.slug" type="button" class="resume__card" @click="resume(item)">
            <img v-if="item.cover" :src="igdbUrl(item.cover, 't_cover_small')" alt="" class="resume__cover" />
            <span v-else class="resume__cover resume__cover--none"></span>
            <span class="resume__text">
              <span class="cond resume__name clamp-2">{{ item.name }}</span>
              <span class="mono resume__meta ellipsis">{{ podcastMeta(item.ep.podcast?.id)?.label }} · {{ formatTime(item.entry.currentTime) }}</span>
              <span class="resume__bar"><span :style="{ width: item.pct + '%' }"></span></span>
            </span>
            <span class="resume__go" aria-hidden="true"><Play :size="16" fill="currentColor" :stroke-width="0" /></span>
          </button>
        </div>
      </section>

      <section aria-labelledby="h-latest">
        <div class="section-head">
          <h2 id="h-latest">{{ searchQuery?.trim() ? 'Résultats' : 'Derniers tests' }}</h2>
          <span v-if="!loading && !error" class="lab">{{ filteredEpisodes.length }} épisodes</span>
        </div>

        <div v-if="loading" aria-hidden="true">
          <div v-for="i in 8" :key="i" class="skel">
            <div class="skeleton-shimmer skel__play" />
            <div class="skeleton-shimmer skel__cover" />
            <div class="skel__lines"><div class="skeleton-shimmer" /><div class="skeleton-shimmer" /></div>
          </div>
        </div>

        <div v-else-if="error" class="empty">
          <p class="cond empty__title">Hors antenne</p>
          <p class="empty__text">{{ error }}</p>
        </div>

        <div v-else-if="!filteredEpisodes.length" class="empty">
          <p class="cond empty__title">Rien ici</p>
          <p class="empty__text">Aucun épisode trouvé.</p>
        </div>

        <div v-else class="feed__list">
          <EpisodeFeedCard
            v-for="ep in visibleEpisodes"
            :key="ep.slug"
            :episode="ep"
            :is-playing="isEpPlaying(ep)"
            :is-paused="playerStore.paused"
            @play="playFromFirstTest"
            @toggle-pause="togglePause"
            @view="viewEp"
          />
        </div>
        <div ref="sentinel" class="h-1" />
      </section>
    </div>
  </div>
</template>

<style scoped>
.feed { max-width: 960px; padding-top: 20px; }
.section-head h2 { display: inline-flex; align-items: center; gap: 12px; }

.resume { margin-bottom: 36px; }
.resume__list { display: grid; grid-template-columns: minmax(0, 1fr); gap: 8px; }
@media (min-width: 900px) { .resume__list { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
.resume__card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px;
  border: 0;
  background: var(--c-surface);
  box-shadow: inset 0 0 0 1px var(--c-line);
  color: var(--c-fg);
  text-align: left;
  cursor: pointer;
  min-width: 0;
}
.resume__card:hover { background: var(--c-raised); }
.resume__cover { width: 48px; height: 64px; object-fit: cover; flex-shrink: 0; }
.resume__cover--none { background: var(--c-raised); }
.resume__text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.resume__name { font-size: 21px; line-height: 1; }
.resume__meta { color: var(--c-fg-3); font-size: var(--text-xs); }
.resume__bar { display: block; height: 3px; background: var(--c-line-strong); }
.resume__bar span { display: block; height: 100%; background: var(--c-accent); }
.resume__go {
  width: 44px;
  height: 44px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--c-accent);
  color: var(--c-accent-fg);
}

.feed__list { border-top: 1px solid var(--c-line); }

.skel { display: grid; grid-template-columns: 44px 48px 1fr; gap: 14px; align-items: center; padding: 12px 0; border-bottom: 1px solid var(--c-line); }
.skel__play { width: 44px; height: 44px; }
.skel__cover { width: 48px; height: 64px; }
.skel__lines { display: flex; flex-direction: column; gap: 8px; }
.skel__lines div { height: 14px; }
.skel__lines div:last-child { width: 50%; }

.empty { padding: 64px 0; text-align: center; }
.empty__title { font-size: var(--text-2xl); margin: 0 0 8px; }
.empty__text { color: var(--c-fg-2); margin: 0; }
</style>
