<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { fetchEpisodes } from '../lib/games.js'
import { useEpisodePlayer } from '../composables/useEpisodePlayer.js'
import { useInfiniteScroll } from '../composables/useInfiniteScroll.js'
import EpisodeFeedCard from './EpisodeFeedCard.vue'
import { Mic } from 'lucide-vue-next'

const props = defineProps({
  searchQuery:   String,
  refreshSignal: { type: Number, default: 0 },
})

const router = useRouter()
const { playerStore, isEpPlaying, playEp, togglePause } = useEpisodePlayer()

const episodes = ref([])
const loading  = ref(true)
const error    = ref(null)

async function load() {
  try { episodes.value = await fetchEpisodes(); error.value = null }
  catch (e) { error.value = e.message }
  finally   { loading.value = false }
}

onMounted(load)
// Reload when the pull-to-refresh signal bumps (keeps the existing list visible).
watch(() => props.refreshSignal, (v, prev) => { if (v !== prev) load() })

const filteredEpisodes = computed(() => {
  const q = props.searchQuery?.trim().toLowerCase()
  if (!q) return episodes.value
  return episodes.value.filter(ep =>
    ep.title.toLowerCase().includes(q) ||
    ep.games?.some(g => g.name.toLowerCase().includes(q))
  )
})

// ── Incremental rendering ────────────────────────────────────────────────────
const { visibleItems: visibleEpisodes, sentinel } = useInfiniteScroll(
  filteredEpisodes,
  { pageSize: 50 },
)

function viewEp(ep) {
  router.push('/episode/' + encodeURIComponent(ep.urlSlug))
}
</script>

<template>
  <div class="grid-area overflow-y-auto">
    <!-- Loading skeletons -->
    <div v-if="loading" class="max-w-3xl mx-auto px-[var(--gutter)] pt-3.5 sm:pt-4 lg:pt-5 flex flex-col gap-2">
      <div
        v-for="i in 10"
        :key="i"
        class="skeleton-shimmer h-[68px] rounded-xl"
        aria-hidden="true"
      />
    </div>

    <!-- Error -->
    <div v-else-if="error" class="flex justify-center items-center py-20 text-base-content/50 text-sm">
      Erreur : {{ error }}
    </div>

    <!-- Empty -->
    <div
      v-else-if="!filteredEpisodes.length"
      class="flex flex-col items-center gap-3 py-20 text-base-content/50"
    >
      <Mic :size="48" :stroke-width="1.5" class="opacity-70" />
      <p class="text-sm">Aucun épisode trouvé.</p>
    </div>

    <!-- Feed list -->
    <div
      v-else
      class="max-w-3xl mx-auto px-[var(--gutter)] pt-3.5 pb-6 sm:pt-4 sm:pb-8 lg:pt-5 lg:pb-10"
    >
      <div class="flex flex-col gap-2">
        <EpisodeFeedCard
          v-for="ep in visibleEpisodes"
          :key="ep.slug"
          :episode="ep"
          :is-playing="isEpPlaying(ep)"
          :is-paused="playerStore.paused"
          @play="playEp"
          @toggle-pause="togglePause"
          @view="viewEp"
        />
      </div>
      <div ref="sentinel" class="h-1" />
    </div>
  </div>
</template>
