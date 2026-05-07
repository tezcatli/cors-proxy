<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
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
watch(() => route.query.q, q => { if (route.path === '/') searchQuery.value = q || '' })

// Auto-load catalog when navigating to / after login (onMounted only fires once)
watch(() => route.path, path => {
  if (path === '/' && loggedIn.value && !gamesStore.all.length && !gamesStore.loading)
    gamesStore.load()
})

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

const hideUnresolved = ref(false)

const displayedGames = computed(() => {
  let games = gamesStore.filtered(searchQuery.value.trim())
  if (hideUnresolved.value) games = games.filter(g => g.igdb !== null)
  return games
})

// Body classes for layout context
watch(() => playerStore.visible, v => {
  document.body.classList.toggle('player-open', v)
})
watch(() => route.path, p => {
  document.body.classList.toggle('detail-open', p.startsWith('/game/'))
}, { immediate: true })

function handleLogout() {
  showAccountModal.value = false
  logout()
  router.push('/login')
}

function handleRefresh() { gamesStore.refresh() }

// ── Pull-to-refresh ───────────────────────────────────────────────────────────
const PULL_THRESHOLD = 80
let   _startY   = 0
let   _active   = false
let   _gridEl   = null
const pullY     = ref(0)
const isPulling = ref(false)

function onTouchStart(e) {
  if (_gridEl && _gridEl.scrollTop > 0) return
  _startY = e.touches[0].clientY
  _active = true
}

function onTouchMove(e) {
  if (!_active) return
  const dy = e.touches[0].clientY - _startY
  if (dy <= 0 || (_gridEl && _gridEl.scrollTop > 0)) { _active = false; return }
  e.preventDefault()
  pullY.value     = Math.min(dy, PULL_THRESHOLD * 1.5)
  isPulling.value = true
}

function onTouchEnd() {
  if (!_active) return
  const triggered = pullY.value >= PULL_THRESHOLD
  _active         = false
  isPulling.value = false
  pullY.value     = 0
  if (triggered) handleRefresh()
}

onMounted(() => {
  if (loggedIn.value) gamesStore.load()
  _gridEl = document.querySelector('.grid-area')
  window.addEventListener('touchmove', onTouchMove, { passive: false })
})

onBeforeUnmount(() => {
  window.removeEventListener('touchmove', onTouchMove)
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
      :hide-unresolved="hideUnresolved"
      @update:searchQuery="searchQuery = $event"
      @set-sort="gamesStore.setSort"
      @refresh="handleRefresh"
      @toggle-hide-unresolved="hideUnresolved = !hideUnresolved"
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

    <!-- Pull-to-refresh indicator -->
    <div
      class="flex justify-center items-center overflow-hidden"
      :style="{
        height: isPulling ? pullY + 'px' : '0px',
        transition: isPulling ? 'none' : 'height 0.2s ease',
      }"
    >
      <span
        class="loading loading-spinner text-primary loading-sm"
        :style="{ opacity: Math.min(pullY / PULL_THRESHOLD, 1) }"
      />
    </div>

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
