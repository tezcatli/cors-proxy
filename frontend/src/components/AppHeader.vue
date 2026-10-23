<script setup>
import { computed, ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { RouterLink } from 'vue-router'
import { Search, X, ArrowUp, ArrowDown, ArrowUpDown, User } from 'lucide-vue-next'
import { PODCASTS } from '../lib/podcasts.js'
import { isAdmin } from '../lib/auth.js'

const props = defineProps({
  searchQuery:     String,
  sortMode:        String,
  sortAsc:         Boolean,
  hideUnresolved:  Boolean,
  selectedPodcast: String,
  isJeux:          Boolean,
})
const emit = defineEmits(['update:searchQuery', 'setSort', 'setPodcast', 'toggle-hide-unresolved', 'show-account'])

const admin = isAdmin()

const podcastOptions = [{ id: 'all', label: 'Tous' }, ...PODCASTS.map(p => ({ id: p.id, label: p.name }))]

const searchPlaceholder = computed(() =>
  props.isJeux ? 'Rechercher un jeu' : 'Rechercher un test, un épisode'
)

const sortOptions = [
  { mode: 'date',  label: 'Récents' },
  { mode: 'alpha', label: 'A–Z' },
  { mode: 'meta',  label: 'Metacritic' },
]

// ── Sort popover (Jeux only) ────────────────────────────────────────────────
const popoverOpen = ref(false)
const popoverRoot = ref(null)
function onDocClick(e) {
  if (popoverOpen.value && popoverRoot.value && !popoverRoot.value.contains(e.target)) popoverOpen.value = false
}
function onEsc(e) { if (e.key === 'Escape') { popoverOpen.value = false; searchOpen.value = false } }
onMounted(() => {
  document.addEventListener('click', onDocClick)
  document.addEventListener('keydown', onEsc)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('keydown', onEsc)
})

// ── Mobile search overlay ───────────────────────────────────────────
const searchOpen  = ref(false)
const overlayInput = ref(null)
async function openSearch() {
  searchOpen.value = true
  await nextTick()
  overlayInput.value?.focus()
}
</script>

<template>
  <header class="topbar">
    <div class="topbar__row">
      <RouterLink to="/" class="wordmark cond" aria-label="Ludothèque, accueil">Ludo<span>//</span></RouterLink>

      <nav class="topbar__nav" aria-label="Sections">
        <RouterLink to="/" class="lab topbar__tab" :class="{ 'is-on': !isJeux }">Tests</RouterLink>
        <RouterLink to="/jeux" class="lab topbar__tab" :class="{ 'is-on': isJeux }">Jeux</RouterLink>
      </nav>

      <div class="topbar__spacer" />

      <label class="search">
        <Search :size="16" :stroke-width="2" aria-hidden="true" />
        <input
          class="search__input"
          type="search"
          :placeholder="searchPlaceholder"
          :aria-label="searchPlaceholder"
          :value="searchQuery"
          @input="emit('update:searchQuery', $event.target.value)"
        />
        <button v-if="searchQuery" type="button" class="search__clear" aria-label="Effacer la recherche" @click="emit('update:searchQuery', '')">
          <X :size="14" :stroke-width="2.25" />
        </button>
      </label>

      <button type="button" class="icon-action mobile-only" :class="{ 'is-active': !!searchQuery }" aria-label="Rechercher" @click="openSearch">
        <Search :size="18" :stroke-width="2" />
        <span v-if="searchQuery" class="icon-action__dot"></span>
      </button>

      <div v-if="isJeux" ref="popoverRoot" class="sort">
        <button
          type="button"
          class="icon-action"
          :class="{ 'is-active': popoverOpen }"
          aria-label="Trier"
          :aria-expanded="popoverOpen"
          @click="popoverOpen = !popoverOpen"
        ><ArrowUpDown :size="18" :stroke-width="2" /></button>

        <div v-if="popoverOpen" class="sort__menu panel" role="menu" aria-label="Trier">
          <div class="lab sort__title">Trier par</div>
          <button
            v-for="opt in sortOptions"
            :key="opt.mode"
            type="button"
            role="menuitemradio"
            :aria-checked="sortMode === opt.mode"
            class="sort__row"
            :class="{ 'is-on': sortMode === opt.mode }"
            @click="emit('setSort', opt.mode)"
          >
            <span>{{ opt.label }}</span>
            <component v-if="sortMode === opt.mode" :is="sortAsc ? ArrowUp : ArrowDown" :size="14" :stroke-width="2.25" />
          </button>
          <template v-if="admin">
            <div class="lab sort__title">Admin</div>
            <button type="button" role="menuitemcheckbox" :aria-checked="!hideUnresolved" class="sort__row" :class="{ 'is-on': !hideUnresolved }" @click="emit('toggle-hide-unresolved')">
              <span>Jeux sans fiche</span><span class="mono">{{ hideUnresolved ? 'OFF' : 'ON' }}</span>
            </button>
          </template>
        </div>
      </div>

      <button type="button" class="icon-action desktop-only" aria-label="Mon compte" @click="emit('show-account')">
        <User :size="18" :stroke-width="2" />
      </button>
    </div>

    <div class="chips" role="group" aria-label="Émission">
      <button
        v-for="opt in podcastOptions"
        :key="opt.id"
        type="button"
        class="chip-btn"
        :class="{ 'is-on': selectedPodcast === opt.id }"
        :aria-pressed="selectedPodcast === opt.id"
        @click="emit('setPodcast', opt.id)"
      >{{ opt.label }}</button>
    </div>

    <div v-if="searchOpen" class="search-overlay">
      <label class="search search--overlay">
        <Search :size="18" :stroke-width="2" aria-hidden="true" />
        <input
          ref="overlayInput"
          class="search__input"
          type="search"
          :placeholder="searchPlaceholder"
          :aria-label="searchPlaceholder"
          :value="searchQuery"
          @input="emit('update:searchQuery', $event.target.value)"
          @keydown.enter="searchOpen = false"
        />
      </label>
      <button type="button" class="icon-action" aria-label="Fermer la recherche" @click="searchOpen = false">
        <X :size="18" :stroke-width="2" />
      </button>
    </div>
  </header>
</template>

<style scoped>
.topbar {
  position: relative;
  flex-shrink: 0;
  background: var(--c-bg);
  border-bottom: 1px solid var(--c-line);
  padding-top: env(safe-area-inset-top, 0px);
  z-index: 20;
}
.topbar__row {
  display: flex;
  align-items: center;
  gap: 4px;
  height: var(--topbar-h);
  padding: 0 calc(var(--gutter) - 8px) 0 var(--gutter);
}
.wordmark {
  font-weight: 800;
  font-size: 26px;
  color: var(--c-fg);
  text-decoration: none;
  margin-right: 24px;
}
.wordmark span { color: var(--c-accent); }
.topbar__nav { display: none; gap: 4px; }
.topbar__tab {
  display: inline-flex;
  align-items: center;
  min-height: 44px;
  padding: 0 12px;
  text-decoration: none;
  color: var(--c-fg-3);
}
.topbar__tab:hover { color: var(--c-fg); }
.topbar__tab.is-on { color: var(--c-fg); box-shadow: inset 0 -2px 0 var(--c-accent); }
.topbar__spacer { flex: 1; }

.search {
  display: none;
  align-items: center;
  gap: 10px;
  height: 40px;
  padding: 0 12px;
  width: 320px;
  box-shadow: inset 0 0 0 1px var(--c-line-strong);
  color: var(--c-fg-3);
  margin-right: 8px;
}
.search:focus-within { box-shadow: inset 0 0 0 2px var(--c-accent); }
.search__input {
  flex: 1;
  min-width: 0;
  background: transparent;
  border: 0;
  outline: 0;
  color: var(--c-fg);
  font-family: var(--font-body);
  font-size: var(--text-md);
}
.search__input::placeholder { color: var(--c-fg-3); }
.search__clear { display: inline-flex; border: 0; background: transparent; color: var(--c-fg-3); cursor: pointer; padding: 4px; }
.search__clear:hover { color: var(--c-fg); }

.sort { position: relative; }
.sort__menu {
  position: absolute;
  right: 0;
  top: calc(100% + 4px);
  width: 240px;
  padding: 8px;
  background: var(--c-surface);
  z-index: 40;
}
.sort__title { padding: 8px 8px 4px; }
.sort__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  min-height: 44px;
  padding: 0 8px;
  border: 0;
  background: transparent;
  color: var(--c-fg-2);
  font-family: var(--font-body);
  font-size: var(--text-md);
  cursor: pointer;
  text-align: left;
}
.sort__row:hover { background: var(--c-raised); color: var(--c-fg); }
.sort__row.is-on { color: var(--c-fg); box-shadow: inset 2px 0 0 var(--c-accent); }

.chips {
  display: flex;
  gap: 6px;
  padding: 0 var(--gutter) 12px;
  overflow-x: auto;
  scrollbar-width: none;
}
.chips::-webkit-scrollbar { display: none; }

.search-overlay {
  position: absolute;
  inset: 0 0 auto 0;
  height: calc(var(--topbar-h) + env(safe-area-inset-top, 0px));
  padding: env(safe-area-inset-top, 0px) 8px 0 var(--gutter);
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--c-bg);
  border-bottom: 1px solid var(--c-line);
  z-index: 50;
}
.search--overlay { display: flex; flex: 1; width: auto; margin: 0; }

.desktop-only { display: none; }
@media (min-width: 768px) {
  .topbar__nav { display: flex; }
  .search { display: flex; }
  .mobile-only, .search-overlay { display: none; }
  .desktop-only { display: inline-flex; }
}
</style>
