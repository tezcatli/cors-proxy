<script setup>
import { computed } from 'vue'
import { Play, Pause, VolumeX } from 'lucide-vue-next'
import { formatDate, PROGRESS_MIN_PCT } from '../lib/utils.js'
import { useProgress } from '../composables/useProgress.js'
import Marquee from './Marquee.vue'

const props = defineProps({
  episode:   Object,
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
  if (!hasAudio.value) return VolumeX
  if (props.isPlaying) return props.isPaused ? Play : Pause
  return Play
})

function handlePlay() {
  if (!hasAudio.value) return
  if (props.isPlaying) emit('togglePause')
  else emit('play', props.episode)
}

// Keyboard activation of the row (view). Ignore keys that bubbled up from the
// inner play button so Enter/Space there doesn't also trigger a navigation.
function onRowKey(e) {
  if (e.target !== e.currentTarget) return
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); emit('view', props.episode) }
}

const playLabel = computed(() =>
  !hasAudio.value ? 'Pas d’audio'
    : props.isPlaying && !props.isPaused ? 'Mettre en pause' : 'Lire l’épisode'
)
</script>

<template>
  <div
    class="episode-card"
    :class="{ 'has-audio': hasAudio, playing: isPlaying }"
    role="button"
    tabindex="0"
    :aria-label="`Voir l’épisode : ${episode.title}`"
    style="cursor: pointer"
    @click="emit('view', episode)"
    @keydown="onRowKey"
  >
    <button type="button" class="ep-icon" :aria-label="playLabel" @click.stop="handlePlay">
      <component :is="iconComp" :size="14" :fill="hasAudio ? 'currentColor' : 'none'" :stroke-width="hasAudio ? 0 : 2" />
    </button>

    <img
      v-if="episode.imageUrl"
      :src="episode.imageUrl"
      :alt="episode.title"
      class="w-10 h-10 rounded-lg object-cover flex-shrink-0 self-center shadow-e1"
      loading="lazy"
    />
    <div v-else class="w-10 h-10 flex-shrink-0 rounded-lg bg-white/5" />

    <div class="flex-1 min-w-0">
      <Marquee :text="episode.title" inner-class="ep-title" />
      <div class="text-[0.7rem] text-white/45 flex gap-1.5 flex-wrap mt-0.5 font-medium">
        <span>{{ formatDate(episode.pubTs) }}</span>
      </div>
    </div>

    <div v-if="progress.pct > PROGRESS_MIN_PCT" class="ep-progress" :class="{ 'ep-progress--done': progress.done }">
      <div class="ep-progress-fill" :style="{ width: progress.pct + '%' }"></div>
    </div>
  </div>
</template>
