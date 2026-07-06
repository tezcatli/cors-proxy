<script setup>
import { computed } from 'vue'
import { podcastMeta } from '../lib/podcasts.js'

const props = defineProps({
  id:   String,
  full: Boolean,   // show the full name instead of the short label
})

const meta = computed(() => podcastMeta(props.id))
</script>

<template>
  <span
    v-if="meta"
    class="podcast-badge"
    :style="{ color: meta.color, backgroundColor: meta.color + '22', borderColor: meta.color + '55' }"
    :title="meta.name"
  >{{ full ? meta.name : meta.label }}</span>
</template>

<style scoped>
.podcast-badge {
  display: inline-flex;
  align-items: center;
  border: 1px solid transparent;
  border-radius: 0.35rem;
  padding: 0 0.3rem;
  font-size: 0.6rem;
  font-weight: 700;
  line-height: 1.35;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  white-space: nowrap;
}
</style>
