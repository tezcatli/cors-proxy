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
  <span v-if="meta" class="podcast-badge" :class="{ 'podcast-badge--full': full }" :title="meta.name">{{ full ? meta.name : meta.label }}</span>
</template>

<style scoped>
.podcast-badge {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--c-fg-2);
  white-space: nowrap;
}
.podcast-badge--full { font-family: var(--font-body); font-size: var(--text-md); font-weight: 600; letter-spacing: 0; text-transform: none; color: var(--c-fg); }
</style>
