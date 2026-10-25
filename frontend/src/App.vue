<script setup>
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { loggedIn, getUserEmail, logout, refresh } from './lib/auth.js'
import { useGamesStore } from './stores/games.js'
import { usePlayerStore } from './stores/player.js'
import { useNavDirection } from './composables/useNavDirection.js'
import { usePullToRefresh } from './composables/usePullToRefresh.js'
import AppHeader    from './components/AppHeader.vue'
import GameGrid     from './components/GameGrid.vue'
import EpisodesFeed from './components/EpisodesFeed.vue'
import PodcastsRow   from './components/PodcastsRow.vue'
import AudioPlayer  from './components/AudioPlayer.vue'
import AccountModal from './components/AccountModal.vue'

const route  = useRoute()
const router = useRouter()

const gamesStore  = useGamesStore()
const playerStore = usePlayerStore()

const userEmail = computed(() => getUserEmail())

const { navDir } = useNavDirection(route, router)

const showAccountModal = ref(false)

// ── The Ludothèque: one base view (/), its tests, its podcasts, its games ───
// Overlay routes (/game/:slug, /episode/:slug, /podcast/:id, /login) slide in over it; it
// stays mounted (and scrolled) underneath.
const BASE_ROUTES = new Set(['/'])

// ── Search: one query, for the tests, the episodes and the games ───────────────────────────
const query = ref(route.query.q || '')

// URL → input (back/forward)
watch(() => route.query.q, q => { if (route.path === '/') query.value = q || '' })

// Input → URL (debounced)
let searchTimer
watch(query, q => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    if (route.path === '/') router.replace({ query: q ? { q } : {} })
  }, 350)
})

// Debounce the query that drives the (filter + locale-sort of ~2000 games) so fast
// typing doesn't re-run it on every keystroke. Separate from the 350 ms URL sync.
const debouncedQuery = ref(query.value)
let filterTimer
watch(query, q => {
  clearTimeout(filterTimer)
  filterTimer = setTimeout(() => { debouncedQuery.value = q }, 140)
})

// Admin only: a game with no page is a pipeline matter, not a reader's.
const hideUnresolved = ref(true)

const displayedGames = computed(() => {
  let games = gamesStore.filtered(debouncedQuery.value.trim())
  if (hideUnresolved.value) games = games.filter(g => g.igdb !== null)
  return games
})

const gridResetKey = computed(() =>
  `${debouncedQuery.value.trim()}|${hideUnresolved.value}|${gamesStore.sortMode}|${gamesStore.sortAsc}`
)

// A new sort shows the games from their start.
watch(
  [() => gamesStore.sortMode, () => gamesStore.sortAsc, hideUnresolved],
  () => { document.getElementById('h-games')?.scrollIntoView({ block: 'start' }) }
)

// Auto-load the catalog after login
watch(() => route.path, path => {
  if (!BASE_ROUTES.has(path) || !loggedIn.value) return
  if (!gamesStore.all.length && !gamesStore.loading) gamesStore.load()
  if (!gamesStore.episodesLoaded) gamesStore.loadEpisodes()
})

// The mini player floats over the bottom of the base views: they clear it
// only while it shows.
watch(() => playerStore.visible, v => {
  if (v) document.documentElement.style.removeProperty('--player-h')
  else document.documentElement.style.setProperty('--player-h', '0px')
}, { immediate: true })

function handleLogout() {
  showAccountModal.value = false
  logout()
  router.push('/login')
}

// The player floats above the login page and would keep playing after logout.
// Watching `loggedIn` covers both the account-modal logout and apiFetch's 401
// auto-logout; close() also clears the resume snapshot.
watch(loggedIn, v => { if (!v) playerStore.close() })

// A pull-to-refresh reloads the episodes in step with the catalog.
function handleRefresh() {
  gamesStore.refresh()
  gamesStore.loadEpisodes()
}

// ── Pull-to-refresh ───────────────────────────────────────────────────────────
const PULL_THRESHOLD = 80
const { pullY, isPulling, setScrollEl } = usePullToRefresh(handleRefresh)

// Point pull-to-refresh at the Ludothèque's scroll container, so its "at the
// top?" guard reads the right element.
function syncPullScrollEl() {
  nextTick(() => setScrollEl(document.querySelector('.home-scroll')))
}

onMounted(() => {
  if (loggedIn.value) {
    gamesStore.load()
    gamesStore.loadEpisodes()
    try {
      const raw = localStorage.getItem('soj-player')
      if (raw) {
        const saved = JSON.parse(raw)
        if (saved?.current) playerStore.restore(saved)
      }
    } catch (_) {}
    refresh().catch(() => {})
  }
  syncPullScrollEl()
})
</script>

<template>
  <div id="mainView">
    <AppHeader
      :search-query="query"
      :sort-mode="gamesStore.sortMode"
      :sort-asc="gamesStore.sortAsc"
      :hide-unresolved="hideUnresolved"
      @update:searchQuery="query = $event"
      @set-sort="gamesStore.setSort"
      @toggle-hide-unresolved="hideUnresolved = !hideUnresolved"
      @show-account="showAccountModal = true"
    />

    <main class="main-region">
      <!-- Pull-to-refresh indicator -->
      <div
        class="pull"
        :style="{ height: isPulling ? pullY + 'px' : '0px', transition: isPulling ? 'none' : 'height 0.2s ease' }"
      >
        <span class="lab" :style="{ opacity: Math.min(pullY / PULL_THRESHOLD, 1) }">
          {{ pullY >= PULL_THRESHOLD ? '↻ Relâcher' : '↓ Actualiser' }}
        </span>
      </div>

      <div class="scroll-area home-scroll">
        <EpisodesFeed :search-query="debouncedQuery" />
        <PodcastsRow v-if="!debouncedQuery.trim()" />
        <GameGrid
          :games="displayedGames"
          :loading="gamesStore.loading"
          :error="gamesStore.error"
          :total="gamesStore.all.length"
          :reset-key="gridResetKey"
          :has-query="!!debouncedQuery.trim()"
        />
      </div>
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

<style scoped>
.home-scroll { position: relative; }   /* the tests' blurred backdrop is placed in it */
.pull {
  display: flex;
  justify-content: center;
  align-items: center;
  overflow: hidden;
  flex-shrink: 0;
}
</style>
