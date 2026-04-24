<script setup>
import { computed } from 'vue'
import { timeAgo } from '../lib/utils.js'

const props = defineProps({
  loggedIn:      Boolean,
  userEmail:     String,
  gameCount:     Number,
  filteredCount: Number,
  searchQuery:   String,
  sortMode:      String,
  sortAsc:       Boolean,
  loading:       Boolean,
  lastFetch:     String,
})
const emit = defineEmits([
  'update:searchQuery',
  'setSort',
  'refresh',
  'showLogin',
  'logout',
])

const lastFetchLabel = computed(() => timeAgo(props.lastFetch))

const sortOptions = [
  { mode: 'alpha', label: 'A–Z' },
  { mode: 'date',  label: 'Date' },
  { mode: 'meta',  label: 'Meta' },
]
</script>

<template>
  <header class="app-header">
    <div class="header-inner">
      <div class="header-brand">
        <span>🎮</span>
        <div>
          <div class="header-title">Silence on Joue</div>
          <div class="header-sub">Catalogue des jeux</div>
        </div>
      </div>

      <span v-if="gameCount" class="badge-count">{{ gameCount }}</span>

      <div class="header-actions">
        <button
          class="btn-icon"
          :disabled="loading"
          :aria-label="loading ? 'Chargement…' : 'Actualiser'"
          @click="emit('refresh')"
        >
          <span class="icon-spin" :class="{ spinning: loading }">↻</span>
        </button>

        <template v-if="loggedIn">
          <span v-if="userEmail" class="user-email">{{ userEmail }}</span>
          <button class="btn-icon" aria-label="Déconnexion" @click="emit('logout')">⎋</button>
        </template>
        <button v-else class="btn-icon" aria-label="Connexion" @click="emit('showLogin')">👤</button>
      </div>
    </div>

    <div v-if="lastFetch" class="header-meta">
      <span>Mis à jour {{ lastFetchLabel }}</span>
    </div>

    <div class="controls">
      <div class="search-wrap">
        <span class="search-icon">🔍</span>
        <input
          id="searchInput"
          type="search"
          class="search-input"
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

      <div class="sort-bar">
        <button
          v-for="opt in sortOptions"
          :key="opt.mode"
          class="sort-opt"
          :class="{ active: sortMode === opt.mode }"
          @click="emit('setSort', opt.mode)"
        >
          {{ opt.label }}
          <span v-if="sortMode === opt.mode" class="sort-dir">{{ sortAsc ? '↑' : '↓' }}</span>
        </button>
        <span v-if="searchQuery" class="filtered-count">
          {{ filteredCount }} / {{ gameCount }}
        </span>
      </div>
    </div>
  </header>
</template>
