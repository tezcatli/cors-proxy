<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { usePlayerStore } from '../stores/player.js'
import { fetchEpisodes } from '../lib/games.js'
import EpisodeFeedCard from './EpisodeFeedCard.vue'
import { Mic } from 'lucide-vue-next'

const props = defineProps({
  searchQuery: String,
})

const router      = useRouter()
const playerStore = usePlayerStore()

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

function isEpPlaying(ep) {
  return !!playerStore.current && ep.audioUrl === playerStore.current.url
}

function playEp(ep) {
  const primaryGame    = ep.games?.[0]
  const gameSlug       = primaryGame?.slug ?? null
  const primaryChapter = ep.chapters?.find(ch => ch.slug === gameSlug)
  playerStore.play({
    game:            primaryGame?.name || 'Silence on Joue',
    slug:            gameSlug,
    episode:         ep.title,
    url:             ep.audioUrl,
    ts:              0,
    timestamp:       null,
    episodeImageUrl: ep.imageUrl ?? null,
    pubTs:           ep.pubTs,
    episodeSlug:     ep.slug,
    coverImageId:    primaryChapter?.coverImageId ?? null,
    chapters:        ep.chapters ?? [],
  })
}

function viewEp(ep) {
  router.push('/episode/' + encodeURIComponent(ep.slug))
}

function togglePause() { playerStore.setPaused(!playerStore.paused) }
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
          v-for="ep in filteredEpisodes"
          :key="ep.slug"
          :episode="ep"
          :is-playing="isEpPlaying(ep)"
          :is-paused="playerStore.paused"
          @play="playEp"
          @toggle-pause="togglePause"
          @view="viewEp"
        />
      </div>
    </div>
  </div>
</template>
