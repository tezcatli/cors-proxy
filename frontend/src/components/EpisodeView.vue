<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { usePlayerStore } from '../stores/player.js'
import { useGamesStore } from '../stores/games.js'
import { fetchEpisodeDetail, fetchGameDetail } from '../lib/games.js'
import { formatDate, formatTime, progressPct, PROGRESS_MIN_PCT, PROGRESS_DONE_PCT } from '../lib/utils.js'
import ArtworkBackdrop from './ArtworkBackdrop.vue'
import Marquee from './Marquee.vue'
import BackBar from './BackBar.vue'
import PodcastBadge from './PodcastBadge.vue'
import { useArtworkAccent } from '../composables/useArtworkAccent.js'
import { useProgress } from '../composables/useProgress.js'
import { Play, Pause, ExternalLink, Check } from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()
const playerStore = usePlayerStore()
const gamesStore = useGamesStore()

const { episodeProgress } = useProgress()

const slug        = route.query.game ?? null
const episodeSlug = route.params.episodeSlug

const episode = ref(null)
const gameName = ref('')
const loading = ref(true)
const error = ref(null)

onMounted(async () => {
  document.body.style.overflow = 'hidden'
  document.addEventListener('keydown', onKeydown)
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
    // Resume from saved progress when partway through; untouched/finished starts at `ts`.
    ts:              playerStore.resumeTimeFor(episode.value.slug, ts),
    timestamp:       timestamp || null,
    episodeImageUrl: episode.value.imageUrl,
    pubTs:           episode.value.pubTs,
    episodeSlug:     episode.value.slug,
    episodeUrlSlug:  episode.value.urlSlug,
    coverImageId:    gameCoverImageId.value,
    chapters:        episode.value.chapters ?? [],
    podcast:         episode.value.podcast ?? null,
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

function onChapterKey(e, ch) {
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); playFrom(ch.timestampSeconds, ch.timestamp) }
}

const playIconComp = computed(() => {
  if (!isPlaying.value) return Play
  return playerStore.paused ? Play : Pause
})

// Chapter rows with their progress precomputed once (avoids re-reading per cell).
const chapterRows = computed(() =>
  (episode.value?.chapters ?? []).map(ch => ({
    ...ch,
    progress: episodeProgress(episode.value.slug, ch.timestampSeconds ?? 0),
  }))
)

// Latest in-progress saved position for this episode → drives the "Reprendre" button.
const resumeEntry = computed(() => {
  if (isPlaying.value) return null
  const e = playerStore.getEpisodeLatestProgress(episode.value?.slug)
  if (!e?.chapterEnd) return null
  const pct = progressPct(e.currentTime, e.ts ?? 0, e.chapterEnd)
  return (pct >= PROGRESS_MIN_PCT && pct < PROGRESS_DONE_PCT) ? e : null
})
</script>

