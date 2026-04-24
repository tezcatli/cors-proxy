<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getCachedData } from '../lib/rawg.js'
import { getScoreClass, formatEpisodeCount } from '../lib/utils.js'
import { useGamesStore } from '../stores/games.js'
import { usePlayerStore } from '../stores/player.js'
import EpisodeCard from './EpisodeCard.vue'
import { useRawgImage } from '../composables/useRawgImage.js'

const route       = useRoute()
const router      = useRouter()
const gamesStore  = useGamesStore()
const playerStore = usePlayerStore()

const { imgUrl, imgFailed, load: loadImg } = useRawgImage()
const rawg = ref(null)

// Look up game by slug; wait if store is still loading
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

async function loadRawg(name) {
  rawg.value = getCachedData(name) || null
  await loadImg(name)
  rawg.value = getCachedData(name) || rawg.value
}

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
  <!-- While games are loading on a direct deep-link visit -->
  <div v-if="gamesStore.loading || !game" class="detail-view">
    <div class="detail-topbar">
      <button class="btn-back" @click="close">← Retour</button>
    </div>
    <div class="spinner-wrap" style="flex:1">
      <div v-if="gamesStore.loading" class="spinner"></div>
      <p v-else style="color:var(--text-dim)">Jeu introuvable.</p>
    </div>
  </div>

  <div v-else class="detail-view">
    <!-- Artwork -->
    <div class="detail-artwork">
      <img
        v-if="imgUrl && !imgFailed"
        class="detail-artwork-img"
        :src="imgUrl"
        :alt="game.name"
        @error="imgFailed = true"
      />
      <div v-else class="detail-img-ph">🎮</div>
      <div class="detail-topbar">
        <button class="btn-back" @click="close">← Retour</button>
      </div>
    </div>

    <!-- Info -->
    <div class="detail-informations">
      <div class="detail-title">{{ game.name }}</div>
      <div v-if="rawg" class="detail-rawg-info">
        <div v-if="badges.length" class="rawg-badges">
          <span v-for="b in badges" :key="b.text" class="rawg-badge" :class="b.cls">{{ b.text }}</span>
        </div>
        <div v-if="rawg.developer" class="rawg-developer">{{ rawg.developer }}</div>
        <p   v-if="rawg.description" class="rawg-description">{{ rawg.description }}</p>
      </div>
      <div class="detail-info-footer">
        <span class="detail-ep-count">{{ epCount }}</span>
        <div v-if="nowPlayingTitle" class="detail-now-playing">
          <span class="np-dot">●</span>
          <span class="np-title">{{ nowPlayingTitle }}</span>
        </div>
      </div>
    </div>

    <!-- Episodes -->
    <div class="detail-lecteur">
      <div class="detail-episodes">
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
