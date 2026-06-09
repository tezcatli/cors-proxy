<script setup>
import GameCard from './GameCard.vue'
import SkeletonTile from './SkeletonTile.vue'
import { AlertTriangle, SearchX } from 'lucide-vue-next'
import { useInfiniteScroll } from '../composables/useInfiniteScroll.js'

const props = defineProps({
  games:    Array,
  loading:  Boolean,
  error:    String,
  total:    Number,
  resetKey: String,
  hasQuery: Boolean,
})

const { visibleItems: visibleGames, sentinel } = useInfiniteScroll(
  () => props.games,
  { pageSize: 60, resetKey: () => props.resetKey },
)
</script>

<template>
  <div class="grid-area">
    <!-- Loading: skeleton shimmer grid -->
    <div
      v-if="loading"
      class="grid grid-cols-3 gap-2 px-[var(--gutter)] pt-3.5 pb-6  sm:grid-cols-4 sm:gap-3 sm:pt-4 lg:grid-cols-[repeat(auto-fill,minmax(140px,1fr))] lg:gap-4 lg:pt-5"
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
      <p v-else-if="hasQuery" class="text-sm text-center">Aucun jeu ne correspond à votre recherche.</p>
      <p v-else class="text-sm text-center max-w-sm">Aucun jeu résolu pour l'instant. Désactivez « Jeux résolus uniquement » pour voir les autres.</p>
    </div>

    <!-- Grid -->
    <div
      v-else
      class="grid grid-cols-3 gap-2 px-[var(--gutter)] pt-3.5 pb-6  sm:grid-cols-4 sm:gap-3 sm:pt-4 sm:pb-8 lg:grid-cols-[repeat(auto-fill,minmax(140px,1fr))] lg:gap-4 lg:pt-5 lg:pb-10"
    >
      <GameCard v-for="game in visibleGames" :key="game.slug" :game="game" />
    </div>
    <div ref="sentinel" class="h-1" />
  </div>
</template>
