<script setup>
import { computed } from 'vue'
import { timeAgo } from '../lib/utils.js'

const props = defineProps({
  gameCount:     Number,
  filteredCount: Number,
  searchQuery:   String,
  sortMode:      String,
  sortAsc:       Boolean,
  loading:       Boolean,
  lastFetch:     String,
})
const emit = defineEmits(['update:searchQuery', 'setSort', 'refresh'])

const subtitle = computed(() => {
  const parts = []
  if (props.gameCount)  parts.push(`${props.gameCount} jeux`)
  if (props.lastFetch)  parts.push(`mis à jour ${timeAgo(props.lastFetch)}`)
  return parts.length ? parts.join(' · ') : 'Catalogue des jeux'
})

const sortOptions = [
  { mode: 'alpha', label: 'A–Z' },
  { mode: 'date',  label: 'Date' },
  { mode: 'meta',  label: 'Meta' },
]
</script>

<template>
  <header class="app-header">

    <!-- Row 1: branding + actions -->
    <div class="flex items-center justify-between gap-3 px-4 py-3 max-w-[1400px] mx-auto">
      <div class="flex items-center gap-2.5 leading-none">
        <span class="text-[1.6rem] lg:text-[1.8rem]">🎮</span>
        <div>
          <div class="text-[1.1rem] font-bold tracking-[-0.2px] leading-[1.2] lg:text-[1.25rem]">Silence on Joue</div>
          <div class="text-[0.7rem] text-base-content/50 mt-px">{{ subtitle }}</div>
        </div>
      </div>

      <div class="flex items-center gap-2 flex-shrink-0">
        <button
          class="btn btn-circle btn-ghost !size-9 !min-h-9 text-[1.1rem]"
          :disabled="loading"
          :aria-label="loading ? 'Chargement…' : 'Actualiser'"
          @click="emit('refresh')"
        >
          <span class="icon-spin" :class="{ spinning: loading }">↻</span>
        </button>
        <slot name="account" />
      </div>
    </div>

    <!-- Row 2: search + sort -->
    <div class="max-w-[1400px] mx-auto px-3 pb-2.5 flex flex-col gap-2 bg-base-100 flex-shrink-0 sm:flex-row sm:items-center sm:pb-3 sm:px-5 lg:px-7 lg:gap-3">
      <div class="relative w-full sm:flex-1 sm:max-w-[440px] lg:max-w-[520px]">
        <span class="absolute left-3 top-1/2 -translate-y-1/2 text-[0.9rem] pointer-events-none z-[1]">🔍</span>
        <input
          id="searchInput"
          type="search"
          placeholder="Rechercher un jeu…"
          :value="searchQuery"
          @input="emit('update:searchQuery', $event.target.value)"
        />
        <button
          v-if="searchQuery"
          class="btn-clear"
          aria-label="Effacer"
          @click="emit('update:searchQuery', '')"
        >✕</button>
      </div>

      <div class="flex gap-1.5 items-center sm:flex-none">
        <div class="join">
          <button
            v-for="opt in sortOptions"
            :key="opt.mode"
            class="join-item btn btn-sm"
            :class="sortMode === opt.mode ? 'btn-primary' : 'btn-ghost'"
            @click="emit('setSort', opt.mode)"
          >
            {{ opt.label }}
            <span v-if="sortMode === opt.mode">{{ sortAsc ? '↑' : '↓' }}</span>
          </button>
        </div>
        <span v-if="searchQuery" class="text-[0.8rem] text-base-content/50 pl-0.5">
          {{ filteredCount }} / {{ gameCount }}
        </span>
      </div>
    </div>

  </header>
</template>
