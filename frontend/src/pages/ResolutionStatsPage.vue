<script setup>
// Admin console for name→IGDB resolution quality.
//
// The job here is judging a *match between two naming systems*, so the row is a
// confrontation: what the podcast said, what IGDB returned, and the cover that
// settles it at a glance. Every group is listed and filtered client-side — the
// old two-list split (suspects + unresolved) made ~1500 correctly-resolved games
// unreachable, which is exactly where a wrong match hides when the heuristic
// under-flags.
//
// Desktop-first by design: this is the one screen in the app whose task is
// scanning ~1660 rows, so filters sit inline rather than behind popovers and
// sorting lives on the column headers.
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter, RouterLink } from 'vue-router'
import { fetchResolutionStats, refreshPodcastIgdb, openResolutionStream } from '../lib/games.js'
import { useGamesStore } from '../stores/games.js'
import { useInfiniteScroll } from '../composables/useInfiniteScroll.js'
import { formatDate } from '../lib/utils.js'
import { igdbUrl } from '../lib/igdbCdn.js'
import { PODCASTS } from '../lib/podcasts.js'
import placeholderCover from '../assets/placeholder-cover.svg'
import PodcastBadge from '../components/PodcastBadge.vue'
import IgdbPickerModal from '../components/IgdbPickerModal.vue'
import BackBar from '../components/BackBar.vue'
import {
  RotateCw, Loader2, Wrench, Search, X, ArrowUp, ArrowDown, Lock, ExternalLink,
} from 'lucide-vue-next'

const router     = useRouter()
const gamesStore = useGamesStore()

const stats   = ref(null)
const loading = ref(true)
const error   = ref(null)
const picking = ref(null)
const refreshingPodcast = ref(null)

// ── Filter state ────────────────────────────────────────────────────────────
// Local, deliberately: `gamesStore.selectedPodcast` is shared with the Jeux and
// Épisodes tabs, and an admin filter silently re-filtering the user's browsing
// would be a surprise.
const query         = ref('')
const status        = ref('all')
const podcastId     = ref('all')
const correctedOnly = ref(false)
const sortMode      = ref('date')     // date | name | year | episodes
const sortAsc       = ref(false)
const DEFAULT_ASC   = { date: false, name: true, year: false, episodes: false }

const STATUSES = [
  { id: 'all',        label: 'Tous' },
  { id: 'resolved',   label: 'Résolus' },
  { id: 'suspect',    label: 'Douteux' },
  { id: 'unresolved', label: 'Non résolus' },
]
const STATUS_LABEL = Object.fromEntries(STATUSES.map(s => [s.id, s.label]))
const podcastOptions = [{ id: 'all', label: 'Tous' },
                        ...PODCASTS.map(p => ({ id: p.id, label: p.label }))]

// One collator for the whole page: `localeCompare` rebuilds one per call, which
// is costly across ~1660 names (same reason stores/games.js keeps a shared one).
const collator = new Intl.Collator('fr', { sensitivity: 'base' })

// Sorting/filtering ~1660 rows per keystroke is the expensive path — debounce the
// query the way App.vue does for the catalogue.
const debouncedQuery = ref('')
let _debounce
watch(query, (v) => {
  clearTimeout(_debounce)
  _debounce = setTimeout(() => { debouncedQuery.value = v }, 140)
})

