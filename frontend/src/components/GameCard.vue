<script setup>
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { getScoreClass, PROGRESS_MIN_PCT } from '../lib/utils.js'
import { igdbUrl } from '../lib/igdbCdn.js'
import placeholderCover from '../assets/placeholder-cover.svg'
import { useArtworkAccent } from '../composables/useArtworkAccent.js'
import { useProgress } from '../composables/useProgress.js'
import { captureSource } from '../lib/flipTransition.js'
import PodcastBadge from './PodcastBadge.vue'

const props       = defineProps({ game: Object })
const router      = useRouter()
const el          = ref(null)
const imgEl       = ref(null)
const inView      = ref(false)

const { gameProgress } = useProgress()

const igdb         = computed(() => props.game?.igdb ?? null)
const coverImageId = computed(() => igdb.value?.coverImageId ?? null)
const score        = computed(() => igdb.value?.metacritic ?? null)
const scoreClass   = computed(() => score.value ? getScoreClass(score.value) : '')

const progress = computed(() => gameProgress(props.game.slug))

// Only run Vibrant palette extraction once the tile has scrolled into view —
// avoids spawning thousands of idle callbacks for off-screen cards. (Covers
// themselves now ship with the catalog, so no per-card fetch is needed.)
const { cssVars } = useArtworkAccent(coverImageId, inView)

function open() {
  captureSource(`cover:${props.game.slug}`, imgEl.value)
  router.push('/game/' + encodeURIComponent(props.game.slug))
}
function handleKey(e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open() } }

let _observer = null

onMounted(() => {
  // Flag the tile visible so accent extraction runs only for on-screen cards.
  _observer = new IntersectionObserver(([entry]) => {
    if (!entry.isIntersecting) return
    inView.value = true
    _observer.disconnect()
    _observer = null
  }, { rootMargin: '300px' })
  _observer.observe(el.value)
})

onUnmounted(() => {
  _observer?.disconnect()
  _observer = null
})
</script>

<template>
  <div
    ref="el"
    class="game-tile"
    :style="cssVars"
    tabindex="0"
    role="button"
    :aria-label="game.name"
    @click="open"
    @keydown="handleKey"
  >
    <img
      ref="imgEl"
      class="game-tile__img"
      :src="coverImageId ? igdbUrl(coverImageId, 't_cover_big') : placeholderCover"
      :srcset="coverImageId
        ? `${igdbUrl(coverImageId,'t_cover_small')} 90w, ${igdbUrl(coverImageId,'t_cover_big')} 264w, ${igdbUrl(coverImageId,'t_cover_big_2x')} 528w`
        : undefined"
      sizes="(min-width:1024px) 176px, (min-width:640px) 23vw, 33vw"
      :alt="game.name"
      loading="lazy"
      decoding="async"
    />

    <div v-if="progress.pct > PROGRESS_MIN_PCT" class="game-tile__progress" :class="{ 'game-tile__progress--done': progress.done }">
      <div class="game-tile__progress-fill" :style="{ width: progress.pct + '%' }"></div>
    </div>

    <div v-if="!coverImageId" class="game-tile__title-fallback">
      <span class="line-clamp-4">{{ game.name }}</span>
    </div>

    <div v-if="game.podcasts?.length" class="game-tile__podcasts">
      <PodcastBadge v-for="p in game.podcasts" :key="p" :id="p" />
    </div>

    <div v-if="score" class="score-arc" :class="scoreClass">{{ score }}</div>

    <div class="game-tile__caption">{{ game.name }}</div>
  </div>
</template>
