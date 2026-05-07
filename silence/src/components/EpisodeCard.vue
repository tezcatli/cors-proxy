<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
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

const icon = computed(() => {
  if (!hasAudio.value)   return '🔇'
  if (props.isPlaying)   return props.isPaused ? '▶' : '⏸'
  return '▶'
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
    <div class="ep-icon" @click="handleClick">{{ icon }}</div>
    <div class="flex-1 min-w-0" @click="handleClick">
      <div ref="titleEl" class="ep-title-scroll [.playing_&]:text-secondary" :class="{ 'ep-title-scroll--on': needsScroll }">
        <span class="ep-title-inner">{{ episode.title }}</span>
        <span v-if="needsScroll" class="ep-title-inner" aria-hidden="true">{{ episode.title }}</span>
      </div>
      <div class="text-[0.72rem] text-base-content/50 flex gap-2 flex-wrap">
        <span>{{ formatDate(episode.pubTs) }}</span>
        <span v-if="episode.timestamp" class="text-primary font-semibold">⏱ {{ episode.timestamp }}</span>
      </div>
    </div>
    <button
      class="btn btn-sm btn-ghost text-base-content/40 hover:text-base-content/80 px-2 self-center flex-shrink-0 text-[1.2rem]"
      aria-label="Détails de l'épisode"
      @click.stop="emit('view', episode)"
    >›</button>
  </div>
</template>
