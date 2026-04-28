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

const { data: igdb, coverImageId, bgImageId, imgFailed, imgLoading, loadError, load: loadRawg } = useRawg()
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

const descExpanded       = ref(false)
const selectedScreenshot = ref(null)

watch(game, g => {
  if (g) {
    descExpanded.value      = false
    selectedScreenshot.value = null
    loadRawg(g.name, gameYear(g.episodes))
  }
}, { immediate: true })

function retryIgdb() { if (game.value) loadRawg(game.value.name, gameYear(game.value.episodes)) }

function close() { router.push('/') }

function onKeydown(e) {
  if (selectedScreenshot.value) {
    if (e.key === 'Escape')     { closeScreenshot(); return }
    if (e.key === 'ArrowLeft')  prevScreenshot()
    if (e.key === 'ArrowRight') nextScreenshot()
    return
  }
  if (e.key === 'Escape') close()
}
onMounted(() => {
  document.body.style.overflow = 'hidden'
  document.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  document.body.style.overflow = ''
  document.removeEventListener('keydown', onKeydown)
})

function openScreenshot(id) { selectedScreenshot.value = id }
function closeScreenshot()  { selectedScreenshot.value = null }

function prevScreenshot() {
  const ids = igdb.value?.screenshotIds
  if (!ids?.length) return
  const i = ids.indexOf(selectedScreenshot.value)
  selectedScreenshot.value = ids[(i - 1 + ids.length) % ids.length]
}

function nextScreenshot() {
  const ids = igdb.value?.screenshotIds
  if (!ids?.length) return
  const i = ids.indexOf(selectedScreenshot.value)
  selectedScreenshot.value = ids[(i + 1) % ids.length]
}

const badges = computed(() => {
  if (!igdb.value) return []
  const { metacritic, rating, released, esrb, genres, platforms, modes } = igdb.value
  const list = []
  if (metacritic) list.push({ text: `Metacritic ${metacritic}`, cls: getScoreClass(metacritic) })
  if (rating)     list.push({ text: `★ ${rating}/5`, cls: 'igdb-rating' })
  if (released)   list.push({ text: released })
  if (esrb)       list.push({ text: esrb })
  if (genres?.length)    list.push({ text: genres.join(' · ') })
  if (platforms?.length) list.push({ text: platforms.join(' · ') })
  if (modes?.length)     list.push({ text: modes.join(' · ') })
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

            <!-- IGDB fetch error -->
            <p v-if="loadError" class="text-[0.72rem] text-white/40 mb-2">
              Données IGDB indisponibles.
              <button class="text-primary/70 hover:text-primary transition-colors" @click="retryIgdb">Réessayer</button>
            </p>

            <!-- IGDB loading skeleton -->
            <div v-else-if="imgLoading" class="flex flex-col gap-2 mb-3">
              <div class="skeleton h-3 w-24 rounded opacity-30"/>
              <div class="skeleton h-3 w-36 rounded opacity-30"/>
              <div class="skeleton h-3 w-28 rounded opacity-30"/>
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
              <span v-if="igdb?.developer" class="text-[0.7rem] text-white/40">
                {{ igdb.developer }}<template v-if="igdb.publisher && igdb.publisher !== igdb.developer"> · {{ igdb.publisher }}</template>
              </span>
              <a v-if="igdb?.steamUrl" :href="igdb.steamUrl" target="_blank" rel="noopener noreferrer"
                 class="text-[0.68rem] text-white/30 hover:text-primary ml-auto flex-shrink-0 transition-colors">Steam ↗</a>
            </div>
            <div v-if="igdb?.description">
              <p class="text-[0.78rem] text-white/60 leading-relaxed" :class="{ 'line-clamp-4': !descExpanded }">{{ igdb.description }}</p>
              <button v-if="igdb.description.length > 280" class="btn btn-xs btn-ghost text-white/50 hover:text-white/90 mt-1 px-0" @click="descExpanded = !descExpanded">
                {{ descExpanded ? 'Voir moins' : 'Voir plus' }}
              </button>
            </div>
          </div>

          <!-- Screenshot strip -->
          <div v-if="igdb?.screenshotIds?.length" class="mx-4 mb-3">
            <div class="screenshot-scroll">
              <img
                v-for="id in igdb.screenshotIds"
                :key="id"
                class="screenshot-thumb"
                :src="igdbUrl(id, 't_screenshot_med')"
                :srcset="`${igdbUrl(id, 't_screenshot_med')} 1x, ${igdbUrl(id, 't_screenshot_big')} 2x`"
                alt=""
                loading="lazy"
                @click="openScreenshot(id)"
              />
            </div>
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

  <!-- Screenshot lightbox -->
  <Teleport to="body">
    <div v-if="selectedScreenshot" class="screenshot-lightbox" @click.self="closeScreenshot">
      <button class="lightbox-btn lightbox-close" @click="closeScreenshot" aria-label="Fermer">✕</button>
      <button v-if="igdb.screenshotIds.length > 1" class="lightbox-btn lightbox-prev" @click="prevScreenshot" aria-label="Précédent">‹</button>
      <button v-if="igdb.screenshotIds.length > 1" class="lightbox-btn lightbox-next" @click="nextScreenshot" aria-label="Suivant">›</button>
      <img
        class="lightbox-img"
        :src="igdbUrl(selectedScreenshot, 't_screenshot_huge')"
        :srcset="`${igdbUrl(selectedScreenshot, 't_screenshot_huge')} 1280w, ${igdbUrl(selectedScreenshot, 't_1080p')} 1920w`"
        sizes="100vw"
        alt=""
      />
      <div v-if="igdb.screenshotIds.length > 1" class="lightbox-dots">
        <span
          v-for="id in igdb.screenshotIds"
          :key="id"
          class="lightbox-dot"
          :class="{ active: id === selectedScreenshot }"
          @click="selectedScreenshot = id"
        />
      </div>
    </div>
  </Teleport>
</template>
