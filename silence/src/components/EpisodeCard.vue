<script setup>
import { computed } from 'vue'
import { formatDate } from '../lib/utils.js'

const props = defineProps({
  episode:   Object,
  gameName:  String,
  isPlaying: Boolean,
  isPaused:  Boolean,
})
const emit = defineEmits(['play', 'togglePause'])

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
    @click="handleClick"
    @keydown="handleKey"
  >
    <div class="ep-icon">{{ icon }}</div>
    <div class="flex-1 min-w-0">
      <div class="[.playing_&]:text-secondary text-[0.85rem] font-semibold leading-[1.35] whitespace-nowrap overflow-hidden text-ellipsis mb-[3px] sm:text-[0.88rem]">{{ episode.title }}</div>
      <div class="text-[0.72rem] text-base-content/50 flex gap-2 flex-wrap">
        <span>{{ formatDate(episode.pubDate) }}</span>
        <span v-if="episode.timestamp" class="text-primary font-semibold">⏱ {{ episode.timestamp }}</span>
      </div>
    </div>
  </div>
</template>
