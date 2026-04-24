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
    <div v-if="loading" class="spinner-wrap">
      <div class="spinner"></div>
    </div>

    <div v-else-if="error || games.length === 0" class="empty-state">
      <span>{{ error ? '⚠️' : '🔍' }}</span>
      <p v-if="error">{{ error }}</p>
      <p v-else-if="total === 0">Aucun jeu dans le catalogue. Essayez d'actualiser.</p>
      <p v-else>Aucun jeu ne correspond à votre recherche.</p>
    </div>

    <div v-else class="game-grid">
      <GameCard v-for="game in games" :key="game.name" :game="game" />
    </div>
  </div>
</template>
