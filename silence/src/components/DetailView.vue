<script setup>
import { computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getScoreClass, formatEpisodeCount } from '../lib/utils.js'
import { useGamesStore } from '../stores/games.js'
import { usePlayerStore } from '../stores/player.js'
import EpisodeCard from './EpisodeCard.vue'
import { useRawg } from '../composables/useRawgImage.js'

const route       = useRoute()
const router      = useRouter()
const gamesStore  = useGamesStore()
const playerStore = usePlayerStore()

const { data: rawg, imgUrl, imgFailed, load: loadRawg } = useRawg()

const game = computed(() => {
  const name = decodeURIComponent(route.params.slug)
  return gamesStore.all.find(g => g.name === name) ?? null
})

const epCount = computed(() => formatEpisodeCount(game.value?.episodes?.length ?? 0))

const nowPlayingTitle = computed(() => {
  if (!playerStore.current || !game.value) return null
  return game.value.episodes.find(e => e.audioUrl === playerStore.current.url)?.title ?? null
})

function isEpPlaying(ep) {
  return !!playerStore.current && ep.audioUrl === playerStore.current.url
}

function playEp(ep) {
  playerStore.play({
    game:      game.value.name,
    episode:   ep.title,
    url:       ep.audioUrl,
    ts:        ep.timestampSeconds || 0,
    timestamp: ep.timestamp || null,
  })
}

function togglePause() { playerStore.setPaused(!playerStore.paused) }

watch(game, g => { if (g) loadRawg(g.name) }, { immediate: true })

function close() { router.push('/') }

function onKeydown(e) { if (e.key === 'Escape') close() }
onMounted(() => {
  document.body.style.overflow = 'hidden'
  document.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  document.body.style.overflow = ''
  document.removeEventListener('keydown', onKeydown)
})

const badges = computed(() => {
  if (!rawg.value) return []
  const { metacritic, rating, released, esrb, playtime, genres, platforms } = rawg.value
  const list = []
  if (metacritic) list.push({ text: `Metacritic ${metacritic}`, cls: getScoreClass(metacritic) })
  if (rating)     list.push({ text: `★ ${rating}/5`, cls: 'rawg-rating' })
  if (released)   list.push({ text: released })
  if (esrb)       list.push({ text: esrb })
  if (playtime)   list.push({ text: `~${playtime}h` })
  if (genres?.length)    list.push({ text: genres.join(' · ') })
  if (platforms?.length) list.push({ text: platforms.join(' · ') })
  return list
})
</script>

<template>
  <!-- Loading / not found -->
  <div v-if="gamesStore.loading || !game" class="fixed inset-0 z-[150] bg-base-100 flex flex-col">
    <div class="flex items-center px-4 py-3 border-b border-base-content/10">
      <button class="btn btn-sm btn-ghost" @click="close">← Retour</button>
    </div>
    <div class="flex flex-1 items-center justify-center">
      <span v-if="gamesStore.loading" class="loading loading-spinner loading-lg text-primary"></span>
      <p v-else class="text-base-content/50">Jeu introuvable.</p>
    </div>
  </div>

  <!-- Main view -->
  <div v-else class="fixed inset-0 z-[150] overflow-y-auto bg-base-100">

    <!-- Sticky back bar -->
    <div class="sticky top-0 z-10 flex items-center px-3 h-11 bg-base-100/80 backdrop-blur-sm border-b border-base-content/[0.06]">
      <button class="btn btn-sm btn-ghost" @click="close">← Retour</button>
    </div>

    <!-- Artwork (bounded height, full-bleed) -->
    <div class="detail-artwork">
      <img
        v-if="imgUrl && !imgFailed"
        class="absolute inset-0 w-full h-full object-cover object-center block"
        :src="imgUrl"
        :alt="game.name"
        @error="imgFailed = true"
      />
      <div v-else class="absolute inset-0 flex items-center justify-center text-[5rem] bg-gradient-to-br from-base-300 to-base-100">🎮</div>
    </div>

    <!-- Info -->
    <div class="flex-shrink-0 px-5 py-4 bg-base-100 border-t border-base-content/10 sm:px-6 lg:px-7">

      <!-- Title row -->
      <div class="flex items-start justify-between gap-4 mb-2">
        <h2 class="text-[1.35rem] font-extrabold leading-tight line-clamp-2 sm:text-[1.65rem] lg:text-[1.9rem]">{{ game.name }}</h2>
        <span class="text-[0.68rem] text-base-content/40 font-semibold uppercase tracking-wide flex-shrink-0 mt-1">{{ epCount }}</span>
      </div>

      <!-- Badges + developer -->
      <div v-if="rawg && (badges.length || rawg.developer)" class="flex flex-wrap items-center gap-1.5 mb-2">
        <span v-for="b in badges" :key="b.text" class="badge badge-sm rawg-badge" :class="b.cls">{{ b.text }}</span>
        <span v-if="rawg.developer" class="text-[0.72rem] text-base-content/40">{{ rawg.developer }}</span>
      </div>

      <!-- Description + now-playing -->
      <div class="flex items-end gap-4">
        <p v-if="rawg?.description" class="text-[0.78rem] text-base-content/50 leading-relaxed line-clamp-8 flex-1 min-w-0">{{ rawg.description }}</p>
        <!--
        <div v-if="nowPlayingTitle" class="flex items-center gap-1.5 text-[0.72rem] text-secondary flex-shrink-0 max-w-[45%] min-w-0">
          <span class="text-[0.5rem] flex-shrink-0">●</span>
          <span class="truncate">{{ nowPlayingTitle }}</span>
        </div>
        -->
      </div>

    </div>

    <!-- Episodes -->
    <div class="detail-lecteur">
      <div class="flex flex-col gap-0.5">
        <EpisodeCard
          v-for="ep in game.episodes"
          :key="ep.title"
          :episode="ep"
          :game-name="game.name"
          :is-playing="isEpPlaying(ep)"
          :is-paused="playerStore.paused"
          @play="playEp"
          @toggle-pause="togglePause"
        />
      </div>
    </div>

  </div>
</template>
