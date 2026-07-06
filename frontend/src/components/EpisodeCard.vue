<script setup>
import { computed } from 'vue'
import { Play, Pause, VolumeX, Clock, ChevronRight, Check } from 'lucide-vue-next'
import { formatDate, PROGRESS_MIN_PCT } from '../lib/utils.js'
import { useProgress } from '../composables/useProgress.js'
import Marquee from './Marquee.vue'
import PodcastBadge from './PodcastBadge.vue'

const props = defineProps({
  episode:   Object,
  gameName:  String,
  isPlaying: Boolean,
  isPaused:  Boolean,
})
const emit = defineEmits(['play', 'togglePause', 'view'])

const { episodeProgress } = useProgress()

const progress = computed(() =>
  episodeProgress(props.episode.slug, props.episode.timestampSeconds ?? 0)
)

const hasAudio = computed(() => !!props.episode.audioUrl)

const iconComp = computed(() => {
  if (!hasAudio.value)   return VolumeX
  if (props.isPlaying)   return props.isPaused ? Play : Pause
  return Play
})

function handleClick() {
  if (!hasAudio.value) return
  if (props.isPlaying) emit('togglePause')
  else emit('play', props.episode)
}

function handleKey(e) {
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleClick() }
}</script>

<template>
  <div
    class="episode-card"
    :class="{ 'has-audio': hasAudio, playing: isPlaying }"
    :role="hasAudio ? 'button' : 'listitem'"
    :tabindex="hasAudio ? 0 : -1"
    @keydown="handleKey"
  >
    <div class="ep-icon" @click="handleClick">
      <component :is="iconComp" :size="14" :fill="hasAudio ? 'currentColor' : 'none'" :stroke-width="hasAudio ? 0 : 2" />
    </div>
    <div class="flex-1 min-w-0" @click="handleClick">
      <Marquee :text="episode.title" class="mb-[3px]" inner-class="ep-title" />
      <div class="text-[0.7rem] text-white/45 flex gap-2 flex-wrap font-medium items-center">
        <PodcastBadge v-if="episode.podcast" :id="episode.podcast.id" />
        <span>{{ formatDate(episode.pubTs) }}</span>
        <span
          v-if="episode.timestamp"
          class="text-game-accent font-mono font-semibold tabular-nums inline-flex items-center gap-1"
        ><Clock :size="11" :stroke-width="2.25" /> {{ episode.timestamp }}</span>
        <span
          v-if="progress.done"
          class="text-game-accent font-semibold inline-flex items-center gap-0.5"
          aria-label="Écouté"
        ><Check :size="11" :stroke-width="3" /> Écouté</span>
      </div>
    </div>
    <button
      class="btn btn-sm btn-ghost text-white/40 hover:text-white/85 px-2 self-center flex-shrink-0 !min-h-0 h-8"
      aria-label="Détails de l'épisode"
      @click.stop="emit('view', episode)"
    ><ChevronRight :size="18" :stroke-width="2" /></button>
    <div v-if="progress.pct > PROGRESS_MIN_PCT" class="ep-progress" :class="{ 'ep-progress--done': progress.done }">
      <div class="ep-progress-fill" :style="{ width: progress.pct + '%' }"></div>
    </div>
  </div>
</template>
