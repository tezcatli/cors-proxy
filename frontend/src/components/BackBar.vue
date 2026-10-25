<script setup>
import { useRouter } from 'vue-router'
import { ArrowLeft } from 'lucide-vue-next'
import { goHome } from '../lib/home.js'
import Wordmark from './Wordmark.vue'

// The top bar of an overlay page (game, episode, podcast), the same on every
// one: back one step on the left; on the right the page's own tools (`actions`
// slot), then LUDO//, home in one step (lib/home.js) — a real link, so a middle
// click still opens it.
defineProps({
  label: String,
})
const emit = defineEmits(['back'])

const router = useRouter()
function onHome(e) {
  if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
  e.preventDefault()
  goHome(router)
}
</script>

<template>
  <div class="backbar">
    <button type="button" class="backbar__back lab" @click="emit('back')">
      <ArrowLeft :size="16" :stroke-width="2" aria-hidden="true" />
      <span class="ellipsis">{{ label }}</span>
    </button>
    <div class="backbar__actions">
      <slot name="actions" />
      <a href="/" class="backbar__home" aria-label="Ludothèque, accueil" @click="onHome"><Wordmark /></a>
    </div>
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
.backbar__actions { display: flex; align-items: center; gap: 4px; }
.backbar__home {
  display: inline-flex;
  align-items: center;
  min-height: 44px;
  padding: 0 10px;
  font-size: 14px;
  text-decoration: none;
  transition: background var(--dur-fast);
}
.backbar__home:hover { background: var(--c-raised); }
</style>