const filtered = computed(() => {
  let rows = stats.value?.games ?? []
  if (status.value !== 'all')  rows = rows.filter(g => g.status === status.value)
  if (podcastId.value !== 'all') rows = rows.filter(g => g.podcasts?.includes(podcastId.value))
  if (correctedOnly.value)     rows = rows.filter(g => g.corrected)
  const q = debouncedQuery.value.trim().toLowerCase()
  if (q) {
    // Both sides of the match are searchable: you look for a game by what the
    // podcast called it *or* by the wrong thing IGDB returned.
    rows = rows.filter(g =>
      g.name.toLowerCase().includes(q) ||
      g.igdbName?.toLowerCase().includes(q) ||
      g.displayName?.toLowerCase().includes(q))
  }
  const dir = sortAsc.value ? 1 : -1
  return [...rows].sort((a, b) => {
    if (sortMode.value === 'name')     return dir * collator.compare(a.name, b.name)
    if (sortMode.value === 'episodes') return dir * (a.episodeCount - b.episodeCount)
    if (sortMode.value === 'year') {
      // Undated last whichever way the column points — a missing year is not "old".
      if (!a.released && !b.released) return collator.compare(a.name, b.name)
      if (!a.released) return 1
      if (!b.released) return -1
      return dir * (Number(a.released) - Number(b.released))
    }
    return dir * ((a.latestPubTs ?? 0) - (b.latestPubTs ?? 0))
  })
})

function setSort(mode) {
  // Click the active column again to flip direction — the idiom stores/games.js
  // already uses for the catalogue's sort.
  if (sortMode.value === mode) sortAsc.value = !sortAsc.value
  else { sortMode.value = mode; sortAsc.value = DEFAULT_ASC[mode] }
}

// Paging resets whenever the visible set changes, like App.vue's gridResetKey.
const resetKey = computed(() =>
  [debouncedQuery.value, status.value, podcastId.value, correctedOnly.value,
   sortMode.value, sortAsc.value].join('|'))
const { visibleItems, sentinel } = useInfiniteScroll(filtered, { pageSize: 80, resetKey })

// Changing the visible set means you're looking at a different list — start at
// the top of it. `scrollTo` is optional-called: not every environment implements
// it on an element (jsdom doesn't), and a missing scroll must not break filtering.
const scroller = ref(null)
watch(resetKey, () => scroller.value?.scrollTo?.({ top: 0 }))

function clearFilters() {
  query.value = ''; debouncedQuery.value = ''
  status.value = 'all'; podcastId.value = 'all'; correctedOnly.value = false
}
const filtersActive = computed(() =>
  !!debouncedQuery.value || status.value !== 'all' ||
  podcastId.value !== 'all' || correctedOnly.value)

// ── Data ────────────────────────────────────────────────────────────────────
let _sse = null