<template>
  <div class="fixed inset-0 z-[var(--z-episode)] bg-base-100" :style="cssVars">
    <!-- Loading / error -->
    <div v-if="loading || error || (!loading && !episode)" class="fixed inset-0 z-[var(--z-episode)] bg-base-100 flex flex-col">
      <BackBar :label="slug ? (gameName || 'Retour') : 'Épisodes'" @back="back" />
      <div class="flex flex-1 items-center justify-center">
        <span v-if="loading" class="loading loading-spinner loading-lg text-game-accent" />
        <p v-else-if="error" class="text-base-content/50">Erreur : {{ error }}</p>
        <p v-else class="text-base-content/50">Épisode introuvable.</p>
      </div>
    </div>

    <!-- Main view -->
    <div v-else class="fixed inset-0 z-[var(--z-episode)] flex flex-col">

      <!-- Hero backdrop: episode image if present, else game cover -->
      <ArtworkBackdrop
        :cover-image-id="gameCoverImageId"
        :fallback-url="episode.imageUrl"
        intensity="hero"
      />

      <!-- Back bar -->
      <BackBar :label="slug ? gameName : 'Épisodes'" @back="back" />

      <!-- Scrollable content -->
      <div class="relative flex-1 overflow-y-auto overscroll-contain pt-[var(--back-clear)]">

        <div class="episode-body" :class="{ 'episode-body--no-image': !episode.imageUrl }">

          <!-- Episode image -->
          <div v-if="episode.imageUrl" class="episode-body__image">
            <img
              :src="episode.imageUrl"
              :alt="episode.title"
              class="rounded-2xl shadow-e4"
            />
          </div>

          <!-- Title + description -->
          <div class="episode-body__meta panel p-5">
            <h1 class="text-[1.25rem] font-extrabold leading-tight tracking-[-0.015em] mb-1 sm:text-[1.4rem]">
              {{ episode.title }}
            </h1>
            <p class="text-[0.72rem] text-white/45 mb-4 font-medium flex items-center gap-2">
              <PodcastBadge v-if="episode.podcast" :id="episode.podcast.id" />
              {{ formatDate(episode.pubTs) }}
            </p>

            <div
              v-if="episode.description"
              class="ep-desc text-[0.86rem] text-white/82 leading-relaxed mb-4"
              v-html="episode.description"
            />

            <button
              v-if="episode.audioUrl && resumeEntry"
              class="ep-cta btn btn-sm gap-2 mt-2"
              @click="playFrom(resumeEntry.ts, null)"
            >
              <Play :size="14" fill="currentColor" :stroke-width="0" />
              <span>Reprendre à {{ formatTime(resumeEntry.currentTime) }}</span>
            </button>
            <button
              v-else-if="episode.audioUrl && !episode.chapters?.length"
              class="ep-cta btn btn-sm gap-2 mt-2"
              @click="togglePlay"
            >
              <component :is="playIconComp" :size="14" fill="currentColor" :stroke-width="0" />
              <span v-if="episode.timestamp">depuis {{ episode.timestamp }}</span>
              <span v-else>Écouter</span>
            </button>
          </div>

          <!-- Chapters as timeline -->
          <div v-if="episode.chapters?.length" class="episode-body__chapters panel p-5">
            <div class="text-[0.7rem] uppercase tracking-[0.1em] font-bold text-white/45 mb-3 px-1">Chapitres</div>
            <div class="chapter-timeline flex flex-col gap-1.5">
              <div
                v-for="ch in chapterRows"
                :key="ch.timestamp"
                class="chapter-row episode-card has-audio w-full text-left"
                :class="{ playing: activeChapter?.timestamp === ch.timestamp }"
                role="button"
                tabindex="0"
                @click="playFrom(ch.timestampSeconds, ch.timestamp)"
                @keydown="e => onChapterKey(e, ch)"
              >
                <div class="ep-icon">
                  <component
                    :is="activeChapter?.timestamp === ch.timestamp && !playerStore.paused ? Pause : Play"
                    :size="14"
                    fill="currentColor"
                    :stroke-width="0"
                  />
                </div>
                <span class="font-mono text-[0.7rem] w-14 text-right flex-shrink-0 text-white/45 tabular-nums">
                  {{ ch.timestamp }}
                </span>
                <Marquee :text="ch.title" class="flex-1" inner-class="ep-ch" />
                <Check
                  v-if="ch.progress.done"
                  :size="14" :stroke-width="3"
                  class="text-game-accent flex-shrink-0 ml-1"
                  aria-label="Écouté"
                />
                <RouterLink
                  v-if="ch.slug"
                  :to="`/game/${ch.slug}`"
                  class="text-game-accent flex-shrink-0 ml-1 transition-opacity hover:opacity-100 opacity-70"
                  @click.stop
                ><ExternalLink :size="14" :stroke-width="2.25" /></RouterLink>
                <div v-if="ch.progress.pct > PROGRESS_MIN_PCT" class="ep-progress" :class="{ 'ep-progress--done': ch.progress.done }">
                  <div class="ep-progress-fill" :style="{ width: ch.progress.pct + '%' }"></div>
                </div>
              </div>
            </div>
          </div>

        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Accent call-to-action button (Reprendre / Écouter) */
.ep-cta {
  background: var(--game-accent);
  color: var(--game-accent-fg);
  border: none;
}
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
