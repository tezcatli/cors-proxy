<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getScoreClass, formatEpisodeCount } from '../lib/utils.js'
import { igdbUrl } from '../lib/igdbCdn.js'
import placeholderCover from '../assets/placeholder-cover.svg'
import { useGamesStore } from '../stores/games.js'
import { usePlayerStore } from '../stores/player.js'
import { fetchGameDetail, refreshGameIgdb } from '../lib/games.js'
import { useArtworkAccent } from '../composables/useArtworkAccent.js'
import { playInto } from '../lib/flipTransition.js'
import EpisodeCard from './EpisodeCard.vue'
import ArtworkBackdrop from './ArtworkBackdrop.vue'
import { ArrowLeft, RotateCw, ExternalLink, ChevronLeft, ChevronRight } from 'lucide-vue-next'

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
const coverFailed  = ref(false)

const { cssVars } = useArtworkAccent(coverImageId)

const heroCoverEl     = ref(null)

// Screenshot carousel
const carouselTrack = ref(null)
const carouselIndex = ref(0)
const CAROUSEL_GAP  = 12

function _slideStep() {
  const first = carouselTrack.value?.firstElementChild
  return first ? first.offsetWidth + CAROUSEL_GAP : 0
}
function carouselGoTo(i) {
  const t = carouselTrack.value
  const step = _slideStep()
  if (!t || !step) return
  t.scrollTo({ left: step * i, behavior: 'smooth' })
}
function carouselPrev() {
  const n = igdb.value?.screenshotIds?.length ?? 0
  if (n) carouselGoTo(Math.max(0, carouselIndex.value - 1))
}
function carouselNext() {
  const n = igdb.value?.screenshotIds?.length ?? 0
  if (n) carouselGoTo(Math.min(n - 1, carouselIndex.value + 1))
}
function updateCarouselIndex() {
  const t = carouselTrack.value
  const step = _slideStep()
  if (!t || !step) return
  carouselIndex.value = Math.round(t.scrollLeft / step)
}

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
  _loadEpisodes(g)
}, { immediate: true })

onMounted(async () => {
  await nextTick()
  if (game.value && heroCoverEl.value) {
    playInto(`cover:${game.value.slug}`, heroCoverEl.value)
  }
})

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

const selectedScreenshot = ref(null)

