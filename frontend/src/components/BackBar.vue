<script setup>
import { ArrowLeft } from 'lucide-vue-next'

// The top bar of an overlay page (game, episode): back on the left, the page's
// own tools in the `actions` slot on the right. `overlay` floats it over a
// band of art (no fill, no rule) until `solid` says the page scrolled past it.
defineProps({
  label:   String,
  overlay: Boolean,
  solid:   Boolean,
})
const emit = defineEmits(['back'])
</script>

<template>
  <div class="backbar" :class="{ 'backbar--overlay': overlay, 'is-solid': solid }">
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
  transition: background var(--dur-fast), border-color var(--dur-fast);
}
.backbar--overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  z-index: 10;
  background: transparent;
  border-bottom-color: transparent;
}
.backbar--overlay.is-solid { background: var(--c-bg); border-bottom-color: var(--c-line); }
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
/* Over art, the label sits on a black chip so it reads on any image. */
.backbar--overlay:not(.is-solid) .backbar__back,
.backbar--overlay:not(.is-solid) .backbar__actions :deep(.icon-action) { background: rgba(11, 11, 11, 0.72); }
.backbar__actions { display: flex; align-items: center; gap: 4px; }
</style>
