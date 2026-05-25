<script setup>
import { computed, ref, watch, onUnmounted, nextTick } from 'vue'
import { Play, Pause, VolumeX, ChevronRight } from 'lucide-vue-next'
import { formatDate } from '../lib/utils.js'

const props = defineProps({
  episode:   Object,
  isPlaying: Boolean,
  isPaused:  Boolean,
})
const emit = defineEmits(['play', 'togglePause', 'view'])

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
    <div class="ep-icon" @click="handlePlay">
      <component :is="iconComp" :size="14" :fill="hasAudio ? 'currentColor' : 'none'" :stroke-width="hasAudio ? 0 : 2" />
    </div>

    <img
      v-if="episode.imageUrl"
      :src="episode.imageUrl"
      :alt="episode.title"
      class="w-10 h-10 rounded-lg object-cover flex-shrink-0 self-center shadow-e1"
      loading="lazy"
      @click="handlePlay"
    />
    <div v-else class="w-10 h-10 flex-shrink-0 rounded-lg bg-white/5" />

    <div class="flex-1 min-w-0" @click="handlePlay">
      <div
        ref="marqueeEl"
        class="ep-title-scroll"
        :class="{ 'ep-title-scroll--on': needsScroll }"
      >
        <span class="ep-title-inner">{{ episode.title }}</span>
        <span v-if="needsScroll" class="ep-title-inner" aria-hidden="true">{{ episode.title }}</span>
      </div>
      <div class="text-[0.7rem] text-white/45 flex gap-1.5 flex-wrap mt-0.5 font-medium">
        <span>{{ formatDate(episode.pubTs) }}</span>
      </div>
    </div>

    <button
      class="btn btn-sm btn-ghost text-white/40 hover:text-white/85 px-2 self-center flex-shrink-0 !min-h-0 h-8"
      aria-label="Détails de l'épisode"
      @click.stop="emit('view', episode)"
    ><ChevronRight :size="18" :stroke-width="2" /></button>
  </div>
</template>
