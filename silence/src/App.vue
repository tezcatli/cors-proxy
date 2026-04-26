<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { isLoggedIn, getUserEmail, logout } from './lib/auth.js'
import { useGamesStore } from './stores/games.js'
import { usePlayerStore } from './stores/player.js'
import AppHeader    from './components/AppHeader.vue'
import GameGrid     from './components/GameGrid.vue'
import AudioPlayer  from './components/AudioPlayer.vue'
import AccountModal from './components/AccountModal.vue'

const route  = useRoute()
const router = useRouter()

const gamesStore  = useGamesStore()
const playerStore = usePlayerStore()

const loggedIn  = computed(() => isLoggedIn())
const userEmail = computed(() => getUserEmail())

const showAccountModal = ref(false)

function handleShowAccount() {
  showAccountModal.value = true
}

// ── Search (Phase 4) ──────────────────────────────────────────────────────
const searchQuery = ref(route.query.q || '')

// URL → input (back/forward)
watch(() => route.query.q, q => { searchQuery.value = q || '' })

// Input → URL (debounced, only while on the grid)
let searchTimer
watch(searchQuery, q => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    if (route.path === '/' || route.path === '') {
      router.replace({ query: q ? { q } : {} })
    }
  }, 350)
})

const displayedGames = computed(() => gamesStore.filtered(searchQuery.value.trim()))

// Body class for audio player padding
watch(() => playerStore.visible, v => {
  document.body.classList.toggle('player-open', v)
})

function handleLogout() {
  showAccountModal.value = false
  logout()
  router.push('/login')
}

function handleRefresh() { gamesStore.load() }

onMounted(() => {
  if (loggedIn.value) gamesStore.load()
})
</script>

<template>
  <div id="mainView">
    <AppHeader
      :game-count="gamesStore.all.length"
      :filtered-count="displayedGames.length"
      :search-query="searchQuery"
      :sort-mode="gamesStore.sortMode"
      :sort-asc="gamesStore.sortAsc"
      :loading="gamesStore.loading"
      :last-fetch="gamesStore.lastFetch"
      @update:searchQuery="searchQuery = $event"
      @set-sort="gamesStore.setSort"
      @refresh="handleRefresh"
    >
      <template #account>
        <button
          class="btn btn-circle btn-ghost !size-9 !min-h-9 text-[1.1rem]"
          :class="loggedIn ? 'text-primary' : 'text-base-content/50'"
          :aria-label="loggedIn ? 'Mon compte' : 'Connexion'"
          @click="handleShowAccount"
        >👤</button>
      </template>
    </AppHeader>

    <GameGrid
      :games="displayedGames"
      :loading="gamesStore.loading"
      :error="gamesStore.error"
      :total="gamesStore.all.length"
    />

    <!-- Detail view and login page slide/fade in over the grid -->
    <RouterView v-slot="{ Component }">
      <Transition name="slide-right">
        <component :is="Component" v-if="Component" :key="route.path" />
      </Transition>
    </RouterView>

    <AudioPlayer />

    <AccountModal
      v-if="showAccountModal"
      :user-email="userEmail"
      @close="showAccountModal = false"
      @logout="handleLogout"
    />
  </div>
</template>
