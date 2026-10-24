<script setup>
import GameCard from './GameCard.vue'
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
  <div class="scroll-area games-scroll">
    <div class="content">
      <div v-if="!loading && !error && games.length" class="lab grid-count">{{ games.length }} jeux</div>

      <div v-if="loading" class="grid" aria-hidden="true">
        <div v-for="i in 18" :key="i" class="skeleton-shimmer skel__cover" />
      </div>

      <div v-else-if="error || games.length === 0" class="empty">
        <p class="cond empty__title">{{ error ? 'Hors antenne' : 'Rien ici' }}</p>
        <p v-if="error" class="empty__text">{{ error }}</p>
        <p v-else-if="total === 0" class="empty__text">Aucun jeu dans le catalogue. Tirez vers le bas pour actualiser.</p>
        <p v-else-if="hasQuery" class="empty__text">Aucun jeu ne correspond à votre recherche.</p>
        <p v-else class="empty__text">Aucun jeu pour cette émission.</p>
      </div>

      <div v-else class="grid">
        <GameCard v-for="game in visibleGames" :key="game.slug" :game="game" />
      </div>
      <div ref="sentinel" class="h-1" />
    </div>
  </div>
</template>

<style scoped>
.grid-count { padding: 16px 0 12px; }
.grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px 12px;
  padding-top: 4px;
}
@media (min-width: 600px) { .grid { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
@media (min-width: 900px) { .grid { grid-template-columns: repeat(auto-fill, minmax(168px, 1fr)); gap: 28px 24px; } }
.skel__cover { aspect-ratio: 3 / 4; }
.empty { padding: 80px 0; text-align: center; }
.empty__title { font-size: var(--text-2xl); margin: 0 0 8px; }
.empty__text { color: var(--c-fg-2); margin: 0 auto; max-width: 36ch; }
</style>
