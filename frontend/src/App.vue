<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { isLoggedIn, getUserEmail, logout } from './lib/auth.js'
import { useGamesStore } from './stores/games.js'
import { usePlayerStore } from './stores/player.js'
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

const loggedIn  = computed(() => isLoggedIn())
const userEmail = computed(() => getUserEmail())

let _prevPos   = router.options.history.state?.position ?? 0
let _prevDepth = route.meta?.depth ?? 0
const navDir = ref('nav-fade')
watch(() => route.path, (newPath, oldPath) => {
  const newPos   = router.options.history.state?.position ?? 0
  const newDepth = route.meta?.depth ?? 0
  if (newPath === '/login' || oldPath === '/login') {
    navDir.value = 'nav-fade'
  } else if (newDepth === 0 && _prevDepth === 0) {
    navDir.value = 'nav-fade'
  } else if (newPos < _prevPos) {
    navDir.value = 'nav-back'
  } else if (newDepth > _prevDepth) {
    navDir.value = 'nav-overlay'
  } else {
    navDir.value = 'nav-forward'
  }
  _prevPos   = newPos
  _prevDepth = newDepth
}, { flush: 'sync' })

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
const feedRef             = ref(null)

const isEpisodes = computed(() => baseRoute.value === '/episodes')

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

const hideUnresolved = ref(false)

const displayedGames = computed(() => {
  let games = gamesStore.filtered(searchQuery.value.trim())
  if (hideUnresolved.value) games = games.filter(g => g.igdb !== null)
  return games
})

watch(
  [() => gamesStore.sortMode, () => gamesStore.sortAsc, hideUnresolved],
  () => { if (_gridEl) _gridEl.scrollTop = 0 }
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
      :search-query="activeSearchQuery"
      :sort-mode="gamesStore.sortMode"
      :sort-asc="gamesStore.sortAsc"
      :loading="gamesStore.loading"
      :last-fetch="gamesStore.lastFetch"
      :hide-unresolved="hideUnresolved"
      :episode-count="feedRef?.episodeCount"
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
    />

    <EpisodesFeed
      v-show="baseRoute === '/episodes'"
      ref="feedRef"
      :search-query="episodesSearchQuery"
    />

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
