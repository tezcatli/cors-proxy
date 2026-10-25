<script setup>
import { computed } from 'vue'
import { useGamesStore } from '../stores/games.js'
import { useInfiniteScroll } from '../composables/useInfiniteScroll.js'
import GameGrid from './GameGrid.vue'
import EpisodeRow from './EpisodeRow.vue'

// A search on the Ludothèque (DECISIONS.md, « Interface »): the listener knows
// whether they look for a game or an episode — the two doors of the one
// listening — so a search shows one list, never both: the games by their name,
// or the episodes by their title. No test cards: a test is found by its game
// (its page holds the review) or by its episode. Games lead, unless only the
// episodes match; once the listener picks a scope it holds while they type.
const props = defineProps({
  query:        { type: String, required: true },
  games:        { type: Array, required: true },   // the catalog, already searched (App)
  scope:        { type: String, default: null },   // 'jeux' | 'episodes', null until chosen
  gamesLoading: Boolean,
  gamesError:   String,
  gamesTotal:   Number,
  resetKey:     String,
})
const emit = defineEmits(['update:scope'])

const gamesStore = useGamesStore()

const q = computed(() => props.query.trim().toLowerCase())
const episodes = computed(() => gamesStore.episodes.filter(ep => ep.title.toLowerCase().includes(q.value)))

const shown = computed(() => props.scope
  ?? (!props.games.length && episodes.value.length ? 'episodes' : 'jeux'))

const { visibleItems: visibleEpisodes, sentinel } = useInfiniteScroll(episodes, { pageSize: 40 })

const SCOPES = [
  { id: 'jeux',     label: 'Jeux',     count: () => props.games.length },
  { id: 'episodes', label: 'Épisodes', count: () => episodes.value.length },
]
</script>

<template>
  <div class="search-results">
    <div class="content">
      <div role="tablist" aria-label="Chercher parmi" class="scopes">
        <button
          v-for="s in SCOPES"
          :id="`tab-${s.id}`"
          :key="s.id"
          type="button"
          role="tab"
          class="scope"
          :aria-selected="shown === s.id"
          :aria-controls="`panel-${s.id}`"
          @click="emit('update:scope', s.id)"
        >
          {{ s.label }} <span class="mono scope__count">{{ s.count() }}</span>
        </button>
      </div>
    </div>

    <div v-if="shown === 'jeux'" id="panel-jeux" role="tabpanel" aria-labelledby="tab-jeux">
      <GameGrid
        :games="games"
        :loading="gamesLoading"
        :error="gamesError"
        :total="gamesTotal"
        :reset-key="resetKey"
        has-query
      />
    </div>

    <div v-else id="panel-episodes" role="tabpanel" aria-labelledby="tab-episodes" class="content episodes">
      <template v-if="episodes.length">
        <EpisodeRow v-for="ep in visibleEpisodes" :key="ep.slug" :ep="ep" show-podcast />
        <div ref="sentinel" class="h-1" />
      </template>
      <div v-else-if="!gamesStore.episodesLoading" class="empty">
        <p class="cond empty__title">Rien ici</p>
        <p class="empty__text">Aucun épisode ne correspond à votre recherche.</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.search-results { padding-top: 16px; }
.scopes {
  display: inline-flex;
  gap: 2px;
  padding: 3px;
  margin-bottom: 20px;
  background: var(--c-surface);
  box-shadow: inset 0 0 0 1px var(--c-line-strong);
}
.scope {
  display: inline-flex;
  align-items: baseline;
  gap: 8px;
  min-height: 40px;
  padding: 8px 16px;
  border: 0;
  background: transparent;
  color: var(--c-fg-2);
  font-family: var(--font-display);
  font-weight: 600;
  cursor: pointer;
}
.scope:hover { color: var(--c-fg); }
.scope:focus-visible { outline: 2px solid var(--c-accent); outline-offset: 2px; }
.scope[aria-selected="true"] { background: var(--c-accent); color: var(--c-accent-fg); }
.scope__count { opacity: 0.7; }
.episodes { padding-bottom: 24px; }
.empty { padding: 80px 0; text-align: center; }
.empty__title { font-size: var(--text-2xl); margin: 0 0 8px; }
.empty__text { color: var(--c-fg-2); margin: 0 auto; max-width: 36ch; }
</style>
