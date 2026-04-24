<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { getCachedMeta } from '../lib/rawg.js'
import { getScoreClass, formatEpisodeCount } from '../lib/utils.js'
import { useRawgImage } from '../composables/useRawgImage.js'

const props  = defineProps({ game: Object })
const router = useRouter()

const cardRef                          = ref(null)
const { imgUrl, imgFailed, imgLoading, load } = useRawgImage()
const score      = ref(null)
const scoreClass = ref('')

async function loadImage() {
  if (imgLoading.value) return
  await load(props.game.name)
  const meta = getCachedMeta(props.game.name)
  if (meta) { score.value = meta; scoreClass.value = getScoreClass(meta) }
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
    class="game-card"
    tabindex="0"
    role="button"
    :aria-label="game.name"
    @click="open"
    @keydown="handleKey"
  >
    <div class="card-img-wrap">
      <img
        v-if="imgUrl && !imgFailed"
        class="card-img"
        :src="imgUrl"
        :alt="game.name"
        @error="imgFailed = true"
      />
      <div v-if="!imgUrl || imgFailed" class="card-ph" :class="{ loading: imgLoading }">
        <template v-if="!imgLoading">🎮</template>
      </div>
      <div v-if="score" class="card-score visible" :class="scoreClass">{{ score }}</div>
    </div>
    <div class="card-body">
      <div class="card-name">{{ game.name }}</div>
      <div class="card-meta">{{ formatEpisodeCount(game.episodes.length) }}</div>
    </div>
  </div>
</template>
