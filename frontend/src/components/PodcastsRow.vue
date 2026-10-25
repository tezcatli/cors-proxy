<script setup>
import { computed, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { useGamesStore } from '../stores/games.js'
import { PODCASTS } from '../lib/podcasts.js'
import { usePodcastsSeen } from '../composables/usePodcastsSeen.js'

// « Les podcasts », between the newest tests and the games (DECISIONS.md,
// « Interface »): one tile per podcast — its image, when its newest episode
// came out, a dot when that is newer than the last visit — leading to its page.
const gamesStore = useGamesStore()
const { isNew, meet } = usePodcastsSeen()

const DAY = 86400
function ago(ts) {
  const days = Math.floor((Date.now() / 1000 - ts) / DAY)
  if (days <= 0) return "aujourd'hui"
  if (days === 1) return 'hier'
  if (days < 30) return `il y a ${days} j`
  return new Date(ts * 1000).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })
}

const latestByPodcast = computed(() => {
  const latest = {}
  for (const ep of gamesStore.episodes) {
    const id = ep.podcast?.id
    if (id && (!latest[id] || (ep.pubTs ?? 0) > (latest[id].pubTs ?? 0))) latest[id] = ep
  }
  return latest
})
watch(latestByPodcast, latest => {
  for (const [id, ep] of Object.entries(latest)) meet(id, ep.pubTs)
}, { immediate: true })

const tiles = computed(() =>
  PODCASTS
    .map(p => ({ ...p, ep: latestByPodcast.value[p.id] ?? null }))
    .filter(t => t.ep)
    .sort((a, b) => (b.ep.pubTs ?? 0) - (a.ep.pubTs ?? 0))
    .map(t => ({
      ...t,
      image: t.ep.podcast?.imageUrl ?? null,
      last:  t.ep.pubTs ? ago(t.ep.pubTs) : '',
      fresh: isNew(t.id, t.ep.pubTs),
    })))
</script>

<template>
  <section v-if="tiles.length" class="content podcasts" aria-labelledby="h-podcasts">
    <div class="section-head"><h2 id="h-podcasts">Les podcasts</h2></div>
    <div class="podcasts__row">
      <RouterLink v-for="t in tiles" :key="t.id" :to="`/podcast/${t.id}`" class="tile">
        <span class="tile__art">
          <img v-if="t.image" :src="t.image" alt="" loading="lazy" />
          <span v-else class="tile__none cond">{{ t.label }}</span>
          <span v-if="t.fresh" class="tile__dot" aria-hidden="true"></span>
        </span>
        <span class="tile__name">{{ t.name }}<span v-if="t.fresh" class="sr-only"> (nouvel épisode)</span></span>
        <span class="tile__last">{{ t.last }}</span>
      </RouterLink>
    </div>
  </section>
</template>

<style scoped>
.podcasts { position: relative; margin-bottom: 36px; }   /* above the tests' blurred backdrop */
.podcasts__row {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: 27%;
  gap: 12px;
  overflow-x: auto;
  scrollbar-width: none;
  margin: 0 calc(var(--gutter) * -1);
  padding: 4px var(--gutter) 8px;
}
.podcasts__row::-webkit-scrollbar { display: none; }
@media (min-width: 600px) { .podcasts__row { grid-auto-columns: 18%; } }
@media (min-width: 900px) {
  .podcasts__row { grid-auto-flow: row; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 24px; overflow: visible; margin: 0; padding: 4px 0 8px; }
}
.tile { display: flex; flex-direction: column; gap: 6px; min-width: 0; color: var(--c-fg); text-decoration: none; }
.tile__art { position: relative; display: block; aspect-ratio: 1 / 1; background: var(--c-surface); box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.14); }
.tile__art img { width: 100%; height: 100%; object-fit: cover; display: block; }
.tile:hover .tile__art { box-shadow: 0 0 0 2px var(--c-accent); }
.tile__none { display: flex; align-items: center; justify-content: center; height: 100%; font-size: 22px; }
.tile__dot { position: absolute; top: 8px; right: 8px; width: 12px; height: 12px; border-radius: 50%; background: var(--c-accent); box-shadow: 0 0 0 4px var(--game-veil); }
.tile__name { font-family: var(--font-display); font-weight: 600; font-size: var(--text-sm); line-height: 1.2; }
.tile__last { font-size: var(--text-xs); color: var(--c-fg-3); }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
</style>
