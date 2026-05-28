<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { fetchEpisodes } from '../lib/games.js'
import { useEpisodePlayer } from '../composables/useEpisodePlayer.js'
import EpisodeFeedCard from './EpisodeFeedCard.vue'
import { Mic } from 'lucide-vue-next'

const props = defineProps({
  searchQuery: String,
})

const router = useRouter()
const { playerStore, isEpPlaying, playEp, togglePause } = useEpisodePlayer()

const episodes = ref([])
const loading  = ref(true)
const error    = ref(null)

onMounted(async () => {
  try { episodes.value = await fetchEpisodes() }
  catch (e) { error.value = e.message }
  finally   { loading.value = false }
})

const filteredEpisodes = computed(() => {
  const q = props.searchQuery?.trim().toLowerCase()
  if (!q) return episodes.value
  return episodes.value.filter(ep =>
    ep.title.toLowerCase().includes(q) ||
    ep.games?.some(g => g.name.toLowerCase().includes(q))
  )
})

defineExpose({ episodeCount: computed(() => episodes.value.length) })

// ── Incremental rendering ────────────────────────────────────────────────────
const PAGE_SIZE    = 50
const visibleCount = ref(PAGE_SIZE)
const sentinel     = ref(null)
let _observer      = null

const visibleEpisodes = computed(() =>
  filteredEpisodes.value.slice(0, visibleCount.value)
)

watch(filteredEpisodes, () => {
  visibleCount.value = PAGE_SIZE
  nextTick(() => {
    if (_observer && sentinel.value) {
      _observer.unobserve(sentinel.value)
      _observer.observe(sentinel.value)
    }
  })
})

watch(sentinel, el => {
  _observer?.disconnect()
  if (!el) return
  _observer = new IntersectionObserver(([entry]) => {
    if (!entry.isIntersecting || visibleCount.value >= filteredEpisodes.value.length) return
    _observer.unobserve(entry.target)
    visibleCount.value += PAGE_SIZE
    nextTick(() => { if (sentinel.value) _observer.observe(sentinel.value) })
  })
  _observer.observe(el)
})
onUnmounted(() => _observer?.disconnect())

function viewEp(ep) {
  router.push('/episode/' + encodeURIComponent(ep.slug))
}
</script>

<template>
  <div class="grid-area overflow-y-auto">
    <!-- Loading skeletons -->
    <div v-if="loading" class="max-w-[900px] mx-auto px-3 pt-3 flex flex-col gap-2">
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
      class="flex flex-col items-center gap-2 py-20 text-base-content/45"
    >
      <Mic :size="40" :stroke-width="1.5" class="opacity-70" />
      <p class="text-sm">Aucun épisode trouvé.</p>
    </div>

    <!-- Feed list -->
    <div
      v-else
      class="max-w-[900px] mx-auto px-3 pt-3 pb-[calc(120px+env(safe-area-inset-bottom,0px))]"
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