watch(game, g => {
  if (g) selectedScreenshot.value = null
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
  <div class="fixed inset-0 z-[150]" :style="cssVars">
    <!-- Loading / not found -->
    <div v-if="gamesStore.loading || !game" class="fixed inset-0 z-[150] bg-base-100 flex flex-col">
      <div class="flex items-center px-4 py-3 border-b border-white/5 backdrop-blur-md bg-black/30">
        <button class="btn btn-sm btn-ghost gap-1.5" @click="close">
          <ArrowLeft :size="16" :stroke-width="2.25" /> Retour
        </button>
      </div>
      <div class="flex flex-1 items-center justify-center">
        <span v-if="gamesStore.loading" class="loading loading-spinner loading-lg text-primary"></span>
        <p v-else class="text-base-content/50">Jeu introuvable.</p>
      </div>
    </div>

    <!-- Main view -->
    <div v-else class="fixed inset-0 z-[150]">

      <!-- Hero backdrop — driven by the cover, not screenshots -->
      <ArtworkBackdrop :cover-image-id="coverImageId" intensity="hero" />

      <!-- Content -->
      <div class="detail-content relative h-full flex flex-col">

        <!-- Back bar -->
        <div class="sticky top-0 z-10 flex items-center px-3 h-12 bg-black/35 backdrop-blur-xl border-b border-white/5 flex-shrink-0">
          <button class="btn btn-sm btn-ghost gap-1.5 text-white/85 hover:text-white" @click="close">
            <ArrowLeft :size="16" :stroke-width="2.25" /> Retour
          </button>
        </div>

        <!-- Body -->
        <div class="detail-body">

          <!-- Hero band: cover · meta · episodes -->
          <section class="detail-hero">
            <!-- Cover -->
            <div class="detail-hero__cover">
              <div ref="heroCoverEl" class="detail-cover-card">
                <img
                  :src="coverImageId && !coverFailed ? igdbUrl(coverImageId, 't_cover_big') : placeholderCover"
                  :srcset="coverImageId && !coverFailed
                    ? `${igdbUrl(coverImageId,'t_cover_big')} 264w 374h , ${igdbUrl(coverImageId,'t_cover_big_2x')} 528w 748h`
                    : undefined"
                  :alt="game.name"
                  @error="coverFailed = true"
                />
              </div>
            </div>

            <!-- Meta -->
            <div class="detail-hero__meta">
              <!-- Title row -->
              <div class="flex items-start justify-between gap-3">
                <h2 class="detail-title">{{ game.name }}</h2>
                <button
                  class="btn btn-xs btn-ghost text-white/35 hover:text-white/70 px-1 min-h-0 h-6 mt-1"
                  :disabled="igdbRefreshing"
                  :aria-label="igdbRefreshing ? 'Actualisation IGDB…' : 'Rafraîchir IGDB'"
                  @click="refreshIgdb"
                >
                  <RotateCw :size="13" :stroke-width="2.25" :class="{ 'animate-spin': igdbRefreshing }" />
                </button>
              </div>

              <!-- Scores -->
              <div v-if="igdb?.metacritic || igdb?.rating" class="flex gap-2">
                <div v-if="igdb?.metacritic" class="score-block" :class="getScoreClass(igdb.metacritic)">
                  <span class="score-number">{{ igdb.metacritic }}</span>
                  <span class="score-label">Metacritic</span>
                </div>
                <div v-if="igdb?.rating" class="score-block igdb-rating">
                  <span class="score-number">{{ igdb.rating }}</span>
                  <span class="score-label">IGDB</span>
                </div>
              </div>

              <!-- Metadata chips: year (accent) · first genre (accent) · others (neutral) -->
              <div
                v-if="igdb?.released || igdb?.genres?.length || igdb?.platforms?.length"
                class="flex flex-wrap gap-1.5"
              >
                <span v-if="igdb?.released" class="chip chip-accent">{{ igdb.released }}</span>
                <span
                  v-for="(g, i) in igdb?.genres ?? []"
                  :key="g"
                  class="chip"
                  :class="{ 'chip-accent': i === 0 }"
                >{{ g }}</span>
                <span v-for="p in igdb?.platforms ?? []" :key="p" class="chip">{{ p }}</span>
              </div>

              <!-- Developer · publisher · ESRB -->
              <div
                v-if="igdb?.developer || igdb?.esrb"
                class="flex items-center flex-wrap gap-2 text-[0.78rem]"
              >
                <span v-if="igdb?.developer" class="text-white/65 font-medium">
                  {{ igdb.developer }}<template v-if="igdb.publisher && igdb.publisher !== igdb.developer"> · {{ igdb.publisher }}</template>
                </span>
                <span v-if="igdb?.esrb" class="chip !text-[0.65rem]">{{ igdb.esrb }}</span>
              </div>

              <!-- Description -->
              <p
                v-if="igdb?.description"
                class="text-[0.9rem] text-white/82 leading-relaxed"
              >{{ igdb.description }}</p>

              <!-- Action row -->
              <div class="detail-action-row">
                <a
                  v-if="igdb?.steamUrl"
                  :href="igdb.steamUrl" target="_blank" rel="noopener noreferrer"
                  class="steam-pill"
                >Steam <ExternalLink :size="13" :stroke-width="2.5" /></a>
                <span class="chip chip-accent">{{ epCount }}</span>
              </div>
            </div>

            <!-- Episodes -->
            <div class="detail-hero__episodes">
              <div class="panel panel--tinted p-3">
                <div class="text-[0.68rem] uppercase tracking-[0.12em] font-extrabold text-white/55 mb-2 px-1">
                  Épisodes
                </div>
                <div v-if="episodesLoading" class="flex justify-center py-6">
                  <span class="loading loading-spinner loading-sm" style="color: var(--game-accent);"></span>
                </div>
                <div v-else class="flex flex-col gap-2">
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
          </section>

          <!-- Screenshots carousel -->
          <section v-if="igdb?.screenshotIds?.length" class="detail-carousel">
            <div class="detail-carousel__track" ref="carouselTrack" @scroll.passive="updateCarouselIndex">
              <img
                v-for="id in igdb.screenshotIds"
                :key="id"
                class="detail-carousel__slide"
                :src="igdbUrl(id, 't_screenshot_big')"
                :srcset="`${igdbUrl(id, 't_screenshot_med')} 1x, ${igdbUrl(id, 't_screenshot_huge')} 2x`"
                alt=""
                loading="lazy"
                @click="openScreenshot(id)"
              />
            </div>
            <button
              v-if="igdb.screenshotIds.length > 1"
              class="detail-carousel__arrow detail-carousel__arrow--prev"
              :disabled="carouselIndex === 0"
              aria-label="Précédent"
              @click="carouselPrev"
            ><ChevronLeft :size="20" :stroke-width="2.25" /></button>
            <button
              v-if="igdb.screenshotIds.length > 1"
              class="detail-carousel__arrow detail-carousel__arrow--next"
              :disabled="carouselIndex >= igdb.screenshotIds.length - 1"
              aria-label="Suivant"
              @click="carouselNext"
            ><ChevronRight :size="20" :stroke-width="2.25" /></button>
            <div v-if="igdb.screenshotIds.length > 1" class="detail-carousel__dots">
              <button
                v-for="(id, i) in igdb.screenshotIds"
                :key="id"
                class="detail-carousel__dot"
                :class="{ 'is-active': i === carouselIndex }"
                :aria-label="`Image ${i+1}`"
                @click="carouselGoTo(i)"
              />
            </div>
          </section>

          <div class="detail-bottom-pad" />
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
