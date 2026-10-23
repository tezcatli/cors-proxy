<script setup>
import { ArrowLeft } from 'lucide-vue-next'

// The top bar of an overlay page (game, episode): back on the left, the page's
// own tools in the `actions` slot on the right.
defineProps({ label: String })
const emit = defineEmits(['back'])
</script>

<template>
  <div class="backbar">
    <button type="button" class="backbar__back lab" @click="emit('back')">
      <ArrowLeft :size="16" :stroke-width="2" aria-hidden="true" />
      <span class="ellipsis">{{ label }}</span>
    </button>
    <div class="backbar__actions"><slot name="actions" /></div>
  </div>
</template>

<style scoped>
.backbar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  height: var(--topbar-h);
  padding: env(safe-area-inset-top, 0px) calc(var(--gutter) - 8px) 0 calc(var(--gutter) - 12px);
  box-sizing: content-box;
  background: var(--c-bg);
  border-bottom: 1px solid var(--c-line);
}
.backbar__back {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 44px;
  max-width: 70vw;
  padding: 0 12px;
  border: 0;
  background: transparent;
  color: var(--c-fg);
  cursor: pointer;
}
.backbar__back:hover { background: var(--c-raised); }
.backbar__actions { display: flex; align-items: center; }
</style>
