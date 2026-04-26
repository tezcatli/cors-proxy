<script setup>
import { computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getScoreClass, formatEpisodeCount, gameYear } from '../lib/utils.js'
import placeholderCover from '../assets/placeholder-cover.svg'
import placeholderBg    from '../assets/placeholder-bg.svg'
import { useGamesStore } from '../stores/games.js'
import { usePlayerStore } from '../stores/player.js'
import EpisodeCard from './EpisodeCard.vue'
import { useRawg } from '../composables/useRawgImage.js'

const route       = useRoute()
const router      = useRouter()
const gamesStore  = useGamesStore()
const playerStore = usePlayerStore()

const { data: igdb, imgUrl, imgFailed, load: loadRawg } = useRawg()

const game = computed(() => {
  const name = decodeURIComponent(route.params.slug)
  return gamesStore.all.find(g => g.name === name) ?? null
})

const epCount = computed(() => formatEpisodeCount(game.value?.episodes?.length ?? 0))

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

watch(game, g => { if (g) loadRawg(g.name, gameYear(g.episodes)) }, { immediate: true })

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
  if (!igdb.value) return []
  const { metacritic, rating, released, esrb, genres, platforms } = igdb.value
  const list = []
  if (metacritic) list.push({ text: `Metacritic ${metacritic}`, cls: getScoreClass(metacritic) })
  if (rating)     list.push({ text: `★ ${rating}/5`, cls: 'igdb-rating' })
  if (released)   list.push({ text: released })
  if (esrb)       list.push({ text: esrb })
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
  <div v-else class="fixed inset-0 z-[150]">

    <!-- Background -->
    <div class="absolute inset-0 overflow-hidden">
      <img
        class="w-full h-full object-cover object-center"
        :src="imgUrl && !imgFailed ? imgUrl : placeholderBg"
        alt=""
        aria-hidden="true"
      />
      <div class="absolute inset-0 bg-black/55" />
    </div>

    <!-- Content (scrollable over background) -->
    <div class="relative h-full overflow-y-auto flex flex-col">

      <!-- Sticky back bar -->
      <div class="sticky top-0 z-10 flex items-center px-3 h-11 bg-black/30 backdrop-blur-md border-b border-white/10 flex-shrink-0">
        <button class="btn btn-sm btn-ghost text-white/90 hover:text-white" @click="close">← Retour</button>
      </div>

      <!-- Cover card (centered, h ≈ 33vh) -->
      <div class="flex justify-center px-4 pt-5 pb-3 flex-shrink-0">
        <div class="detail-cover-card">
          <img
            class="w-full h-full object-cover block"
            :src="imgUrl && !imgFailed ? imgUrl : placeholderCover"
            :alt="game.name"
            @error="imgFailed = true"
          />
        </div>
      </div>

      <!-- Info panel (glass) -->
      <div class="detail-glass mx-4 mb-3">
        <div class="flex items-start justify-between gap-3 mb-2">
          <h2 class="text-[1.2rem] font-extrabold leading-tight sm:text-[1.45rem]">{{ game.name }}</h2>
          <span class="text-[0.65rem] text-white/50 font-semibold uppercase tracking-wide flex-shrink-0 mt-1">{{ epCount }}</span>
        </div>
        <div v-if="badges.length || igdb?.developer" class="flex flex-wrap items-center gap-1.5 mb-2">
          <span v-for="b in badges" :key="b.text" class="badge badge-sm igdb-badge" :class="b.cls">{{ b.text }}</span>
          <span v-if="igdb?.developer" class="text-[0.7rem] text-white/40">{{ igdb.developer }}</span>
        </div>
        <p v-if="igdb?.description" class="text-[0.78rem] text-white/60 leading-relaxed line-clamp-4">{{ igdb.description }}</p>
      </div>

      <!-- Episodes -->
      <div class="detail-lecteur mx-4 mb-4">
        <div class="flex flex-col gap-1.5">
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
  </div>
</template>
