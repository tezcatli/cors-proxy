<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { usePlayerStore } from '../stores/player.js'
import { useGamesStore } from '../stores/games.js'
import { fetchGameDetail } from '../lib/games.js'
import { formatDate } from '../lib/utils.js'

const route = useRoute()
const router = useRouter()
const playerStore = usePlayerStore()
const gamesStore = useGamesStore()

const slug = route.params.slug
const pubTs = Number(route.params.pubTs)

const episode = ref(null)
const gameName = ref('')
const loading = ref(true)
const error = ref(null)

onMounted(async () => {
  document.body.style.overflow = 'hidden'
  const storeGame = gamesStore.all.find(g => g.slug === slug)
  gameName.value = storeGame?.name ?? slug
  try {
    const detail = await fetchGameDetail(slug)
    gameName.value = detail.name || gameName.value
    episode.value = detail.episodes.find(ep => ep.pubTs === pubTs) ?? null
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

function back() {
  router.push('/game/' + slug)
}

function onKeydown(e) {
  if (e.key === 'Escape') back()
}

onMounted(() => document.addEventListener('keydown', onKeydown))
onUnmounted(() => {
  document.body.style.overflow = ''
  document.removeEventListener('keydown', onKeydown)
})

const isPlaying = computed(() =>
  !!playerStore.current && playerStore.current.url === episode.value?.audioUrl
)

function playFrom(ts, timestamp) {
  if (!episode.value?.audioUrl) return
  playerStore.play({
    game: slug,
    episode: episode.value.title,
    url: episode.value.audioUrl,
    ts: ts,
    timestamp: timestamp || null,
    coverImageId: playerStore.current?.coverImageId ?? null,
    pubTs: episode.value.pubTs,
  })
}

function togglePlay() {
  if (!episode.value?.audioUrl) return
  if (isPlaying.value) {
    playerStore.setPaused(!playerStore.paused)
    return
  }
  playFrom(episode.value.timestampSeconds || 0, episode.value.timestamp)
}

const playIcon = computed(() => {
  if (!isPlaying.value) return '▶'
  return playerStore.paused ? '▶' : '⏸'
})

function isGameChapter(ch) {
  return episode.value?.timestamp && ch.timestamp === episode.value.timestamp
}

const cleanDescription = computed(() => {
  const raw = episode.value?.description
  const chs = episode.value?.chapters
  if (!raw) return null
  if (!chs?.length) return raw
  const idx = raw.indexOf(chs[0].timestamp)
  return idx > 0 ? raw.slice(0, idx).trimEnd() : raw
})
</script>

<template>
  <!-- Loading / error -->
  <div v-if="loading || error || (!loading && !episode)" class="fixed inset-0 z-[200] bg-base-100 flex flex-col">
    <div class="flex items-center px-4 py-3 border-b border-base-content/10">
      <button class="btn btn-sm btn-ghost" @click="back">← {{ gameName || 'Retour' }}</button>
    </div>
    <div class="flex flex-1 items-center justify-center">
      <span v-if="loading" class="loading loading-spinner loading-lg text-primary" />
      <p v-else-if="error" class="text-base-content/50">Erreur : {{ error }}</p>
      <p v-else class="text-base-content/50">Épisode introuvable.</p>
    </div>
  </div>

  <!-- Main view -->
  <div v-else class="fixed inset-0 z-[200] flex flex-col">

    <!-- Background -->
    <div class="absolute inset-0 overflow-hidden bg-base-100">
      <img v-if="episode.imageUrl" class="w-full h-full object-cover object-center" :src="episode.imageUrl" alt=""
        aria-hidden="true" />
      <div class="absolute inset-0 bg-black/65" />
    </div>

    <!-- Back bar -->
    <div
      class="relative flex items-center px-3 h-11 bg-black/30 backdrop-blur-md border-b border-white/10 flex-shrink-0">
      <button class="btn btn-sm btn-ghost text-white/90 hover:text-white" @click="back">← {{ gameName }}</button>
    </div>

    <!-- Scrollable content -->
    <div class="relative flex-1 overflow-y-auto overscroll-contain">

      <!-- Episode image -->
      <div v-if="episode.imageUrl" class="flex justify-center pt-5 pb-2">
        <img :src="episode.imageUrl" :alt="episode.title"
          class="max-h-80 max-w-[90%] object-contain rounded-xl shadow-2xl" />
      </div>

      <div class="px-4 py-4 pb-28 max-w-2xl mx-auto" >

        <div class="panel p-3" style="margin-bottom: 20px;">

          <!-- Title + date -->
          <h1 class="text-[1.1rem] font-bold leading-snug mb-1">{{ episode.title }}</h1>
          <p class="text-[0.75rem] text-base-content/50 mb-4">{{ formatDate(episode.pubTs) }}</p>

          <!-- Description -->

          <div v-if="cleanDescription" class="ep-desc text-[0.82rem] text-base-content/80 leading-relaxed mb-5"
            v-html="cleanDescription" />

          <!-- Play button -->
          <button v-if="episode.audioUrl && !episode.chapters?.length" class="btn btn-sm btn-primary mb-5 gap-2"
            @click="togglePlay">
            <span>{{ playIcon }}</span>
            <span v-if="episode.timestamp">depuis {{ episode.timestamp }}</span>
            <span v-else>Écouter</span>
          </button>
        </div>

        <!-- Chapters -->
        <div v-if="episode.chapters?.length" class="panel p-3">
          <div class="flex flex-col gap-1">
            <button v-for="ch in episode.chapters" :key="ch.timestamp"
              class="flex items-center gap-2.5 w-full px-2.5 py-2.5 rounded-xl border border-transparent bg-white/15 text-left text-white/65 transition-[background,border-color,color] duration-200 hover:bg-white/[0.09] hover:border-white/10 hover:text-white/85 backdrop-blur-md"
              :class="isGameChapter(ch) ? '!bg-primary/10 !border-primary/30 !text-primary' : ''"
              @click="playFrom(ch.timestampSeconds, ch.timestamp)">
              <span
                class="size-6 flex-shrink-0 rounded-full flex items-center justify-center text-[0.6rem] bg-white/[0.06] border border-white/10">▶</span>
              <span class="font-mono text-[0.7rem] w-12 text-right flex-shrink-0 opacity-50">{{ ch.timestamp }}</span>
              <span class="text-[0.82rem] leading-snug flex-1">{{ ch.title }}</span>
            </button>
          </div>
        </div>

      </div>
    </div>
  </div>
</template>

<style scoped>
.ep-desc :deep(a) {
  color: oklch(var(--p));
  text-decoration: underline;
}

.ep-desc :deep(p) {
  margin-bottom: 0.6rem;
}

.ep-desc :deep(ul),
.ep-desc :deep(ol) {
  padding-left: 1.25rem;
  margin-bottom: 0.6rem;
}

.ep-desc :deep(ul) {
  list-style: disc;
}

.ep-desc :deep(ol) {
  list-style: decimal;
}

.ep-desc :deep(li) {
  margin-bottom: 0.2rem;
}

.ep-desc :deep(strong),
.ep-desc :deep(b) {
  font-weight: 600;
}

.ep-desc :deep(em),
.ep-desc :deep(i) {
  font-style: italic;
}

.ep-desc :deep(br) {
  display: block;
  content: '';
  margin-bottom: 0.3rem;
}
</style>
