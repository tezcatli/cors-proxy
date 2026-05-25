<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { Play, Pause, VolumeX, Clock, ChevronRight } from 'lucide-vue-next'
import { formatDate } from '../lib/utils.js'

const props = defineProps({
  episode:   Object,
  gameName:  String,
  isPlaying: Boolean,
  isPaused:  Boolean,
})
const emit = defineEmits(['play', 'togglePause', 'view'])

const titleEl     = ref(null)
const needsScroll = ref(false)

onMounted(async () => {
  await nextTick()
  if (titleEl.value) needsScroll.value = titleEl.value.scrollWidth > titleEl.value.clientWidth
})

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
}
</script>

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
      <div
        ref="titleEl"
        class="ep-title-scroll"
        :class="{ 'ep-title-scroll--on': needsScroll }"
      >
        <span class="ep-title-inner">{{ episode.title }}</span>
        <span v-if="needsScroll" class="ep-title-inner" aria-hidden="true">{{ episode.title }}</span>
      </div>
      <div class="text-[0.7rem] text-white/45 flex gap-2 flex-wrap font-medium">
        <span>{{ formatDate(episode.pubTs) }}</span>
        <span
          v-if="episode.timestamp"
          class="font-mono font-semibold tabular-nums inline-flex items-center gap-1"
          style="color: var(--game-accent);"
        ><Clock :size="11" :stroke-width="2.25" /> {{ episode.timestamp }}</span>
      </div>
    </div>
    <button
      class="btn btn-sm btn-ghost text-white/40 hover:text-white/85 px-2 self-center flex-shrink-0 !min-h-0 h-8"
      aria-label="Détails de l'épisode"
      @click.stop="emit('view', episode)"
    ><ChevronRight :size="18" :stroke-width="2" /></button>
  </div>
</template>
