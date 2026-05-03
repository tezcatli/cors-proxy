<script setup>
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { getScoreClass } from '../lib/utils.js'
import { igdbUrl } from '../lib/igdbCdn.js'
import placeholderCover from '../assets/placeholder-cover.svg'
import { useGamesStore } from '../stores/games.js'

const props      = defineProps({ game: Object })
const router     = useRouter()
const gamesStore = useGamesStore()
const el         = ref(null)

const igdb         = computed(() => props.game?.igdb ?? null)
const coverImageId = computed(() => igdb.value?.coverImageId ?? null)
const score        = computed(() => igdb.value?.metacritic ?? null)
const scoreClass   = computed(() => score.value ? getScoreClass(score.value) : '')

function open() { router.push('/game/' + encodeURIComponent(props.game.name)) }
function handleKey(e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open() } }

let _observer = null

onMounted(() => {
  if (coverImageId.value) return   // already fully loaded
  _observer = new IntersectionObserver(([entry]) => {
    if (entry.isIntersecting) {
      gamesStore.queueIgdb(props.game.name)
      _observer.disconnect()
      _observer = null
    }
  }, { rootMargin: '200px' })
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
    class="relative aspect-[45/64] bg-[#1a2a50] rounded-lg overflow-hidden cursor-pointer select-none [touch-action:manipulation] [-webkit-tap-highlight-color:transparent] transition duration-[180ms] ease-[ease] hover:brightness-110 hover:shadow-[0_4px_20px_rgba(0,0,0,0.5)] active:scale-[0.97] focus:outline focus:outline-2 focus:outline-[#e94560] focus:outline-offset-2"
    tabindex="0"
    role="button"
    :aria-label="game.name"
    @click="open"
    @keydown="handleKey"
  >
    <img
      class="w-full h-full object-cover block"
      :src="coverImageId ? igdbUrl(coverImageId, 't_cover_big_2x') : placeholderCover"
      :srcset="coverImageId
        ? `${igdbUrl(coverImageId,'t_cover_small')} 128h, ${igdbUrl(coverImageId,'t_cover_big')} 374h, ${igdbUrl(coverImageId,'t_cover_big_2x')} 748h`
        : undefined"
      :alt="game.name"
    />
    <div v-if="score" class="card-score visible" :class="scoreClass">{{ score }}</div>
  </div>
</template>
