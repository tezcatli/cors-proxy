<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { usePlayerStore } from '../stores/player.js'
import { useGamesStore } from '../stores/games.js'
import { fetchEpisodeDetail, fetchGameDetail } from '../lib/games.js'
import { formatDate } from '../lib/utils.js'
import ArtworkBackdrop from './ArtworkBackdrop.vue'
import { useArtworkAccent } from '../composables/useArtworkAccent.js'
import { ArrowLeft, Play, Pause, ExternalLink } from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()
const playerStore = usePlayerStore()
const gamesStore = useGamesStore()

function chapterProgressPct(ch) {
  const chapterTs = ch.timestampSeconds ?? 0
  const live = playerStore.liveProgress
  if (live?.episodeSlug === episode.value?.slug && live.chapterTs === chapterTs) return live.pct
  const p = playerStore.getEpisodeProgress(episode.value?.slug, chapterTs)
  if (!p || !p.chapterEnd) return 0
  const span = p.chapterEnd - (p.ts ?? 0)
  if (span <= 0) return 0
  return Math.min(100, Math.max(0, ((p.currentTime - (p.ts ?? 0)) / span) * 100))
}

const slug        = route.query.game ?? null
const episodeSlug = route.params.episodeSlug

const episode = ref(null)
const gameName = ref('')
const loading = ref(true)
const error = ref(null)

onMounted(async () => {
  document.body.style.overflow = 'hidden'
  try {
    if (slug != null) {
      const detail = await fetchGameDetail(slug)
      gameName.value = detail.name
    }
    episode.value = await fetchEpisodeDetail(episodeSlug)
  } catch (e) {
    console.error('Error fetching episode details:', e)
    error.value = e.message
  } finally {
    loading.value = false
  }
})

function back() {
  if (router.options.history.state?.back) router.back()
  else if (slug) router.push('/game/' + slug)
  else router.push('/episodes')
}

function onKeydown(e) { if (e.key === 'Escape') back() }

onMounted(() => document.addEventListener('keydown', onKeydown))
onUnmounted(() => {
  document.body.style.overflow = ''
  document.removeEventListener('keydown', onKeydown)
})

const gameCoverImageId = computed(() =>
  slug ? (gamesStore.all.find(g => g.slug === slug)?.igdb?.coverImageId ?? null) : null
)

const { cssVars } = useArtworkAccent(gameCoverImageId)

const isPlaying = computed(() =>
  !!playerStore.current && playerStore.current.url === episode.value?.audioUrl
)
const activeChapter = computed(() => isPlaying.value ? playerStore.currentChapter : null)

