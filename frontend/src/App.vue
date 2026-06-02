<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { loggedIn, getUserEmail, logout, refresh } from './lib/auth.js'
import { useGamesStore } from './stores/games.js'
import { usePlayerStore } from './stores/player.js'
import { useNavDirection } from './composables/useNavDirection.js'
import { usePullToRefresh } from './composables/usePullToRefresh.js'
import AppHeader    from './components/AppHeader.vue'
import GameGrid     from './components/GameGrid.vue'
import EpisodesFeed from './components/EpisodesFeed.vue'
import AudioPlayer  from './components/AudioPlayer.vue'
import AccountModal from './components/AccountModal.vue'
import { User } from 'lucide-vue-next'

const route  = useRoute()
const router = useRouter()

const gamesStore  = useGamesStore()
const playerStore = usePlayerStore()

const userEmail = computed(() => getUserEmail())

const { navDir } = useNavDirection(route, router)

const showAccountModal = ref(false)

function handleShowAccount() {
  showAccountModal.value = true
}

// ── Base route (only / or /episodes) ─────────────────────────────────────────
// Overlay routes (/game/:slug, /episode/:slug, /login) must NOT update this,
// so the background view stays visible during the slide-in transition.
const BASE_ROUTES = new Set(['/', '/episodes'])
const baseRoute   = ref(BASE_ROUTES.has(route.path) ? route.path : '/')

watch(() => route.path, path => {
  if (BASE_ROUTES.has(path)) baseRoute.value = path
})

// ── Search ────────────────────────────────────────────────────────────────────
const searchQuery         = ref(route.query.q || '')
const episodesSearchQuery = ref('')

const isEpisodes = computed(() => baseRoute.value === '/episodes')

// Mount the episodes feed only once the Épisodes tab is first opened, then keep
// it mounted — avoids fetching the (large) feed for grid-only sessions.
const episodesVisited = ref(false)
watch(isEpisodes, v => { if (v) episodesVisited.value = true }, { immediate: true })

const activeSearchQuery = computed(() =>
  isEpisodes.value ? episodesSearchQuery.value : searchQuery.value
)

function handleSearchUpdate(q) {
  if (isEpisodes.value) episodesSearchQuery.value = q
  else searchQuery.value = q
}

// Reset active search when switching tabs
watch(() => route.path, (newPath, oldPath) => {
  if (newPath !== oldPath) {
    if (newPath === '/episodes') episodesSearchQuery.value = ''
    else if (newPath === '/') searchQuery.value = ''
  }
})

// URL → input (back/forward on games view)
watch(() => route.query.q, q => { if (route.path === '/') searchQuery.value = q || '' })

// Auto-load catalog when navigating to / after login
watch(() => route.path, path => {
  if (path === '/' && loggedIn.value && !gamesStore.all.length && !gamesStore.loading)
    gamesStore.load()
})

// Input → URL (debounced, games view only)
let searchTimer
watch(searchQuery, q => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    if (route.path === '/' || route.path === '') {
      router.replace({ query: q ? { q } : {} })
    }
  }, 350)
})

const hideUnresolved = ref(true)

const displayedGames = computed(() => {
  let games = gamesStore.filtered(searchQuery.value.trim())
  if (hideUnresolved.value) games = games.filter(g => g.igdb !== null)
  return games
})

const gridResetKey = computed(() =>
  `${searchQuery.value.trim()}|${hideUnresolved.value}|${gamesStore.sortMode}|${gamesStore.sortAsc}`
)

watch(
  [() => gamesStore.sortMode, () => gamesStore.sortAsc, hideUnresolved],
  () => { document.querySelector('.grid-area')?.scrollTo({ top: 0 }) }
)

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
const { pullY, isPulling, setScrollEl } = usePullToRefresh(handleRefresh)

onMounted(() => {
  if (loggedIn.value) {
    gamesStore.load()
    try {
      const raw = localStorage.getItem('soj-player')
      if (raw) {
        const saved = JSON.parse(raw)
        if (saved?.current) playerStore.restore(saved)
      }
    } catch (_) {}
    refresh().catch(() => {})
  }
  setScrollEl(document.querySelector('.grid-area'))

  // Publish the command bar's measured height so .grid-area can clear it
  // robustly (survives font-scaling / wrap) instead of a fixed padding.
  const bar = document.querySelector('.command-bar')
  if (bar && 'ResizeObserver' in window) {
    _barObserver = new ResizeObserver(() => {
      document.documentElement.style.setProperty('--command-bar-h', `${bar.offsetHeight}px`)
    })
    _barObserver.observe(bar)
  }
})

let _barObserver = null
onUnmounted(() => _barObserver?.disconnect())
</script>

<template>
  <div id="mainView">
    <AppHeader
      :search-query="activeSearchQuery"
      :sort-mode="gamesStore.sortMode"
      :sort-asc="gamesStore.sortAsc"
      :loading="gamesStore.loading"
      :resolving="gamesStore.resolving"
      :last-fetch="gamesStore.lastFetch"
      :hide-unresolved="hideUnresolved"
      :is-episodes="isEpisodes"
      @update:searchQuery="handleSearchUpdate"
      @set-sort="gamesStore.setSort"
      @refresh="handleRefresh"
      @toggle-hide-unresolved="hideUnresolved = !hideUnresolved"
    >
      <template #account>
        <button
          class="btn btn-circle btn-ghost !size-9 !min-h-9"
          :class="loggedIn ? 'text-primary' : 'text-base-content/50'"
          :aria-label="loggedIn ? 'Mon compte' : 'Connexion'"
          @click="handleShowAccount"
        ><User :size="18" :stroke-width="2.25" /></button>
      </template>
    </AppHeader>

    <main class="main-region">
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
        v-show="baseRoute === '/'"
        :games="displayedGames"
        :loading="gamesStore.loading"
        :error="gamesStore.error"
        :total="gamesStore.all.length"
        :reset-key="gridResetKey"
      />

      <EpisodesFeed
        v-if="episodesVisited"
        v-show="baseRoute === '/episodes'"
        :search-query="episodesSearchQuery"
      />
    </main>

    <AudioPlayer />
  </div>

  <!-- Outside #mainView so overflow:hidden doesn't clip slide transitions -->
  <RouterView v-slot="{ Component }">
    <Transition :name="navDir">
      <component :is="Component" v-if="Component" :key="route.path" />
    </Transition>
  </RouterView>

  <AccountModal
    v-if="showAccountModal"
    :user-email="userEmail"
    @close="showAccountModal = false"
    @logout="handleLogout"
  />
</template>
