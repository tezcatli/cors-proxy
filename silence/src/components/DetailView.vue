<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getScoreClass, formatEpisodeCount } from '../lib/utils.js'
import { igdbUrl } from '../lib/igdbCdn.js'
import placeholderCover from '../assets/placeholder-cover.svg'
import placeholderBg    from '../assets/placeholder-bg.svg'
import { useGamesStore } from '../stores/games.js'
import { usePlayerStore } from '../stores/player.js'
import { fetchGameDetail, refreshGameIgdb } from '../lib/games.js'
import EpisodeCard from './EpisodeCard.vue'

const route       = useRoute()
const router      = useRouter()
const gamesStore  = useGamesStore()
const playerStore = usePlayerStore()

const game = computed(() => {
  const slug = route.params.slug
  return gamesStore.all.find(g => g.slug === slug) ?? null
})

const igdb         = computed(() => game.value?.igdb ?? null)
const coverImageId = computed(() => igdb.value?.coverImageId ?? null)
const bgImageId    = computed(() => igdb.value?.bgImageId ?? null)
const coverFailed  = ref(false)
const bgFailed     = ref(false)

const episodes         = ref([])
const episodesLoading  = ref(false)
const igdbRefreshing   = ref(false)

async function _loadEpisodes(g) {
  if (!g) { episodes.value = []; return }
  episodesLoading.value = true
  try {
    const detail = await fetchGameDetail(g.slug)
    episodes.value = detail.episodes
    if (detail.igdb) {
      const idx = gamesStore.all.findIndex(x => x.slug === g.slug)
      if (idx !== -1) gamesStore.all[idx].igdb = detail.igdb
    }
  } catch (_) {
    episodes.value = []
  } finally {
    episodesLoading.value = false
  }
}

watch(game, g => {
  coverFailed.value = false
  bgFailed.value    = false
  _loadEpisodes(g)
}, { immediate: true })

async function refreshIgdb() {
  if (!game.value) return
  igdbRefreshing.value = true
  try {
    const result = await refreshGameIgdb(game.value.slug)
    const idx = gamesStore.all.findIndex(g => g.slug === result.slug)
    if (idx !== -1) gamesStore.all[idx].igdb = result.igdb
    episodes.value = result.episodes
  } catch (_) {
    // ignore
  } finally {
    igdbRefreshing.value = false
  }
}

watch(coverImageId, id => {
  if (id && playerStore.current?.slug === game.value?.slug) playerStore.setEpisodeImageUrl(igdbUrl(id, 't_cover_big'))
})

const epCount = computed(() => formatEpisodeCount(game.value?.episodeCount ?? episodes.value.length))

function isEpPlaying(ep) {
  return !!playerStore.current && ep.audioUrl === playerStore.current.url
}

function playEp(ep) {
  playerStore.play({
    game:            game.value.name,
    slug:            game.value.slug,
    episode:         ep.title,
    url:             ep.audioUrl,
    ts:              ep.timestampSeconds || 0,
    timestamp:       ep.timestamp || null,
    episodeImageUrl: ep.imageUrl ?? null,
    pubTs:           ep.pubTs,
    episodeSlug:     ep.slug,
    coverImageId:    coverImageId.value,
    chapters:        ep.chapters ?? [],
  })
}

function viewEp(ep) {
  router.push(`/episode/${ep.slug}/game/${game.value.slug}`)
}

function togglePause() { playerStore.setPaused(!playerStore.paused) }

const descExpanded       = ref(false)
const selectedScreenshot = ref(null)

watch(game, g => {
  if (g) {
    descExpanded.value       = false
    selectedScreenshot.value = null
  }
})


function close() {
  if (router.options.history.state?.back) router.back()
  else router.push('/')
}

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

</script>

