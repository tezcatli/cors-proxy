<script setup>
import { computed } from 'vue'
import { Play, Pause, VolumeX } from 'lucide-vue-next'
import { formatShortDate, PROGRESS_MIN_PCT } from '../lib/utils.js'
import { igdbUrl } from '../lib/igdbCdn.js'
import { verdictMeta } from '../lib/verdicts.js'
import { podcastMeta } from '../lib/podcasts.js'
import { useProgress } from '../composables/useProgress.js'

// One episode of the home feed, told by its tests: their covers and names, then
// `SIGLE · date · title`, and a verdict glyph per test. The row opens the episode;
// the square button plays it from its first test. Two siblings, never nested.
const props = defineProps({
  episode:   Object,
  isPlaying: Boolean,
  isPaused:  Boolean,
})
const emit = defineEmits(['play', 'togglePause', 'view'])

const { episodeProgress } = useProgress()

const tests    = computed(() => props.episode.games ?? [])
const covers   = computed(() => tests.value.filter(t => t.coverImageId).slice(0, 3))
const heading  = computed(() => tests.value.length
  ? tests.value.map(t => t.resolvedName ?? t.name).join(' · ')
  : props.episode.title)
const sigle    = computed(() => podcastMeta(props.episode.podcast?.id)?.label ?? '')
const href     = computed(() => '/episode/' + encodeURIComponent(props.episode.urlSlug))
const hasAudio = computed(() => !!props.episode.audioUrl)
const progress = computed(() =>
  episodeProgress(props.episode.slug, tests.value[0]?.timestampSeconds ?? 0))

const playLabel = computed(() =>
  !hasAudio.value ? 'Pas d’audio'
    : props.isPlaying && !props.isPaused ? 'Mettre en pause' : `Écouter : ${heading.value}`)

function onPlay() {
  if (!hasAudio.value) return
  props.isPlaying ? emit('togglePause') : emit('play', props.episode)
}
function onOpen(e) {
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return
  e.preventDefault()
  emit('view', props.episode)
}
</script>

<template>
  <div class="row" :class="{ 'is-playing': isPlaying }">
    <button type="button" class="row__play" :class="{ 'is-on': isPlaying }" :disabled="!hasAudio" :aria-label="playLabel" @click="onPlay">
      <VolumeX v-if="!hasAudio" :size="16" :stroke-width="2" />
      <Pause v-else-if="isPlaying && !isPaused" :size="16" fill="currentColor" :stroke-width="0" />
      <Play v-else :size="16" fill="currentColor" :stroke-width="0" />
    </button>

    <a class="row__link" :href="href" @click="onOpen">
      <span class="row__covers" :class="`n${Math.max(covers.length, 1)}`" aria-hidden="true">
        <img v-for="t in covers" :key="t.coverImageId" :src="igdbUrl(t.coverImageId, 't_cover_small')" alt="" loading="lazy" />
        <img v-if="!covers.length && episode.imageUrl" :src="episode.imageUrl" alt="" loading="lazy" class="is-show" />
        <span v-if="!covers.length && !episode.imageUrl" class="row__nocover"></span>
      </span>

      <span class="row__text">
        <span class="row__title cond clamp-2">{{ heading }}</span>
        <span class="row__meta mono ellipsis">
          {{ sigle }} · {{ formatShortDate(episode.pubTs) }}<template v-if="tests.length"> · {{ episode.title }}</template>
        </span>
        <span v-if="progress.pct > PROGRESS_MIN_PCT" class="row__progress"><span :style="{ width: progress.pct + '%' }"></span></span>
      </span>

      <span v-if="tests.length" class="row__marks mono" :aria-label="`Verdicts : ${tests.map(t => verdictMeta(t.verdict).label).join(', ')}`">
        <span v-for="(t, i) in tests.slice(0, 3)" :key="i" :class="{ 'is-none': !t.verdict }" aria-hidden="true">{{ verdictMeta(t.verdict).glyph }}</span>
        <span class="row__marks-word" aria-hidden="true" v-if="tests.length === 1">{{ verdictMeta(tests[0].verdict).label }}</span>
      </span>
    </a>
  </div>
</template>

<style scoped>
.row {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr);
  gap: 12px;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid var(--c-line);
}
.row.is-playing { box-shadow: inset 3px 0 0 var(--c-accent); padding-left: 10px; }
.row__play {
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 0;
  background: transparent;
  box-shadow: inset 0 0 0 1px var(--c-line-strong);
  color: var(--c-fg);
  cursor: pointer;
}
.row__play:hover:not(:disabled) { box-shadow: inset 0 0 0 1px var(--c-fg-3); }
.row__play.is-on { background: var(--c-accent); color: var(--c-accent-fg); box-shadow: none; }
.row__play:disabled { color: var(--c-fg-3); cursor: default; }

.row__link {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
  color: var(--c-fg);
  text-decoration: none;
}
/* Fixed width whatever the count, so every title starts on the same line. */
.row__covers { position: relative; flex-shrink: 0; width: 72px; height: 64px; }
.row__covers img, .row__nocover {
  position: absolute;
  top: 0;
  width: 48px;
  height: 64px;
  object-fit: cover;
  box-shadow: 0 0 0 1px var(--c-bg);
}
.row__covers img.is-show { height: 48px; top: 8px; }
.row__nocover { background: var(--c-surface); box-shadow: inset 0 0 0 1px var(--c-line); }
/* Several tests fan out: each cover steps right over the previous. */
.row__covers img:nth-child(2) { left: 12px; }
.row__covers img:nth-child(3) { left: 24px; }

.row__text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.row__title { font-size: 21px; line-height: 1.02; }
.row__meta { color: var(--c-fg-3); font-size: var(--text-xs); }
.row__progress { display: block; height: 3px; background: var(--c-line-strong); max-width: 160px; }
.row__progress span { display: block; height: 100%; background: var(--c-accent); }

.row__marks { display: flex; gap: 6px; align-items: center; flex-shrink: 0; font-size: var(--text-xs); font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; }
.row__marks .is-none { color: var(--c-fg-3); font-weight: 500; }
.row__marks-word { display: none; }
.row__link:hover .row__title { text-decoration: underline; text-decoration-thickness: 2px; text-underline-offset: 3px; }
@media (min-width: 768px) {
  .row { grid-template-columns: 44px minmax(0, 1fr); gap: 16px; }
  .row__title { font-size: 24px; }
  .row__marks-word { display: inline; }
}
</style>
