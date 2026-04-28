<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { getScoreClass, gameYear } from '../lib/utils.js'
import { useRawg } from '../composables/useIgdb.js'
import { igdbUrl } from '../lib/igdbCdn.js'
import placeholderCover from '../assets/placeholder-cover.svg'

const props  = defineProps({ game: Object })
const router = useRouter()

const cardRef                                                         = ref(null)
const { data: igdbData, coverImageId, imgFailed, imgLoading, load } = useRawg()

const score      = computed(() => igdbData.value?.metacritic ?? null)
const scoreClass = computed(() => score.value ? getScoreClass(score.value) : '')

async function loadImage() {
  if (imgLoading.value) return
  await load(props.game.name, gameYear(props.game.episodes))
}

let observer
onMounted(() => {
  observer = new IntersectionObserver(entries => {
    for (const { isIntersecting, target } of entries) {
      if (!isIntersecting) continue
      observer.unobserve(target)
      loadImage()
    }
  }, { rootMargin: '300px' })
  observer.observe(cardRef.value)
})
onUnmounted(() => observer?.disconnect())

function open() { router.push('/game/' + encodeURIComponent(props.game.name)) }
function handleKey(e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open() } }
function prefetch() { loadImage() }
</script>

<template>
  <div
    ref="cardRef"
    class="relative aspect-[45/64] bg-[#1a2a50] rounded-lg overflow-hidden cursor-pointer select-none [touch-action:manipulation] [-webkit-tap-highlight-color:transparent] transition duration-[180ms] ease-[ease] hover:brightness-110 hover:shadow-[0_4px_20px_rgba(0,0,0,0.5)] active:scale-[0.97] focus:outline focus:outline-2 focus:outline-[#e94560] focus:outline-offset-2"
    tabindex="0"
    role="button"
    :aria-label="game.name"
    @click="open"
    @keydown="handleKey"
    @mouseenter="prefetch"
    @touchstart.passive="prefetch"
  >
    <img
      v-if="!imgLoading"
      class="w-full h-full object-cover block"
      :src="coverImageId && !imgFailed ? igdbUrl(coverImageId, 't_cover_big_2x') : placeholderCover"
      :srcset="coverImageId && !imgFailed
        ? `${igdbUrl(coverImageId,'t_cover_small')} 128h, ${igdbUrl(coverImageId,'t_cover_big')} 374h, ${igdbUrl(coverImageId,'t_cover_big_2x')} 748h`
        : undefined"
      :alt="game.name"
      @error="imgFailed = true"
    />
    <div v-if="imgLoading" class="absolute inset-0 skeleton"/>
    <div v-if="score" class="card-score visible" :class="scoreClass">{{ score }}</div>
  </div>
</template>
