<script setup>
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import { RouterLink } from 'vue-router'
import { Search, RotateCw, X, ArrowUp, ArrowDown, SlidersHorizontal, Check } from 'lucide-vue-next'
import { timeAgo } from '../lib/utils.js'

const props = defineProps({
  searchQuery:    String,
  sortMode:       String,
  sortAsc:        Boolean,
  loading:        Boolean,
  resolving:      Boolean,
  lastFetch:      String,
  hideUnresolved: Boolean,
  isEpisodes:     Boolean,
})
const emit = defineEmits(['update:searchQuery', 'setSort', 'refresh', 'toggle-hide-unresolved'])

const searchPlaceholder = computed(() =>
  props.isEpisodes ? 'Rechercher un épisode…' : 'Rechercher un jeu…'
)

const sortOptions = [
  { mode: 'alpha', label: 'A–Z',          hint: 'Alphabétique' },
  { mode: 'date',  label: 'Date',         hint: 'Date de l\'épisode' },
  { mode: 'meta',  label: 'Metacritic',   hint: 'Note Metacritic' },
]

const lastFetchLabel = computed(() => props.lastFetch ? timeAgo(props.lastFetch) : null)
const filtersActive  = computed(() => props.hideUnresolved || props.sortMode !== 'alpha' || !props.sortAsc)

// ── Filters popover ─────────────────────────────────────────────────
const popoverOpen = ref(false)
const popoverRoot = ref(null)
function togglePopover() { popoverOpen.value = !popoverOpen.value }
function closePopover()  { popoverOpen.value = false }
// Outside-click handler runs in CAPTURE phase so we can swallow the click
// before it reaches whatever's under the cursor (e.g. a game tile in the grid).
function onDocClick(e) {
  if (!popoverOpen.value) return
  if (popoverRoot.value && popoverRoot.value.contains(e.target)) return
  closePopover()
  e.stopPropagation()
  e.preventDefault()
}
function onEsc(e) { if (e.key === 'Escape') closePopover() }
onMounted(() => {
  document.addEventListener('click', onDocClick, true)
  document.addEventListener('keydown', onEsc)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick, true)
  document.removeEventListener('keydown', onEsc)
})

// ── Mobile search overlay ───────────────────────────────────────────
const searchOpen = ref(false)
function openSearch()  { searchOpen.value = true }
function closeSearch() { searchOpen.value = false }
</script>

<template>
  <header class="command-bar">
    <div class="command-bar__inner">
      <!-- Tab pills -->
      <nav class="tab-group" aria-label="Sections">
        <RouterLink to="/" class="tab-pill" :class="{ 'is-active': !isEpisodes }">
          <span>Jeux</span>
        </RouterLink>
        <RouterLink to="/episodes" class="tab-pill" :class="{ 'is-active': isEpisodes }">
          <span>Épisodes</span>
        </RouterLink>
      </nav>

      <!-- Search (always visible on tablet+, behind icon on mobile) -->
      <div class="search-wrap">
        <Search :size="16" class="search-wrap__icon" />
        <input
          id="searchInput"
          class="search-input"
          type="search"
          :placeholder="searchPlaceholder"
          :value="searchQuery"
          @input="emit('update:searchQuery', $event.target.value)"
        />
        <button
          v-if="searchQuery"
          class="search-wrap__clear"
          aria-label="Effacer la recherche"
          @click="emit('update:searchQuery', '')"
        ><X :size="12" :stroke-width="2.5" /></button>
      </div>

      <!-- Mobile search trigger -->
      <button
        class="icon-action mobile-only"
        :class="{ 'is-active': !!searchQuery }"
        aria-label="Rechercher"
        @click="openSearch"
      >
        <Search :size="17" :stroke-width="2.25" />
        <span v-if="searchQuery" class="icon-action__dot"></span>
      </button>

      <!-- Sort/filter popover (Jeux only) -->
      <div v-if="!isEpisodes" ref="popoverRoot" class="popover-wrap">
        <button
          class="icon-action"
          :class="{ 'is-active': popoverOpen || filtersActive }"
          aria-label="Trier et filtrer"
          :aria-expanded="popoverOpen"
          @click="togglePopover"
        >
          <SlidersHorizontal :size="17" :stroke-width="2.25" />
          <span v-if="filtersActive" class="icon-action__dot"></span>
        </button>

        <Transition name="popover">
          <div v-if="popoverOpen" class="popover" role="dialog" aria-label="Trier et filtrer">
            <div class="popover__title">Trier par</div>
            <div class="flex flex-col gap-1 mb-3">
              <button
                v-for="opt in sortOptions"
                :key="opt.mode"
                class="popover__row"
                :class="{ 'is-active': sortMode === opt.mode }"
                @click="emit('setSort', opt.mode)"
              >
                <span class="popover__row-label">
                  <Check v-if="sortMode === opt.mode" :size="14" :stroke-width="2.5" class="popover__check" />
                  {{ opt.label }}
                </span>
                <component
                  v-if="sortMode === opt.mode"
                  :is="sortAsc ? ArrowUp : ArrowDown"
                  :size="13"
                  :stroke-width="2.5"
                  class="popover__dir"
                />
              </button>
            </div>

            <div class="popover__divider"></div>

            <div class="popover__title">Filtres</div>
            <button
              class="popover__row"
              :class="{ 'is-active': hideUnresolved }"
              @click="emit('toggle-hide-unresolved')"
            >
              <span class="popover__row-label">
                <span class="popover__toggle" :class="{ 'is-on': hideUnresolved }">
                  <span class="popover__toggle-knob" />
                </span>
                Jeux résolus uniquement
              </span>
            </button>
          </div>
        </Transition>
      </div>

      <!-- Spacer pushes refresh + account to the right -->
      <div class="flex-1" aria-hidden="true"></div>

      <!-- Refresh -->
      <button
        class="icon-action"
        :disabled="loading || resolving"
        :aria-label="loading ? 'Chargement…' : resolving ? 'Résolution IGDB en cours…' : (lastFetchLabel ? `Actualiser (mis à jour ${lastFetchLabel})` : 'Actualiser')"
        :title="resolving ? 'Résolution IGDB en cours…' : (lastFetchLabel ? `Mis à jour ${lastFetchLabel}` : 'Actualiser')"
        @click="emit('refresh')"
      >
        <RotateCw :size="17" :stroke-width="2.25" :class="{ 'animate-spin': loading || resolving }" />
      </button>

      <!-- Account slot -->
      <slot name="account" />
    </div>

    <!-- Mobile search overlay -->
    <Transition name="search-overlay">
      <div v-if="searchOpen" class="search-overlay" @click.self="closeSearch">
        <div class="search-overlay__bar">
          <Search :size="18" :stroke-width="2.25" class="text-white/55" />
          <input
            class="search-overlay__input"
            type="search"
            autofocus
            :placeholder="searchPlaceholder"
            :value="searchQuery"
            @input="emit('update:searchQuery', $event.target.value)"
            @keydown.enter="closeSearch"
          />
          <button class="icon-action" aria-label="Fermer" @click="closeSearch">
            <X :size="18" :stroke-width="2.25" />
          </button>
        </div>
      </div>
    </Transition>
  </header>
</template>
