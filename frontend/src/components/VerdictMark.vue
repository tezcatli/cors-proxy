<script setup>
import { computed } from 'vue'
import { verdictMeta } from '../lib/verdicts.js'

// A test's verdict as glyph + word (`full`), or the glyph alone for tight rows
// (the word stays as the accessible name).
const props = defineProps({
  verdict: { type: String, default: null },
  full:    { type: Boolean, default: true },
})
const meta = computed(() => verdictMeta(props.verdict))
</script>

<template>
  <span class="verdict" :class="{ 'verdict--none': !verdict }" :title="meta.label">
    <span aria-hidden="true">{{ meta.glyph }}</span>
    <span v-if="full">{{ meta.label }}</span>
    <span v-else class="sr-only">{{ meta.label }}</span>
  </span>
</template>

<style scoped>
.verdict {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--c-fg);
  white-space: nowrap;
}
.verdict--none { color: var(--c-fg-3); font-weight: 500; }
</style>
