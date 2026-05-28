<script setup>
import { ref, computed, watch, nextTick, onUnmounted } from 'vue'
import GameCard from './GameCard.vue'
import SkeletonTile from './SkeletonTile.vue'
import { AlertTriangle, SearchX } from 'lucide-vue-next'

const props = defineProps({
  games:   Array,
  loading: Boolean,
  error:   String,
  total:   Number,
})

const PAGE_SIZE    = 60
const visibleCount = ref(PAGE_SIZE)
const sentinel     = ref(null)
let _observer      = null

const visibleGames = computed(() => props.games.slice(0, visibleCount.value))

watch(() => props.games, () => {
  visibleCount.value = PAGE_SIZE
  nextTick(() => {
    if (_observer && sentinel.value) {
      _observer.unobserve(sentinel.value)
      _observer.observe(sentinel.value)
    }
  })
})

watch(sentinel, el => {
  _observer?.disconnect()
  if (!el) return
  _observer = new IntersectionObserver(([entry]) => {
    if (!entry.isIntersecting || visibleCount.value >= props.games.length) return
    _observer.unobserve(entry.target)
    visibleCount.value += PAGE_SIZE
    nextTick(() => { if (sentinel.value) _observer.observe(sentinel.value) })
  })
  _observer.observe(el)
})
onUnmounted(() => _observer?.disconnect())
</script>

<template>
  <div class="grid-area">
    <!-- Loading: skeleton shimmer grid -->
    <div
      v-if="loading"
      class="grid grid-cols-3 gap-2 px-3 pt-3.5 pb-6  sm:grid-cols-4 sm:gap-3 sm:px-5 sm:pt-4 lg:grid-cols-[repeat(auto-fill,minmax(140px,1fr))] lg:gap-4 lg:px-7 lg:pt-5"
    >
      <SkeletonTile v-for="i in 18" :key="i" />
    </div>

    <!-- Empty / error -->
    <div
      v-else-if="error || games.length === 0"
      class="flex flex-col items-center gap-3 py-20 px-6 text-base-content/50"
    >
      <component :is="error ? AlertTriangle : SearchX" :size="48" :stroke-width="1.5" class="opacity-70" />
      <p v-if="error" class="text-sm text-center max-w-sm">{{ error }}</p>
      <p v-else-if="total === 0" class="text-sm text-center">Aucun jeu dans le catalogue. Essayez d'actualiser.</p>
      <p v-else class="text-sm text-center">Aucun jeu ne correspond à votre recherche.</p>
    </div>

    <!-- Grid -->
    <div
      v-else
      class="grid grid-cols-3 gap-2 px-3 pt-3.5 pb-6  sm:grid-cols-4 sm:gap-3 sm:px-5 sm:pt-4 sm:pb-8 lg:grid-cols-[repeat(auto-fill,minmax(140px,1fr))] lg:gap-4 lg:px-7 lg:pt-5 lg:pb-10"
    >
      <GameCard v-for="game in visibleGames" :key="game.slug" :game="game" />
    </div>
    <div ref="sentinel" class="h-1" />
  </div>
</template>
