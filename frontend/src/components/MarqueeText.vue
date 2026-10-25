<script setup>
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'

// A one-line title that scrolls when it doesn't fit (DECISIONS.md, « Interface »):
// the player's only — one title on one line; never a list's. It rests at its
// start, slides slowly to its end, rests, and comes back. Reduced motion: an
// ellipsis instead.
const props = defineProps({ text: { type: String, default: '' } })

const SPEED = 30   // px per second
const REST  = 1.5  // s at each end

const box   = ref(null)
const inner = ref(null)
const shift = ref(0)
let observer = null

function measure() {
  if (!box.value || !inner.value) return
  const over = inner.value.scrollWidth - box.value.clientWidth
  shift.value = over > 4 ? over : 0
}

onMounted(() => {
  measure()
  if (typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(measure)
    observer.observe(box.value)
  }
})
onBeforeUnmount(() => observer?.disconnect())
watch(() => props.text, () => { shift.value = 0; nextTick(measure) })
</script>

<template>
  <span ref="box" class="marquee" :class="{ 'is-moving': shift }" :title="text">
    <span
      ref="inner"
      class="marquee__text"
      :style="shift ? { '--shift': `-${shift}px`, '--dur': `${(shift / SPEED + REST * 2) * 2}s` } : null"
    >{{ text }}</span>
  </span>
</template>

<style scoped>
.marquee { display: block; overflow: hidden; white-space: nowrap; min-width: 0; }
.marquee__text { display: inline-block; }
.is-moving .marquee__text { animation: marquee var(--dur) ease-in-out infinite; }
@keyframes marquee {
  0%, 15%   { transform: translateX(0); }
  50%, 65%  { transform: translateX(var(--shift)); }
  100%      { transform: translateX(0); }
}
@media (prefers-reduced-motion: reduce) {
  .is-moving .marquee__text { animation: none; }
  .marquee__text { display: block; overflow: hidden; text-overflow: ellipsis; }
}
</style>
