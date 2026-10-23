<script setup>
import { RouterLink } from 'vue-router'
import { ListMusic, LayoutGrid, User } from 'lucide-vue-next'

// Mobile only: the sections within thumb reach, the mini player just above.
defineProps({ isJeux: Boolean })
const emit = defineEmits(['show-account'])
</script>

<template>
  <nav class="tabbar" aria-label="Sections">
    <RouterLink to="/" class="tabbar__tab lab" :class="{ 'is-on': !isJeux }">
      <ListMusic :size="20" :stroke-width="2" aria-hidden="true" />Tests
    </RouterLink>
    <RouterLink to="/jeux" class="tabbar__tab lab" :class="{ 'is-on': isJeux }">
      <LayoutGrid :size="20" :stroke-width="2" aria-hidden="true" />Jeux
    </RouterLink>
    <button type="button" class="tabbar__tab lab" @click="emit('show-account')">
      <User :size="20" :stroke-width="2" aria-hidden="true" />Compte
    </button>
  </nav>
</template>

<style scoped>
.tabbar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: var(--z-tabbar);
  display: flex;
  background: var(--c-bg);
  border-top: 1px solid var(--c-line);
  padding-bottom: env(safe-area-inset-bottom, 0px);
}
.tabbar__tab {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  height: var(--tabbar-h);
  border: 0;
  background: transparent;
  text-decoration: none;
  color: var(--c-fg-3);
  cursor: pointer;
}
.tabbar__tab.is-on { color: var(--c-fg); box-shadow: inset 0 2px 0 var(--c-accent); }
@media (min-width: 768px) { .tabbar { display: none; } }
</style>
