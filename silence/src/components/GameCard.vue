<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { getScoreClass, formatEpisodeCount } from '../lib/utils.js'
import { useRawg } from '../composables/useRawgImage.js'

const props  = defineProps({ game: Object })
const router = useRouter()

const cardRef                                    = ref(null)
const { data: rawgData, imgUrl, imgFailed, imgLoading, load } = useRawg()

const score      = computed(() => rawgData.value?.metacritic ?? null)
const scoreClass = computed(() => score.value ? getScoreClass(score.value) : '')

async function loadImage() {
  if (imgLoading.value) return
  await load(props.game.name)
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
</script>

<template>
  <div
    ref="cardRef"
    class="group bg-[#16213e] border border-white/[0.08] rounded-xl overflow-hidden cursor-pointer flex flex-col select-none [touch-action:manipulation] [-webkit-tap-highlight-color:transparent] transition duration-[180ms] ease-[ease] hover:border-[rgba(233,69,96,0.5)] hover:shadow-[0_4px_20px_rgba(0,0,0,0.4)] active:scale-[0.97] focus:outline focus:outline-2 focus:outline-[#e94560] focus:outline-offset-2"
    tabindex="0"
    role="button"
    :aria-label="game.name"
    @click="open"
    @keydown="handleKey"
  >
    <div class="w-full aspect-video bg-[#1a2a50] relative overflow-hidden">
      <img
        v-if="imgUrl && !imgFailed"
        class="w-full h-full object-cover block transition-transform duration-[350ms] ease-[ease] group-hover:scale-[1.06]"
        :src="imgUrl"
        :alt="game.name"
        @error="imgFailed = true"
      />
      <div v-if="!imgUrl || imgFailed" class="absolute inset-0 flex items-center justify-center text-[2rem] bg-gradient-to-br from-[#1a2a50] to-[#0f0f1a]" :class="{ skeleton: imgLoading }">
        <template v-if="!imgLoading">🎮</template>
      </div>
      <div v-if="score" class="card-score visible" :class="scoreClass">{{ score }}</div>
    </div>
    <div class="p-2.5 flex-1 flex flex-col gap-[3px]">
      <div class="text-[0.85rem] m-1 font-semibold leading-[1.3] line-clamp-2 lg:text-[0.9rem]">{{ game.name }}</div>
      <div class="text-[0.72rem] m-1 text-[#8888aa] lg:text-[0.76rem]">{{ formatEpisodeCount(game.episodes.length) }}</div>
    </div>
  </div>
</template>