async function load() {
  try {
    stats.value = await fetchResolutionStats()
    error.value = null
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

// While a sweep runs the figures are a moving target; follow it to the end and
// reload once, so the page settles on numbers that mean something.
async function watchResolution() {
  if (_sse) return
  try {
    _sse = await openResolutionStream()
  } catch { return }
  _sse.onmessage = (e) => {
    if (JSON.parse(e.data).type === 'done') { _sse.close(); _sse = null; load() }
  }
  _sse.onerror = () => {
    if (_sse && _sse.readyState === EventSource.CLOSED) { _sse = null; load() }
  }
}

async function reresolvePodcast(id) {
  refreshingPodcast.value = id
  try {
    await refreshPodcastIgdb(id)
    await load()
    watchResolution()
  } catch (e) {
    error.value = e.message
  } finally {
    refreshingPodcast.value = null
  }
}

function onSaved() {
  picking.value = null
  load()
  gamesStore.load(false)   // the catalogue entry may have moved to a new slug
}

onMounted(async () => {
  await load()
  if (stats.value?.pending) watchResolution()
})
onUnmounted(() => {
  clearTimeout(_debounce)
  if (_sse) { _sse.close(); _sse = null }
})

function pct(n, total) { return total ? Math.round((n / total) * 100) : 0 }
</script>

<template>
  <!-- Fixed shell + inner scroller, like DetailView: the back pill is positioned
       absolute, so a page that scrolls its own root scrolls the pill away. -->
  <div class="fixed inset-0 z-[var(--z-detail)] bg-base-100 flex flex-col">
    <BackBar label="Retour" @back="router.push('/')" />

    <div ref="scroller" class="flex-1 min-h-0 overflow-y-auto">
      <div class="console">
        <header class="console__head">
          <div>
            <h1 class="console__title">Résolution des noms</h1>
            <p class="console__sub">Nom du podcast → fiche IGDB.</p>
          </div>

          <div v-if="stats" class="console__podcasts">
            <div v-for="p in stats.podcasts" :key="p.id" class="pstat">
              <div class="pstat__top">
                <PodcastBadge :id="p.id" />
                <span class="pstat__nums">
                  <b>{{ p.resolved }}</b>/{{ p.appearances }}
                  <template v-if="p.failed"> · <span class="text-error">{{ p.failed }} échec</span></template>
                  <template v-if="p.pending"> · {{ p.pending }} en attente</template>
                </span>
                <button
                  class="icon-action !size-6 !min-h-6"
                  :disabled="refreshingPodcast === p.id"
                  :title="`Re-résoudre tout ${p.name}`"
                  :aria-label="`Re-résoudre tout ${p.name}`"
                  @click="reresolvePodcast(p.id)"
                >
                  <RotateCw :size="11" :stroke-width="2.5"
                            :class="{ 'animate-spin': refreshingPodcast === p.id }" />
                </button>
              </div>
              <div class="meter" :aria-label="`${pct(p.resolved, p.appearances)} % résolus`">
                <span class="meter__fill" :style="{ width: pct(p.resolved, p.appearances) + '%' }" />
              </div>
            </div>
          </div>
        </header>

        <div v-if="loading" class="flex flex-col gap-1.5 mt-4">
          <div v-for="i in 12" :key="i" class="skeleton-shimmer h-[42px] rounded-lg" aria-hidden="true" />
        </div>

        <p v-else-if="error" class="text-sm text-error py-8">Erreur : {{ error }}</p>

        <template v-else-if="stats">
          <!-- A sweep in flight means these numbers are still moving. Say so: a
               half-built cache reads exactly like a quality problem otherwise. -->
          <p v-if="stats.pending" class="banner">
            <Loader2 v-if="stats.resolving" :size="14" class="animate-spin flex-shrink-0" />
            <span>
              {{ stats.resolving ? 'Résolution en cours' : 'Résolution incomplète' }} —
              {{ stats.pending }} apparition(s) en attente. Les chiffres ne sont pas définitifs.
            </span>
          </p>
          <p v-if="!stats.writable" class="banner banner--muted">
            <Lock :size="14" class="flex-shrink-0" />
            <span>
              Lecture seule : corrections.json fait partie de l’image. Corrigez en dev,
              puis committez le fichier — c’est lui la source de vérité.
            </span>
          </p>

          <!-- Toolbar. Inline, not behind popovers: on a desktop console the
               filters are the primary control and there is room to show them. -->
          <div class="toolbar">
            <label class="search-wrap !flex toolbar__search">
              <Search :size="15" class="search-wrap__icon" />
              <input v-model="query" class="search-input" type="search"
                     placeholder="Rechercher un nom (podcast ou IGDB)…" />
              <button v-if="query" class="search-wrap__clear" aria-label="Effacer la recherche"
                      @click="query = ''"><X :size="12" :stroke-width="2.5" /></button>
            </label>

            <div class="tab-group" role="group" aria-label="Statut">
              <button v-for="s in STATUSES" :key="s.id" class="tab-pill"
                      :class="{ 'is-active': status === s.id }" @click="status = s.id">
                <span>{{ s.label }}</span>
              </button>
            </div>

            <div v-if="podcastOptions.length > 2" class="tab-group" role="group" aria-label="Podcast">
              <button v-for="p in podcastOptions" :key="p.id" class="tab-pill"
                      :class="{ 'is-active': podcastId === p.id }" @click="podcastId = p.id">
                <span>{{ p.label }}</span>
              </button>
            </div>

            <button class="chip toolbar__toggle" :class="{ 'chip-accent': correctedOnly }"
                    :aria-pressed="correctedOnly" @click="correctedOnly = !correctedOnly">
              Corrigés
            </button>

            <span class="toolbar__count">
              {{ filtered.length }}<span class="toolbar__count-total"> / {{ stats.games.length }}</span>
              <button v-if="filtersActive" class="toolbar__reset" @click="clearFilters">réinitialiser</button>
            </span>
          </div>

          <!-- Column headers double as the sort control — the desktop idiom. -->
          <div class="rt-head rt-row" role="row">
            <span aria-hidden="true" />
            <button class="rt-sort" :class="{ 'is-active': sortMode === 'name' }" @click="setSort('name')">
              Nom du podcast
              <component :is="sortAsc ? ArrowUp : ArrowDown" v-if="sortMode === 'name'" :size="11" :stroke-width="3" />
            </button>
            <span aria-hidden="true" />
            <span>Fiche IGDB</span>
            <button class="rt-sort rt-num" :class="{ 'is-active': sortMode === 'year' }" @click="setSort('year')">
              An
              <component :is="sortAsc ? ArrowUp : ArrowDown" v-if="sortMode === 'year'" :size="11" :stroke-width="3" />
            </button>
            <button class="rt-sort rt-num" :class="{ 'is-active': sortMode === 'episodes' }" @click="setSort('episodes')">
              Ép
              <component :is="sortAsc ? ArrowUp : ArrowDown" v-if="sortMode === 'episodes'" :size="11" :stroke-width="3" />
            </button>
            <button class="rt-sort" :class="{ 'is-active': sortMode === 'date' }" @click="setSort('date')">
              Dernier épisode
              <component :is="sortAsc ? ArrowUp : ArrowDown" v-if="sortMode === 'date'" :size="11" :stroke-width="3" />
            </button>
            <span aria-hidden="true">Actions</span>
          </div>

          <p v-if="!filtered.length" class="empty">
            Aucun jeu ne correspond.
            <button v-if="filtersActive" class="toolbar__reset" @click="clearFilters">Réinitialiser les filtres</button>
          </p>

          <div v-else class="rt-body">
            <div v-for="row in visibleItems" :key="row.slug" class="rt-row rt-item"
                 :class="`is-${row.status}`">
              <span class="rt-bar" :title="STATUS_LABEL[row.status]" />

              <div class="rt-cell rt-cell--podcast min-w-0">
                <span class="rt-name" :title="row.name">{{ row.name }}</span>
                <PodcastBadge v-for="id in row.podcasts" :key="id" :id="id" />
                <span v-if="row.corrected" class="chip chip-accent rt-flag"
                      :title="row.displayName ? `Nom affiché : ${row.displayName}` : 'Corrigé à la main'">
                  corrigé
                </span>
              </div>

              <span class="rt-arrow" aria-hidden="true">→</span>

              <div class="rt-cell rt-cell--igdb min-w-0">
                <img class="rt-cover"
                     :src="row.coverImageId ? igdbUrl(row.coverImageId, 't_thumb') : placeholderCover"
                     alt="" loading="lazy" />
                <span v-if="row.igdbName" class="rt-igdb" :title="row.igdbSlug">{{ row.igdbName }}</span>
                <span v-else class="rt-none">non résolu</span>
              </div>

              <span class="rt-num rt-dim">{{ row.released || '—' }}</span>
              <span class="rt-num rt-dim">{{ row.episodeCount }}</span>
              <span class="rt-date rt-dim">{{ row.latestPubTs ? formatDate(row.latestPubTs) : '—' }}</span>

              <div class="rt-actions">
                <RouterLink class="icon-action !size-7 !min-h-7"
                            :to="`/episode/${encodeURIComponent(row.episodeSlug)}`"
                            :title="`Épisode : ${row.episodeTitle}`"
                            :aria-label="`Ouvrir l’épisode ${row.episodeTitle}`">
                  <ExternalLink :size="13" :stroke-width="2.25" />
                </RouterLink>
                <button v-if="stats.writable" class="icon-action !size-7 !min-h-7"
                        title="Corriger" aria-label="Corriger cette résolution"
                        @click="picking = row">
                  <Wrench :size="13" :stroke-width="2.25" />
                </button>
              </div>
            </div>
            <div ref="sentinel" class="h-1" />
          </div>
        </template>

        <!-- Clears the floating audio player, which overlays this page. -->
        <div class="detail-bottom-pad" />
      </div>
    </div>

    <IgdbPickerModal
      v-if="picking"
      :game="picking"
      :has-correction="picking.corrected"
      :writable="stats?.writable !== false"
      @close="picking = null"
      @saved="onSaved"
    />
  </div>
</template>

<style scoped>
.console {
  max-width: 1600px;
  margin: 0 auto;
  padding: var(--back-clear) var(--gutter) 0;
}

/* ── Header ─────────────────────────────────────────────────────────── */
.console__head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}
.console__title { font-size: 1.5rem; font-weight: 800; letter-spacing: -0.02em; }
.console__sub   { font-size: 0.8rem; color: rgba(var(--rgb-line), 0.45); margin-top: 2px; }

.console__podcasts { display: flex; gap: 10px; flex-wrap: wrap; }
.pstat {
  min-width: 210px;
  padding: 7px 10px;
  border-radius: var(--radius-md);
  background: rgba(var(--rgb-line), 0.04);
  border: 1px solid var(--border-subtle);
}
.pstat__top { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.pstat__nums {
  flex: 1;
  font-family: var(--font-mono);
  font-size: 0.68rem;
  font-variant-numeric: tabular-nums;
  color: rgba(var(--rgb-line), 0.5);
}
.pstat__nums b { color: rgba(var(--rgb-line), 0.9); font-weight: 700; }

.meter { height: 3px; border-radius: 999px; background: rgba(var(--rgb-line), 0.08); overflow: hidden; }
/* Green, not the brand accent: this gauge measures the same "resolved" the green
   row bars mean, and a near-full bar of alarm-red reads as a problem. */
.meter__fill {
  display: block; height: 100%; border-radius: 999px;
  background: rgba(var(--rgb-high), 0.65);
  transition: width var(--dur-med) var(--ease-std);
}

/* ── Banners ────────────────────────────────────────────────────────── */
.banner {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 11px; margin-bottom: 10px;
  border-radius: var(--radius-md);
  font-size: 0.76rem;
  background: color-mix(in srgb, var(--game-accent) 12%, transparent);
  border: 1px solid var(--border-accent);
  color: rgba(var(--rgb-line), 0.85);
}
.banner--muted {
  background: rgba(var(--rgb-line), 0.05);
  border-color: var(--border-subtle);
  color: rgba(var(--rgb-line), 0.62);
}

/* ── Toolbar ────────────────────────────────────────────────────────── */
.toolbar {
  position: sticky;
  top: 0;
  z-index: 2;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 10px 0;
  background: rgb(var(--rgb-base));
  border-bottom: 1px solid var(--border-subtle);
}
.toolbar__search { flex: 1 1 260px; min-width: 200px; max-width: 420px; position: relative; }
.toolbar__toggle { cursor: pointer; height: 30px; }
.toolbar__count {
  margin-left: auto;
  display: flex; align-items: center; gap: 8px;
  font-family: var(--font-mono);
  font-size: 0.72rem;
  font-variant-numeric: tabular-nums;
  color: rgba(var(--rgb-line), 0.75);
}
.toolbar__count-total { color: rgba(var(--rgb-line), 0.35); }
.toolbar__reset {
  font-family: inherit;
  font-size: 0.7rem;
  color: var(--game-accent);
  text-decoration: underline;
  text-underline-offset: 2px;
}

/* ── Table ──────────────────────────────────────────────────────────── */
/* One template shared by the header and every row, so columns line up without
   a real <table> (rows need their own hover/status treatment). */
.rt-row {
  display: grid;
  grid-template-columns:
    3px                 /* status bar   */
    minmax(0, 1.1fr)    /* podcast name */
    14px                /* arrow        */
    minmax(0, 1.4fr)    /* IGDB name    */
    52px                /* year         */
    40px                /* episodes     */
    116px               /* last episode */
    64px;               /* actions      */
  align-items: center;
  gap: 10px;
}

.rt-head {
  position: sticky;
  top: 50px;                     /* under the toolbar */
  z-index: 1;
  padding: 7px 8px;
  background: rgb(var(--rgb-base));
  border-bottom: 1px solid var(--border-subtle);
  font-size: 0.6rem;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: rgba(var(--rgb-line), 0.4);
}
.rt-sort {
  display: inline-flex; align-items: center; gap: 3px;
  text-align: left;
  color: inherit;
  transition: color var(--dur-fast) var(--ease-std);
}
.rt-sort:hover     { color: rgba(var(--rgb-line), 0.75); }
.rt-sort.is-active { color: var(--game-accent); }

.rt-body { padding-bottom: 8px; }

.rt-item {
  position: relative;
  padding: 5px 8px;
  border-radius: var(--radius-sm);
  border: 1px solid transparent;
  transition: background var(--dur-fast) var(--ease-std);
}
.rt-item:hover { background: rgba(var(--rgb-line), 0.05); }
.rt-item + .rt-item { border-top: 1px solid rgba(var(--rgb-line), 0.04); }

/* Status is the row's own left edge — the idiom .episode-card.playing uses. */
.rt-bar { height: 22px; border-radius: 999px; background: rgba(var(--rgb-line), 0.12); }
.is-resolved   .rt-bar { background: rgba(var(--rgb-high), 0.55); }
.is-suspect    .rt-bar { background: rgb(var(--rgb-mid)); }
.is-unresolved .rt-bar { background: rgba(var(--rgb-low), 0.7); }

.rt-cell { display: flex; align-items: center; gap: 6px; }
.rt-name {
  font-size: 0.82rem; font-weight: 600;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.rt-arrow { font-size: 0.8rem; color: rgba(var(--rgb-line), 0.25); text-align: center; }
.rt-igdb {
  font-size: 0.8rem; color: rgba(var(--rgb-line), 0.72);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.rt-none { font-size: 0.75rem; font-style: italic; color: rgba(var(--rgb-low), 0.75); }
.rt-flag { font-size: 0.55rem !important; padding: 0 5px; }

/* The cover is the fastest wrong-match detector there is: you see that
   Astrobotanica is not Astro Bot without reading a word. */
.rt-cover {
  width: 22px; height: 29px; flex-shrink: 0;
  object-fit: cover; border-radius: 3px;
  background: rgba(var(--rgb-line), 0.06);
}

/* JetBrains Mono is loaded app-wide and used nowhere else — it is exactly the
   utility face a column of years and counts wants. */
.rt-num, .rt-date {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: 0.7rem;
}
.rt-num  { text-align: right; }
.rt-dim  { color: rgba(var(--rgb-line), 0.42); }
.rt-date { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.rt-actions { display: flex; align-items: center; gap: 2px; justify-content: flex-end; }

.empty {
  display: flex; align-items: center; gap: 10px;
  font-size: 0.82rem; color: rgba(var(--rgb-line), 0.35);
  padding: 40px 8px;
}

/* ── Below the console's home turf ───────────────────────────────────── */
/* The task is desktop, but the page must not be broken on a phone: drop the
   columns and let each row stack. */
@media (max-width: 899px) {
  .rt-head { display: none; }
  .rt-row {
    grid-template-columns: 3px minmax(0, 1fr) auto;
    grid-template-areas:
      "bar name    actions"
      "bar igdb    actions"
      "bar meta    actions";
    gap: 2px 10px;
    padding: 8px;
  }
  .rt-bar    { grid-area: bar; height: 100%; }
  .rt-cell--podcast { grid-area: name; }
  .rt-cell--igdb    { grid-area: igdb; }
  .rt-arrow  { display: none; }
  .rt-actions { grid-area: actions; }
  .rt-num, .rt-date { display: none; }
  .rt-item + .rt-item { margin-top: 4px; }
}
</style>
