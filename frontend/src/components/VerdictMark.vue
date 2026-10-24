<script setup>
import { computed } from 'vue'
import { verdictMeta } from '../lib/verdicts.js'

// A test's verdict, its word alone; nothing when the test has none.
const props = defineProps({
  verdict: { type: String, default: null },
})
const meta = computed(() => verdictMeta(props.verdict))
</script>

<template>
  <span v-if="meta" class="verdict">{{ meta.label }}</span>
</template>

<style scoped>
.verdict {
  display: inline-flex;
  align-items: center;
  font-family: var(--font-display);
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--c-fg);
  white-space: nowrap;
}
</style>
