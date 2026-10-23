<script setup>
import { computed } from 'vue'
import { formatTime } from '../lib/utils.js'

// The episode cut into its segments (tests, else chapters): each one a block,
// the one playing taller, what's played in yellow. An invisible range input
// laid over the whole carries seeking and accessibility.
const props = defineProps({
  duration:    { type: Number, default: 0 },
  currentTime: { type: Number, default: 0 },
  marks:       { type: Array,  default: () => [] },   // [{ timestampSeconds, ... }], sorted
  showTime:    { type: Boolean, default: true },
  label:       { type: String, default: '' },          // centre caption (« X ▸ Y »)
})
const emit = defineEmits(['seek'])

const segments = computed(() => {
  const d = props.duration
  if (!(d > 0)) return [{ start: 0, end: 1, flex: 1, played: 0, current: true }]
  const starts = [0, ...props.marks.map(m => m.timestampSeconds).filter(t => t > 0 && t < d)]
  const uniq = [...new Set(starts)].sort((a, b) => a - b)
  return uniq.map((start, i) => {
    const end = uniq[i + 1] ?? d
    const played = Math.min(1, Math.max(0, (props.currentTime - start) / (end - start)))
    return { start, end, flex: end - start, played, current: props.currentTime >= start && props.currentTime < end }
  })
})

function onInput(e) { emit('seek', parseFloat(e.target.value)) }
</script>

<template>
  <div class="seek">
    <div class="seek__bar">
      <span
        v-for="s in segments"
        :key="s.start"
        class="seek__seg"
        :class="{ 'is-current': s.current }"
        :style="{ flexGrow: s.flex }"
      ><span :style="{ width: s.played * 100 + '%' }"></span></span>
      <input
        type="range"
        class="seek__input"
        min="0"
        :max="duration || 100"
        step="1"
        :value="currentTime"
        aria-label="Position"
        :aria-valuetext="`${formatTime(currentTime)} sur ${formatTime(duration)}`"
        @input="onInput"
      />
    </div>
    <div v-if="showTime" class="seek__times mono">
      <span>{{ formatTime(currentTime) }}</span>
      <span class="seek__label ellipsis">{{ label }}</span>
      <span>{{ formatTime(duration) }}</span>
    </div>
  </div>
</template>

<style scoped>
.seek { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.seek__bar { position: relative; display: flex; gap: 2px; align-items: flex-end; height: 18px; }
.seek__seg { position: relative; display: block; height: 8px; min-width: 2px; background: var(--c-line-strong); overflow: hidden; }
.seek__seg.is-current { height: 18px; }
.seek__seg > span { position: absolute; inset: 0 auto 0 0; background: var(--c-accent); }
.seek__input {
  position: absolute;
  inset: -8px 0;
  width: 100%;
  height: calc(100% + 16px);
  margin: 0;
  opacity: 0;
  cursor: pointer;
}
.seek__input:focus-visible { opacity: 0.01; }
.seek__bar:has(.seek__input:focus-visible) { outline: 2px solid var(--c-accent); outline-offset: 4px; }
.seek__times { display: flex; justify-content: space-between; gap: 12px; color: var(--c-fg-3); font-size: var(--text-xs); }
.seek__label { flex: 1; text-align: center; text-transform: uppercase; letter-spacing: 0.06em; }
</style>