function playFrom(ts, timestamp) {
  if (!episode.value?.audioUrl) return
  playerStore.play({
    game:            gameName.value,
    slug:            slug,
    episode:         episode.value.title,
    url:             episode.value.audioUrl,
    ts:              ts,
    timestamp:       timestamp || null,
    episodeImageUrl: episode.value.imageUrl,
    pubTs:           episode.value.pubTs,
    episodeSlug:     episode.value.slug,
    coverImageId:    gameCoverImageId.value,
    chapters:        episode.value.chapters ?? [],
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

const playIconComp = computed(() => {
  if (!isPlaying.value) return Play
  return playerStore.paused ? Play : Pause
})

const chapterTitleEls = []
const chapterScrolls  = ref([])

watch(() => episode.value?.chapters, (chs) => {
  if (!chs?.length) { chapterScrolls.value = []; return }
  chapterScrolls.value = chs.map((_, i) => {
    const el = chapterTitleEls[i]
    return !!el && el.scrollWidth > el.clientWidth
  })
}, { flush: 'post' })
</script>

<template>
  <div class="fixed inset-0 z-[200] bg-base-100" :style="cssVars">
    <!-- Loading / error -->
    <div v-if="loading || error || (!loading && !episode)" class="fixed inset-0 z-[200] bg-base-100 flex flex-col">
      <div class="flex items-center px-4 py-3 border-b border-white/5 backdrop-blur-md bg-black/30">
        <button class="btn btn-sm btn-ghost gap-1.5" @click="back">
          <ArrowLeft :size="16" :stroke-width="2.25" /> {{ slug ? (gameName || 'Retour') : 'Épisodes' }}
        </button>
      </div>
      <div class="flex flex-1 items-center justify-center">
        <span v-if="loading" class="loading loading-spinner loading-lg" style="color: var(--game-accent);" />
        <p v-else-if="error" class="text-base-content/50">Erreur : {{ error }}</p>
        <p v-else class="text-base-content/50">Épisode introuvable.</p>
      </div>
    </div>

    <!-- Main view -->
    <div v-else class="fixed inset-0 z-[200] flex flex-col">

      <!-- Hero backdrop: episode image if present, else game cover -->
      <ArtworkBackdrop
        :cover-image-id="gameCoverImageId"
        :fallback-url="episode.imageUrl"
        intensity="hero"
      />

      <!-- Back bar -->
      <div class="relative flex items-center px-3 h-12 bg-black/35 backdrop-blur-xl border-b border-white/5 flex-shrink-0 z-10">
        <button class="btn btn-sm btn-ghost gap-1.5 text-white/85 hover:text-white" @click="back">
          <span class="text-[1rem] leading-none">←</span> {{ slug ? gameName : 'Épisodes' }}
        </button>
      </div>

      <!-- Scrollable content -->
      <div class="relative flex-1 overflow-y-auto overscroll-contain">

        <!-- Episode image -->
        <div v-if="episode.imageUrl" class="flex justify-center pt-6 pb-3">
          <img
            :src="episode.imageUrl"
            :alt="episode.title"
            class="max-h-80 max-w-[88%] object-contain rounded-2xl shadow-e4"
          />
        </div>

        <div class="px-4 py-4 pb-32 max-w-2xl mx-auto">

          <!-- Title + description -->
          <div class="panel p-5 mb-5">
            <h1 class="text-[1.25rem] font-extrabold leading-tight tracking-[-0.015em] mb-1 sm:text-[1.4rem]">
              {{ episode.title }}
            </h1>
            <p class="text-[0.72rem] text-white/45 mb-4 font-medium">
              {{ formatDate(episode.pubTs) }}
            </p>

            <div
              v-if="episode.description"
              class="ep-desc text-[0.86rem] text-white/82 leading-relaxed mb-4"
              v-html="episode.description"
            />

            <button
              v-if="episode.audioUrl && !episode.chapters?.length"
              class="btn btn-sm gap-2 mt-2"
              style="background: var(--game-accent); color: var(--game-accent-fg); border: none;"
              @click="togglePlay"
            >
              <component :is="playIconComp" :size="14" fill="currentColor" :stroke-width="0" />
              <span v-if="episode.timestamp">depuis {{ episode.timestamp }}</span>
              <span v-else>Écouter</span>
            </button>
          </div>

          <!-- Chapters as timeline -->
          <div v-if="episode.chapters?.length" class="panel p-4 pb-5">
            <div class="text-[0.7rem] uppercase tracking-[0.1em] font-bold text-white/45 mb-3 px-1">Chapitres</div>
            <div class="chapter-timeline flex flex-col gap-1.5">
              <button
                v-for="(ch, i) in episode.chapters"
                :key="ch.timestamp"
                type="button"
                class="chapter-row episode-card has-audio w-full text-left"
                :class="{ playing: activeChapter?.timestamp === ch.timestamp }"
                @click="playFrom(ch.timestampSeconds, ch.timestamp)"
              >
                <div class="ep-icon">
                  <component
                    :is="activeChapter?.timestamp === ch.timestamp && !playerStore.paused ? Pause : Play"
                    :size="14"
                    fill="currentColor"
                    :stroke-width="0"
                  />
                </div>
                <span class="font-mono text-[0.7rem] w-12 text-right flex-shrink-0 text-white/45 tabular-nums">
                  {{ ch.timestamp }}
                </span>
                <span
                  :ref="el => { chapterTitleEls[i] = el }"
                  class="ep-ch-scroll"
                  :class="{ 'ep-ch-scroll--on': chapterScrolls[i] }"
                >
                  <span class="ep-ch-inner">{{ ch.title }}</span>
                  <span v-if="chapterScrolls[i]" class="ep-ch-inner" aria-hidden="true">{{ ch.title }}</span>
                </span>
                <RouterLink
                  v-if="ch.slug"
                  :to="`/game/${ch.slug}`"
                  class="flex-shrink-0 ml-1 transition-opacity hover:opacity-100 opacity-70"
                  style="color: var(--game-accent);"
                  @click.stop
                ><ExternalLink :size="14" :stroke-width="2.25" /></RouterLink>
                <div v-if="chapterProgressPct(ch) > 2" class="ep-progress">
                  <div class="ep-progress-fill" :style="{ width: chapterProgressPct(ch) + '%' }"></div>
                </div>
              </button>
            </div>
          </div>

        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ep-desc :deep(a) {
  color: var(--game-accent);
  text-decoration: underline;
  text-underline-offset: 2px;
}
.ep-desc :deep(p)  { margin-bottom: 0.7rem; }
.ep-desc :deep(ul), .ep-desc :deep(ol) { padding-left: 1.25rem; margin-bottom: 0.7rem; }
.ep-desc :deep(ul) { list-style: disc; }
.ep-desc :deep(ol) { list-style: decimal; }
.ep-desc :deep(li) { margin-bottom: 0.25rem; }
.ep-desc :deep(strong), .ep-desc :deep(b) { font-weight: 700; color: #fff; }
.ep-desc :deep(em),     .ep-desc :deep(i) { font-style: italic; }
.ep-desc :deep(br)     { display: block; content: ''; margin-bottom: 0.3rem; }
</style>
