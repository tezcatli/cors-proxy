<script setup>
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { usePlayerStore } from '../stores/player.js'
import { episodeTrack, formatDayMonth, formatTime } from '../lib/utils.js'
import { igdbUrl } from '../lib/igdbCdn.js'
import { Play, Pause } from 'lucide-vue-next'

// One episode in a list (a podcast's page, the search): its date, its title,
// the covers of its tests, where it was left, and ▶ — the whole episode, from
// its start or where it was left (DECISIONS.md, « Interface » : une seule
// écoute). The row opens the episode's page.
const props = defineProps({
  ep:          { type: Object, required: true },
  showPodcast: { type: Boolean, default: false },   // a list mixing podcasts says whose
})

const playerStore = usePlayerStore()

const COVERS = 4
const tests  = computed(() => props.ep.games ?? [])
const covers = computed(() => tests.value.slice(0, COVERS))
const more   = computed(() => Math.max(0, tests.value.length - COVERS))

const resume   = computed(() => playerStore.resumeEntryFor(props.ep.slug))
const isOnAir  = computed(() => playerStore.current?.episodeSlug === props.ep.slug)
const playing  = computed(() => isOnAir.value && !playerStore.paused)

const meta = computed(() => [props.showPodcast ? props.ep.podcast?.name : null, formatDayMonth(props.ep.pubTs)]
  .filter(Boolean).join(' · '))
const playLabel = computed(() =>
  playing.value ? `Pause : ${props.ep.title}`
  : isOnAir.value || resume.value ? `Reprendre ${props.ep.title}`
  : `Écouter depuis le début ${props.ep.title}`)

function onPlay() {
  if (isOnAir.value) { playerStore.togglePlayback(); return }
  playerStore.play(episodeTrack(props.ep, { ts: resume.value?.currentTime ?? 0 }))
}
</script>

<template>
  <div class="row line" :class="{ 'is-on': isOnAir }">
    <RouterLink :to="`/episode/${encodeURIComponent(ep.urlSlug)}`" class="row__main">
      <span class="row__date">{{ meta }}</span>
      <span class="row__title clamp-2">{{ ep.title }}</span>
      <span v-if="covers.length || resume" class="row__extra">
        <span v-if="covers.length" class="row__covers" :aria-label="`${tests.length} test${tests.length > 1 ? 's' : ''}`">
          <template v-for="t in covers" :key="t.name">
            <img v-if="t.coverImageId" :src="igdbUrl(t.coverImageId, 't_cover_small')" alt="" class="row__cover" loading="lazy" data-test="cover" />
            <span v-else class="row__cover row__cover--none" data-test="cover"></span>
          </template>
          <span v-if="more" class="lab row__more">+{{ more }}</span>
        </span>
        <span v-if="resume && !isOnAir" class="row__resume">En cours · {{ formatTime(resume.currentTime) }}</span>
      </span>
    </RouterLink>
    <button type="button" class="icon-action icon-action--boxed row__play" :aria-label="playLabel" :disabled="!ep.audioUrl" @click="onPlay">
      <Pause v-if="playing" :size="15" fill="currentColor" :stroke-width="0" />
      <Play v-else :size="15" fill="currentColor" :stroke-width="0" />
    </button>
  </div>
</template>

<style scoped>
.row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 44px;
  gap: 12px;
  align-items: center;
  padding: 12px 0;
}
.row.is-on { padding-left: 12px; }
.row__main { display: flex; flex-direction: column; gap: 6px; min-width: 0; color: var(--c-fg); text-decoration: none; }
.row__main:hover .row__title { color: var(--c-accent); }
.row__date { font-size: var(--text-xs); color: var(--c-fg-3); font-variant-numeric: tabular-nums; }
.row__title { font-family: var(--font-display); font-weight: 600; font-size: 15px; line-height: 1.3; }
.row__extra { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.row__covers { display: inline-flex; align-items: center; gap: 5px; }
.row__cover { width: 21px; height: 28px; object-fit: cover; box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.16); }
.row__cover--none { background: var(--c-raised); }
.row__more { font-size: 11px; }
.row__resume { font-size: var(--text-xs); color: var(--c-accent); }
.row.is-on .row__title { color: var(--c-accent); }
.row__play.is-on { color: var(--c-accent); }

/* Wide: one line — date, title, covers, ▶. */
@media (min-width: 900px) {
  .row { grid-template-columns: minmax(0, 1fr) 44px; padding: 14px 0; }
  .row.is-on { padding-left: 16px; }
  .row__main { display: grid; grid-template-columns: 72px minmax(0, 1fr) auto; align-items: center; gap: 4px 16px; }
  .row__date { grid-row: 1 / span 2; }
  .row__title { font-size: 16px; }
  .row__extra { display: contents; }
  .row__covers { grid-column: 3; grid-row: 1 / span 2; }
  .row__resume { grid-column: 2; }
  .row__cover { width: 30px; height: 40px; }
}
</style>
