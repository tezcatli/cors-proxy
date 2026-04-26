<script setup>
import GameCard from './GameCard.vue'

defineProps({
  games:   Array,
  loading: Boolean,
  error:   String,
  total:   Number,
})
</script>

<template>
  <div class="grid-area">
    <div v-if="loading" class="flex justify-center py-16">
      <span class="loading loading-spinner loading-lg text-primary"></span>
    </div>

    <div v-else-if="error || games.length === 0" class="flex flex-col items-center gap-3 py-16 px-6 text-base-content/50">
      <span class="text-4xl">{{ error ? '⚠️' : '🔍' }}</span>
      <p v-if="error">{{ error }}</p>
      <p v-else-if="total === 0">Aucun jeu dans le catalogue. Essayez d'actualiser.</p>
      <p v-else>Aucun jeu ne correspond à votre recherche.</p>
    </div>

    <!--
    <div v-else class="grid grid-cols-2 gap-2.5 px-3 pt-3.5 pb-6 max-w-[1400px] mx-auto sm:grid-cols-3 sm:gap-3.5 sm:px-5 sm:pt-4 
    sm:pb-7 lg:grid-cols-[repeat(auto-fill,minmax(200px,1fr))] lg:gap-[18px] lg:px-7 lg:pt-5 lg:pb-10 xl:grid-cols-[repeat(auto-fill,minmax(220px,1fr))]">
      <GameCard v-for="game in games" :key="game.name" :game="game" />
    </div>
    -->
    <div v-else class="grid grid-cols-2 gap-2.5 px-3 pt-3.5 pb-6 max-w-[1400px] mx-auto sm:grid-cols-3 sm:gap-3.5 sm:px-5 sm:pt-4 
    sm:pb-7 lg:grid-cols-[repeat(auto-fill,minmax(200px,1fr))] lg:gap-[18px] lg:px-7 lg:pt-5 lg:pb-10 xl:grid-cols-[repeat(auto-fill,minmax(220px,1fr))]">
      <GameCard v-for="game in games" :key="game.name" :game="game" />
    </div>
  </div>
</template>
