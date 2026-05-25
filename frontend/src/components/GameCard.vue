<script setup>
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { getScoreClass } from '../lib/utils.js'
import { igdbUrl } from '../lib/igdbCdn.js'
import placeholderCover from '../assets/placeholder-cover.svg'
import { useGamesStore } from '../stores/games.js'
import { useArtworkAccent } from '../composables/useArtworkAccent.js'
import { captureSource } from '../lib/flipTransition.js'

const props      = defineProps({ game: Object })
const router     = useRouter()
const gamesStore = useGamesStore()
const el         = ref(null)
const imgEl      = ref(null)
const inView     = ref(false)

const igdb         = computed(() => props.game?.igdb ?? null)
const coverImageId = computed(() => igdb.value?.coverImageId ?? null)
const score        = computed(() => igdb.value?.metacritic ?? null)
const scoreClass   = computed(() => score.value ? getScoreClass(score.value) : '')

// Only run Vibrant palette extraction once the tile has scrolled into view —
// avoids spawning thousands of idle callbacks for off-screen cards.
const { cssVars } = useArtworkAccent(coverImageId, inView)

function open() {
  captureSource(`cover:${props.game.slug}`, imgEl.value)
  router.push('/game/' + encodeURIComponent(props.game.slug))
}
function handleKey(e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open() } }

let _observer = null

onMounted(() => {
  // One observer that handles both visibility flagging (for accent extraction)
  // and IGDB queueing for tiles that don't yet have cover data.
  _observer = new IntersectionObserver(([entry]) => {
    if (!entry.isIntersecting) return
    inView.value = true
    if (!coverImageId.value) gamesStore.queueIgdb(props.game.slug)
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
      :src="coverImageId ? igdbUrl(coverImageId, 't_cover_big_2x') : placeholderCover"
      :srcset="coverImageId
        ? `${igdbUrl(coverImageId,'t_cover_small')} 90w 128h, ${igdbUrl(coverImageId,'t_cover_big')} 264w 374h, ${igdbUrl(coverImageId,'t_cover_big_2x')} 528w 748h`
        : undefined"
      :alt="game.name"
      loading="lazy"
      decoding="async"
    />

    <div v-if="!coverImageId" class="game-tile__title-fallback">
      <span class="line-clamp-4">{{ game.name }}</span>
    </div>

    <div v-if="score" class="score-arc" :class="scoreClass">{{ score }}</div>

    <div class="game-tile__caption">{{ game.name }}</div>
  </div>
</template>
