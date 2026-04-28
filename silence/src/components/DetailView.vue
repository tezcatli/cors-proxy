<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getScoreClass, formatEpisodeCount, gameYear } from '../lib/utils.js'
import { igdbUrl } from '../lib/igdbCdn.js'
import placeholderCover from '../assets/placeholder-cover.svg'
import placeholderBg    from '../assets/placeholder-bg.svg'
import { useGamesStore } from '../stores/games.js'
import { usePlayerStore } from '../stores/player.js'
import EpisodeCard from './EpisodeCard.vue'
import { useRawg } from '../composables/useIgdb.js'

const route       = useRoute()
const router      = useRouter()
const gamesStore  = useGamesStore()
const playerStore = usePlayerStore()

const { data: igdb, coverImageId, bgImageId, imgFailed, imgLoading, load: loadRawg } = useRawg()
const coverFailed = imgFailed
const bgFailed    = ref(false)

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
    game:         game.value.name,
    episode:      ep.title,
    url:          ep.audioUrl,
    ts:           ep.timestampSeconds || 0,
    timestamp:    ep.timestamp || null,
    coverImageId: coverImageId.value ?? null,
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
        :src="bgImageId && !bgFailed ? igdbUrl(bgImageId, 't_1080p') : placeholderBg"
        :srcset="bgImageId && !bgFailed
          ? `${igdbUrl(bgImageId,'t_720p')} 1280w, ${igdbUrl(bgImageId,'t_1080p')} 1920w, ${igdbUrl(bgImageId,'t_720p_2x')} 2560w, ${igdbUrl(bgImageId,'t_1080p_2x')} 3840w`
          : undefined"
        sizes="100vw"
        alt=""
        aria-hidden="true"
        @error="bgFailed = true"
      />
      <div class="absolute inset-0 bg-black/55" />
    </div>

    <!-- Content (scrollable on mobile, split on landscape desktop) -->
    <div class="detail-content relative h-full flex flex-col">

      <!-- Back bar -->
      <div class="sticky top-0 z-10 flex items-center px-3 h-11 bg-black/30 backdrop-blur-md border-b border-white/10 flex-shrink-0">
        <button class="btn btn-sm btn-ghost text-white/90 hover:text-white" @click="close">← Retour</button>
      </div>

      <!-- Body -->
      <div class="detail-body">

        <!-- Cover column (left on landscape desktop, inline on mobile) -->
        <div class="detail-cover-col">
          <div class="detail-cover-card">
            <img
              class="w-full h-full object-cover block"
              :src="coverImageId && !coverFailed ? igdbUrl(coverImageId, 't_cover_big') : placeholderCover"
              :srcset="coverImageId && !coverFailed
                ? `${igdbUrl(coverImageId,'t_cover_big')} 374w, ${igdbUrl(coverImageId,'t_cover_big_2x')} 748w`
                : undefined"
              :alt="game.name"
              @error="coverFailed = true"
            />
          </div>
        </div>

        <!-- Scroll column (right on landscape desktop, below on mobile) -->
        <div class="detail-scroll-col">
        <div class="detail-scroll-inner">

          <!-- Info panel -->
          <div class="detail-glass mx-4 mb-3 mt-4">
            <div class="flex items-start justify-between gap-3 mb-2">
              <h2 class="text-[1.2rem] font-extrabold leading-tight sm:text-[1.45rem]">{{ game.name }}</h2>
              <span class="text-[0.65rem] text-white/50 font-semibold uppercase tracking-wide flex-shrink-0 mt-1">{{ epCount }}</span>
            </div>

            <!-- Prominent scores (landscape desktop only) -->
            <div v-if="igdb?.metacritic || igdb?.rating" class="detail-scores">
              <div v-if="igdb?.metacritic" class="score-block" :class="getScoreClass(igdb.metacritic)">
                <span class="score-number">{{ igdb.metacritic }}</span>
                <span class="score-label">Metacritic</span>
              </div>
              <div v-if="igdb?.rating" class="score-block igdb-rating">
                <span class="score-number">{{ igdb.rating }}</span>
                <span class="score-label">IGDB</span>
              </div>
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
    </div>
  </div>
</div>
</template>
