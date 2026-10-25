<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useGamesStore } from '../stores/games.js'
import { usePlayerStore } from '../stores/player.js'
import { podcastMeta } from '../lib/podcasts.js'
import { episodeTrack, formatDayMonth, formatTime } from '../lib/utils.js'
import { paletteFromAccent, themeStyle } from '../composables/useGameTheme.js'
import { useInfiniteScroll } from '../composables/useInfiniteScroll.js'
import { usePodcastsSeen } from '../composables/usePodcastsSeen.js'
import BackBar from './BackBar.vue'
import EpisodeRow from './EpisodeRow.vue'
import GameCard from './GameCard.vue'
import { Play, Pause } from 'lucide-vue-next'

// A podcast's page (DECISIONS.md, « Interface »): listen to it — its newest
// episode, or the one left partway — and every one of its episodes, those that
// test nothing included, newest first; then its games. It replaces the filter
// the Ludothèque's header had. Wears the podcast's colour (`lib/podcasts.js`).
const route       = useRoute()
const router      = useRouter()
const gamesStore  = useGamesStore()
const playerStore = usePlayerStore()

const id      = route.params.id
const podcast = podcastMeta(id)
const theme   = themeStyle(paletteFromAccent(podcast?.accent))

onMounted(() => {
  document.body.style.overflow = 'hidden'
  document.addEventListener('keydown', onKeydown)
  if (!gamesStore.episodesLoaded) gamesStore.loadEpisodes()
  if (!gamesStore.all.length && !gamesStore.loading) gamesStore.load()
})
onUnmounted(() => {
  document.body.style.overflow = ''
  document.removeEventListener('keydown', onKeydown)
})
function back() {
  if (router.options.history.state?.back) router.back()
  else router.push('/')
}
function onKeydown(e) { if (e.key === 'Escape') back() }

const episodes = computed(() =>
  gamesStore.episodes.filter(ep => ep.podcast?.id === id).sort((a, b) => (b.pubTs ?? 0) - (a.pubTs ?? 0)))
const latest   = computed(() => episodes.value[0] ?? null)
const image    = computed(() => latest.value?.podcast?.imageUrl ?? latest.value?.imageUrl ?? null)
const nTests   = computed(() => episodes.value.reduce((n, ep) => n + (ep.games?.length ?? 0), 0))

// Visiting the page sees its newest episode: its tile loses its dot.
const { markSeen } = usePodcastsSeen()
watch(latest, ep => { if (ep) markSeen(id, ep.pubTs) }, { immediate: true })

// ── The main button: what this podcast's listening is at ────────────────────
// The episode on air, else the latest left partway, else the newest.
const onAir = computed(() => {
  const slug = playerStore.current?.episodeSlug
  return slug ? episodes.value.find(ep => ep.slug === slug) ?? null : null
})
const resumed = computed(() => {
  if (onAir.value) return null
  for (const p of playerStore.inProgress) {
    const ep = episodes.value.find(e => e.slug === p.episodeSlug)
    if (ep && playerStore.resumeEntryFor(ep.slug)) return { ep, entry: playerStore.resumeEntryFor(ep.slug) }
  }
  return null
})
const mainEp = computed(() => onAir.value ?? resumed.value?.ep ?? latest.value)
const mainLabel = computed(() => {
  if (onAir.value) return playerStore.paused ? 'Reprendre' : 'Pause'
  if (resumed.value) return `Reprendre à ${formatTime(resumed.value.entry.currentTime)}`
  return 'Écouter le dernier épisode'
})
function onMain() {
  if (onAir.value) { playerStore.togglePlayback(); return }
  const ep = mainEp.value
  if (ep) playerStore.play(episodeTrack(ep, { ts: resumed.value?.entry.currentTime ?? 0 }))
}

// ── Episodes, with a heading per year ───────────────────────────────────────
const { visibleItems, sentinel } = useInfiniteScroll(episodes, { pageSize: 40 })
const years = computed(() => {
  const groups = []
  for (const ep of visibleItems.value) {
    const year = ep.pubTs ? new Date(ep.pubTs * 1000).getFullYear() : '—'
    if (groups.at(-1)?.year !== year) groups.push({ year, eps: [] })
    groups.at(-1).eps.push(ep)
  }
  return groups
})

// ── Its games: a few, then all of them on demand ────────────────────────────
const GAMES_FIRST = 12
const games    = computed(() => gamesStore.filtered('', id).filter(g => g.igdb !== null))
const allGames = ref(false)
const shownGames = computed(() => (allGames.value ? games.value : games.value.slice(0, GAMES_FIRST)))
</script>