<template>
  <div class="fixed inset-0 z-[150]">
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
          ? `${igdbUrl(bgImageId,'t_720p')} 1280w 720h, ${igdbUrl(bgImageId,'t_1080p')} 1920w 1080h, ${igdbUrl(bgImageId,'t_720p_2x')} 2560w 1440h, ${igdbUrl(bgImageId,'t_1080p_2x')} 3840w 2160h`
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
                ? `${igdbUrl(coverImageId,'t_cover_big')} 264w 374h , ${igdbUrl(coverImageId,'t_cover_big_2x')} 528w 748h`
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
          <div class="panel mx-4 mb-3 mt-4 p-4">
            <div class="flex items-start justify-between gap-3 mb-3">
              <h2 class="text-[1.2rem] font-extrabold leading-tight sm:text-[1.45rem]">{{ game.name }}</h2>
              <div class="flex items-center gap-1.5 flex-shrink-0 mt-1">
                <span class="badge badge-sm text-white/50">{{ epCount }}</span>
                <button
                  class="btn btn-xs btn-ghost text-white/30 hover:text-white/60 px-1 min-h-0 h-5 leading-none"
                  :disabled="igdbRefreshing"
                  :aria-label="igdbRefreshing ? 'Actualisation IGDB…' : 'Rafraîchir IGDB'"
                  @click="refreshIgdb"
                >{{ igdbRefreshing ? '…' : '↻' }}</button>
              </div>
            </div>

            <!-- Scores (always visible) -->
            <div v-if="igdb?.metacritic || igdb?.rating" class="flex gap-2 mb-3">
              <div v-if="igdb?.metacritic" class="score-block" :class="getScoreClass(igdb.metacritic)">
                <span class="score-number">{{ igdb.metacritic }}</span>
                <span class="score-label">Metacritic</span>
              </div>
              <div v-if="igdb?.rating" class="score-block igdb-rating">
                <span class="score-number">{{ igdb.rating }}</span>
                <span class="score-label">IGDB</span>
              </div>
            </div>

            <!-- Year · genres · platforms -->
            <p v-if="igdb?.released || igdb?.genres?.length || igdb?.platforms?.length" class="text-[0.78rem] text-white/55 mb-1.5">
              <template v-if="igdb?.released">{{ igdb.released }}</template><template v-if="igdb?.released && (igdb?.genres?.length || igdb?.platforms?.length)"> · </template><template v-if="igdb?.genres?.length">{{ igdb.genres.join(', ') }}</template><template v-if="igdb?.genres?.length && igdb?.platforms?.length"> · </template><template v-if="igdb?.platforms?.length">{{ igdb.platforms.join(', ') }}</template>
            </p>

            <!-- Developer · publisher · ESRB · Steam -->
            <div v-if="igdb?.developer || igdb?.esrb || igdb?.steamUrl" class="flex items-center flex-wrap gap-2 mb-3 text-[0.72rem]">
              <span v-if="igdb?.developer" class="text-white/45">
                {{ igdb.developer }}<template v-if="igdb.publisher && igdb.publisher !== igdb.developer"> · {{ igdb.publisher }}</template>
              </span>
              <span v-if="igdb?.esrb" class="badge badge-sm text-white/40">{{ igdb.esrb }}</span>
              <a v-if="igdb?.steamUrl" :href="igdb.steamUrl" target="_blank" rel="noopener noreferrer"
                 class="text-primary/80 hover:text-primary ml-auto flex-shrink-0 transition-colors">Steam ↗</a>
            </div>

            <!-- Description -->
            <div v-if="igdb?.description" class="border-t border-white/10 pt-3">
              <p class="text-[0.82rem] text-white/80 leading-relaxed" :class="{ 'line-clamp-4': !descExpanded }">{{ igdb.description }}</p>
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
          <div class="panel mx-4 mb-4 p-3 mb-[calc(150px+env(safe-area-inset-bottom,0px))]">
            <div v-if="episodesLoading" class="flex justify-center py-4">
              <span class="loading loading-spinner loading-sm text-primary/50"></span>
            </div>
            <div v-else class="flex flex-col gap-1.5">
              <EpisodeCard
                v-for="ep in episodes"
                :key="ep.title"
                :episode="ep"
                :game-name="game.name"
                :is-playing="isEpPlaying(ep)"
                :is-paused="playerStore.paused"
                @play="playEp"
                @toggle-pause="togglePause"
                @view="viewEp"
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
        :srcset="`${igdbUrl(selectedScreenshot, 't_screenshot_huge')} 1280w 720h, ${igdbUrl(selectedScreenshot, 't_1080p')} 1920w 1080h`"
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
  </div>
</template>
