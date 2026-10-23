<script setup>
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { loggedIn, getUserEmail, logout, refresh } from './lib/auth.js'
import { useGamesStore } from './stores/games.js'
import { usePlayerStore } from './stores/player.js'
import { useNavDirection } from './composables/useNavDirection.js'
import { usePullToRefresh } from './composables/usePullToRefresh.js'
import AppHeader    from './components/AppHeader.vue'
import TabBar       from './components/TabBar.vue'
import GameGrid     from './components/GameGrid.vue'
import EpisodesFeed from './components/EpisodesFeed.vue'
import AudioPlayer  from './components/AudioPlayer.vue'
import AccountModal from './components/AccountModal.vue'

const route  = useRoute()
const router = useRouter()

const gamesStore  = useGamesStore()
const playerStore = usePlayerStore()

const userEmail = computed(() => getUserEmail())

const { navDir } = useNavDirection(route, router)

const showAccountModal = ref(false)

// ── Base route: Tests (/) or Jeux (/jeux) ────────────────────────────────────
// Overlay routes (/game/:slug, /episode/:slug, /login) must NOT update this,
// so the base view stays visible under the slide-in transition.
const BASE_ROUTES = new Set(['/', '/jeux'])
const baseRoute   = ref(BASE_ROUTES.has(route.path) ? route.path : '/')

watch(() => route.path, path => {
  if (BASE_ROUTES.has(path)) baseRoute.value = path
})

const isJeux = computed(() => baseRoute.value === '/jeux')

// Mount the catalog only once Jeux is first opened, then keep it mounted (and
// scrolled) under the overlays and across tab switches.
const jeuxVisited = ref(false)
watch(isJeux, v => { if (v) jeuxVisited.value = true }, { immediate: true })

// ── Search: one query per tab ────────────────────────────────────────────────
const gamesQuery = ref(route.query.q || '')
const testsQuery = ref('')

const activeSearchQuery = computed(() => isJeux.value ? gamesQuery.value : testsQuery.value)

function handleSearchUpdate(q) {
  if (isJeux.value) gamesQuery.value = q
  else testsQuery.value = q
}

// URL → input (back/forward on Jeux)
watch(() => route.query.q, q => { if (route.path === '/jeux') gamesQuery.value = q || '' })

// Input → URL (debounced, Jeux only)
let searchTimer
watch(gamesQuery, q => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    if (route.path === '/jeux') router.replace({ query: q ? { q } : {} })
  }, 350)
})

// Debounce the query that drives the (filter + locale-sort of ~1600 games) so fast
// typing doesn't re-run it on every keystroke. Separate from the 350 ms URL sync.
const debouncedQuery = ref(gamesQuery.value)
let filterTimer
watch(gamesQuery, q => {
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
  `${debouncedQuery.value.trim()}|${hideUnresolved.value}|${gamesStore.sortMode}|${gamesStore.sortAsc}|${gamesStore.selectedPodcast}`
)

watch(
  [() => gamesStore.sortMode, () => gamesStore.sortAsc, hideUnresolved],
  () => { document.querySelector('.games-scroll')?.scrollTo({ top: 0 }) }
)

// Auto-load the catalog after login
watch(() => route.path, path => {
  if (BASE_ROUTES.has(path) && loggedIn.value && !gamesStore.all.length && !gamesStore.loading)
    gamesStore.load()
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

// Bumped on every pull-to-refresh so the (separately-mounted) feed reloads in
// step with the catalog — a pull on either tab refreshes both.
const feedRefreshSignal = ref(0)
function handleRefresh() {
  gamesStore.refresh()
  feedRefreshSignal.value++
}

// ── Pull-to-refresh ───────────────────────────────────────────────────────────
const PULL_THRESHOLD = 80
const { pullY, isPulling, setScrollEl } = usePullToRefresh(handleRefresh)

// Point pull-to-refresh at the shown tab's scroll container, so its "at the
// top?" guard reads the right element.
function syncPullScrollEl() {
  nextTick(() => setScrollEl(document.querySelector(isJeux.value ? '.games-scroll' : '.feed-scroll')))
}
watch(isJeux, syncPullScrollEl)

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
  syncPullScrollEl()
})
</script>

<template>
  <div id="mainView">
    <AppHeader
      :search-query="activeSearchQuery"
      :sort-mode="gamesStore.sortMode"
      :sort-asc="gamesStore.sortAsc"
      :hide-unresolved="hideUnresolved"
      :selected-podcast="gamesStore.selectedPodcast"
      :is-jeux="isJeux"
      @update:searchQuery="handleSearchUpdate"
      @set-sort="gamesStore.setSort"
      @set-podcast="gamesStore.setPodcast"
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

      <EpisodesFeed
        v-show="baseRoute === '/'"
        :search-query="testsQuery"
        :refresh-signal="feedRefreshSignal"
      />

      <GameGrid
        v-if="jeuxVisited"
        v-show="baseRoute === '/jeux'"
        :games="displayedGames"
        :loading="gamesStore.loading"
        :error="gamesStore.error"
        :total="gamesStore.all.length"
        :reset-key="gridResetKey"
        :has-query="!!gamesQuery.trim()"
      />
    </main>

    <AudioPlayer />
    <TabBar :is-jeux="isJeux" @show-account="showAccountModal = true" />
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
.pull {
  display: flex;
  justify-content: center;
  align-items: center;
  overflow: hidden;
  flex-shrink: 0;
}
</style>