<template>
  <div class="overlay-page" :style="[theme, { zIndex: 'var(--z-detail)' }]">
    <BackBar label="Ludothèque" @back="back" />

    <div v-if="!podcast" class="state"><p class="cond state__title">Podcast introuvable</p></div>

    <div v-else class="scroll-area">
      <div class="content pod">
        <aside class="pod__side">
          <header class="pod__head">
            <img v-if="image" :src="image" alt="" class="pod__art" />
            <span v-else class="pod__art pod__art--none cond">{{ podcast.label }}</span>
            <div class="pod__id">
              <h1 class="pod__name cond">{{ podcast.name }}</h1>
              <span v-if="gamesStore.episodesLoaded" class="lab">{{ episodes.length }} épisodes · {{ nTests }} tests</span>
            </div>
          </header>

          <div v-if="mainEp" class="pod__main">
            <button type="button" class="btn-play" :disabled="!mainEp.audioUrl" @click="onMain">
              <Pause v-if="onAir && !playerStore.paused" :size="14" fill="currentColor" :stroke-width="0" />
              <Play v-else :size="14" fill="currentColor" :stroke-width="0" />
              {{ mainLabel }}
            </button>
            <RouterLink :to="`/episode/${encodeURIComponent(mainEp.urlSlug)}`" class="pod__context">
              <span class="pod__date">{{ formatDayMonth(mainEp.pubTs) }}</span>
              <span class="clamp-2">{{ mainEp.title }}</span>
            </RouterLink>
          </div>

          <section v-if="games.length" class="pod__games" aria-labelledby="h-pod-games">
            <div class="section-head">
              <h2 id="h-pod-games">Ses jeux</h2>
              <button v-if="games.length > GAMES_FIRST" type="button" class="lab pod__all" :aria-expanded="allGames" @click="allGames = !allGames">
                {{ allGames ? 'Moins' : `Tous · ${games.length}` }}
              </button>
            </div>
            <div class="pod__grid" :class="{ 'is-all': allGames }">
              <GameCard v-for="g in shownGames" :key="g.slug" :game="g" />
            </div>
          </section>
        </aside>

        <main class="pod__eps" aria-labelledby="h-pod-eps">
          <div class="section-head"><h2 id="h-pod-eps">Épisodes</h2></div>
          <div v-if="gamesStore.episodesLoading" aria-hidden="true">
            <div v-for="i in 6" :key="i" class="skeleton-shimmer skel" />
          </div>
          <p v-else-if="gamesStore.episodesError" class="pod__empty">Erreur : {{ gamesStore.episodesError }}</p>
          <p v-else-if="!episodes.length" class="pod__empty">Aucun épisode.</p>
          <template v-else>
            <section v-for="g in years" :key="g.year" :aria-label="String(g.year)">
              <h3 class="lab pod__year">{{ g.year }}</h3>
              <EpisodeRow v-for="ep in g.eps" :key="ep.slug" :ep="ep" />
            </section>
            <div ref="sentinel" class="h-1" />
          </template>
        </main>
      </div>
    </div>
  </div>
</template>

<style scoped>
.state { flex: 1; display: flex; align-items: center; justify-content: center; }
.state__title { font-size: var(--text-2xl); }

.pod { display: flex; flex-direction: column; gap: 28px; padding-top: 8px; }
.pod__side { display: flex; flex-direction: column; gap: 20px; }
.pod__head { display: flex; align-items: flex-end; gap: 16px; }
.pod__art { width: 112px; height: 112px; object-fit: cover; flex-shrink: 0; box-shadow: var(--shadow-cover); }
.pod__art--none { display: flex; align-items: center; justify-content: center; background: var(--c-surface); font-size: 24px; }
.pod__id { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.pod__name { margin: 0; font-size: clamp(28px, 4vw, 40px); overflow-wrap: anywhere; }
.pod__main { display: flex; flex-direction: column; gap: 8px; }
.pod__main .btn-play { min-height: 48px; }
.pod__context { display: flex; flex-direction: column; gap: 2px; color: var(--c-fg-2); font-size: var(--text-sm); text-decoration: none; }
.pod__date { font-size: var(--text-xs); color: var(--c-fg-3); }
.pod__context:hover { color: var(--c-fg); }
.pod__all { border: 0; background: transparent; color: var(--c-accent); cursor: pointer; min-height: 44px; }

/* Phone: a few covers in a row to swipe; all of them, a grid. */
.pod__grid {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: 26%;
  gap: 10px;
  overflow-x: auto;
  scrollbar-width: none;
  margin: 0 calc(var(--gutter) * -1);
  padding: 0 var(--gutter) 4px;
}
.pod__grid::-webkit-scrollbar { display: none; }
.pod__grid.is-all { grid-auto-flow: row; grid-template-columns: repeat(3, minmax(0, 1fr)); grid-auto-columns: auto; overflow: visible; margin: 0; padding: 0; }

.pod__year { margin: 18px 0 2px; color: var(--c-accent); }
.pod__eps .section-head { margin-bottom: 0; }
.pod__empty { color: var(--c-fg-2); }
.skel { height: 64px; margin-bottom: 8px; }

/* Wide: the podcast and its games in a column on the left, the episodes on the right. */
@media (min-width: 900px) {
  .pod { flex-direction: row; align-items: flex-start; gap: 56px; padding-top: 24px; }
  .pod__side { width: 360px; flex-shrink: 0; }
  .pod__head { flex-direction: column; align-items: flex-start; }
  .pod__art { width: 220px; height: 220px; }
  .pod__eps { flex: 1; min-width: 0; }
  .pod__grid, .pod__grid.is-all { grid-auto-flow: row; grid-template-columns: repeat(4, minmax(0, 1fr)); grid-auto-columns: auto; overflow: visible; margin: 0; padding: 0; }
}
</style>
