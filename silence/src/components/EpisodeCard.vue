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
    <div class="episode-info">
      <div class="episode-title">{{ episode.title }}</div>
      <div class="episode-meta">
        <span>{{ formatDate(episode.pubDate) }}</span>
        <span v-if="episode.timestamp" class="episode-ts">⏱ {{ episode.timestamp }}</span>
      </div>
    </div>
  </div>
</template>
