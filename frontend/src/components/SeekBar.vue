<script setup>
import { computed } from 'vue'
import { formatTime } from '../lib/utils.js'

// Layered seek bar (track < fill < chapter markers < thumb < invisible range
// input). Rendered for both the mobile and desktop player rows. The .seek-*
// styles live in components.css.
const props = defineProps({
  progress:    { type: Number, default: 0 },   // played %, 0–100
  duration:    { type: Number, default: 0 },
  chapters:    { type: Array,  default: () => [] },
  currentTime: { type: Number, default: 0 },
  showTime:    { type: Boolean, default: true },  // elapsed / remaining labels
})
const emit = defineEmits(['seek'])
function onInput(e) { emit('seek', parseFloat(e.target.value)) }

const elapsedLabel   = computed(() => formatTime(props.currentTime))
const remainingLabel = computed(() =>
  props.duration > 0 ? '-' + formatTime(props.duration - props.currentTime) : formatTime(0)
)
</script>

<template>
  <div class="seek">
    <div class="seek-wrap">
      <div class="seek-track">
        <div class="seek-fill" :style="{ width: progress + '%' }"></div>
        <span
          v-for="ch in chapters"
          :key="ch.timestampSeconds"
          class="seek-marker"
          :style="{ left: (ch.timestampSeconds / (duration || 1) * 100) + '%' }"
        />
      </div>
      <div class="seek-thumb" :style="{ left: progress + '%' }"></div>
      <input
        type="range" class="seek-input"
        min="0" :max="duration || 100"
        :value="currentTime"
        @input="onInput"
        aria-label="Position"
      />
    </div>
    <div v-if="showTime" class="seek-times">
      <span>{{ elapsedLabel }}</span>
      <span>{{ remainingLabel }}</span>
    </div>
  </div>
</template>
