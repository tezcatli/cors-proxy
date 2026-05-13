<script setup>
import { computed, ref, watch, onUnmounted, nextTick } from 'vue'
import { formatDate } from '../lib/utils.js'

const props = defineProps({
  episode:   Object,
  isPlaying: Boolean,
  isPaused:  Boolean,
})
const emit = defineEmits(['play', 'togglePause', 'view'])

const hasAudio = computed(() => !!props.episode.audioUrl)

const icon = computed(() => {
  if (!hasAudio.value) return '🔇'
  if (props.isPlaying)  return props.isPaused ? '▶' : '⏸'
  return '▶'
})

const gameNames = computed(() =>
  props.episode.games?.map(g => g.name).join(' · ') || ''
)

function handlePlay() {
  if (!hasAudio.value) return
  if (props.isPlaying) emit('togglePause')
  else emit('play', props.episode)
}

const marqueeEl   = ref(null)
const needsScroll = ref(false)

async function checkScroll() {
  await nextTick()
  if (!marqueeEl.value) { needsScroll.value = false; return }
  const inner = marqueeEl.value.firstElementChild
  needsScroll.value = inner ? inner.offsetWidth > marqueeEl.value.clientWidth : false
}

let resizeObs = null
watch(marqueeEl, el => {
  resizeObs?.disconnect()
  resizeObs = null
  if (el) {
    resizeObs = new ResizeObserver(checkScroll)
    resizeObs.observe(el)
    checkScroll()
  }
})
onUnmounted(() => resizeObs?.disconnect())
</script>

<template>
  <div
    class="episode-card"
    :class="{ 'has-audio': hasAudio, playing: isPlaying }"
  >
    <div class="ep-icon" @click="handlePlay">{{ icon }}</div>

    <img
      v-if="episode.imageUrl"
      :src="episode.imageUrl"
      :alt="episode.title"
      class="w-9 h-9 rounded object-cover flex-shrink-0 self-center"
      loading="lazy"
      @click="handlePlay"
    />
    <div v-else class="w-9 h-9 flex-shrink-0" />

    <div class="flex-1 min-w-0" @click="handlePlay">
      <div
        ref="marqueeEl"
        class="ep-title-scroll [.playing_&]:text-secondary"
        :class="{ 'ep-title-scroll--on': needsScroll }"
      >
        <span class="ep-title-inner">{{ episode.title }}</span>
        <span v-if="needsScroll" class="ep-title-inner" aria-hidden="true">{{ episode.title }}</span>
      </div>
      <div class="text-[0.7rem] text-base-content/50 flex gap-1.5 flex-wrap mt-0.5">
        <span>{{ formatDate(episode.pubTs) }}</span>

      </div>
    </div>

    <button
      class="btn btn-sm btn-ghost text-base-content/40 hover:text-base-content/80 px-2 self-center flex-shrink-0 text-[1.2rem]"
      aria-label="Détails de l'épisode"
      @click.stop="emit('view', episode)"
    >›</button>
  </div>
</template>
