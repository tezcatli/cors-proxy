<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getScoreClass, formatEpisodeCount } from '../lib/utils.js'
import { igdbUrl } from '../lib/igdbCdn.js'
import placeholderCover from '../assets/placeholder-cover.svg'
import { useGamesStore } from '../stores/games.js'
import { usePlayerStore } from '../stores/player.js'
import { fetchGameDetail, refreshGameIgdb } from '../lib/games.js'
import { isAdmin } from '../lib/auth.js'
import { useArtworkAccent } from '../composables/useArtworkAccent.js'
import { useEpisodePlayer } from '../composables/useEpisodePlayer.js'
import { playInto } from '../lib/flipTransition.js'
import EpisodeCard from './EpisodeCard.vue'
import ArtworkBackdrop from './ArtworkBackdrop.vue'
import BackBar from './BackBar.vue'
import IgdbPickerModal from './IgdbPickerModal.vue'
import { RotateCw, ExternalLink, ChevronLeft, ChevronRight, X, Play, Clock, Gamepad2, Wrench } from 'lucide-vue-next'
import { platformIconPath } from '../lib/platformIcons.js'

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

// Platform chips: each {label, family}. Old cached blobs store plain name
// strings — normalise those to a family-less chip so they still render.
const platformChips = computed(() =>
  (igdb.value?.platforms ?? []).map(p =>
    typeof p === 'string' ? { label: p, family: null } : p)
)
const coverFailed        = ref(false)
const selectedScreenshot = ref(null)
const trailerOpen        = ref(false)

// Carousel media = key-art artworks first, then gameplay screenshots.
const carouselImages = computed(() => [
  ...(igdb.value?.artworkIds ?? []),
  ...(igdb.value?.screenshotIds ?? []),
])
// Total slides incl. the leading trailer slide (drives arrows/dots).
const carouselSlideCount = computed(() =>
  (igdb.value?.trailerId ? 1 : 0) + carouselImages.value.length
)

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
  if (carouselSlideCount.value) carouselGoTo(Math.max(0, carouselIndex.value - 1))
}
function carouselNext() {
  const n = carouselSlideCount.value
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
// The podcast name(s) behind this entry — what the corrections API keys on.
const nameSlugs        = ref([])
const corrected        = ref(false)
const pickerOpen       = ref(false)
const admin            = isAdmin()

async function _loadEpisodes(g) {
  if (!g) { episodes.value = []; return }
  episodesLoading.value = true
  try {
    const detail = await fetchGameDetail(g.slug)
    episodes.value   = detail.episodes
    nameSlugs.value  = detail.nameSlugs ?? []
    corrected.value  = !!detail.corrected
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

// The picker corrects ONE podcast name. An entry merging several names (variant
// spellings) has no single target, so offer it only when there's exactly one.
const pickerTarget = computed(() => {
  if (nameSlugs.value.length !== 1 || !game.value) return null
  return {
    name:      game.value.name,
    nameSlug:  nameSlugs.value[0],
    nameSlugs: nameSlugs.value,
    podcasts:  game.value.podcasts ?? [],
    igdbName:  game.value.name,
    igdbSlug:  game.value.slug,
  }
})

async function onCorrectionSaved(detail) {
  pickerOpen.value = false
  await gamesStore.load(false)
  // Pinning a different game moves the entry to a new igdb_slug — follow it,
  // or we'd sit on a route that no longer exists in the catalog.
  if (detail?.slug && detail.slug !== route.params.slug) {
    router.replace(`/game/${encodeURIComponent(detail.slug)}`)
  } else {
    episodes.value   = detail?.episodes ?? episodes.value
    nameSlugs.value  = detail?.nameSlugs ?? nameSlugs.value
    corrected.value  = !!detail?.corrected
  }
}

watch(game, g => {
  coverFailed.value = false
  selectedScreenshot.value = null
  _loadEpisodes(g)
}, { immediate: true })

onMounted(async () => {
  document.body.style.overflow = 'hidden'
  document.addEventListener('keydown', onKeydown)
  window.addEventListener('resize', updateCarouselIndex)
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

const gameCtx = computed(() => ({
  name:         game.value?.name,
  slug:         game.value?.slug,
  coverImageId: coverImageId.value,
}))
const { isEpPlaying, playEp, togglePause } = useEpisodePlayer(gameCtx)

function viewEp(ep) {
  router.push({ path: `/episode/${encodeURIComponent(ep.urlSlug)}`, query: game.value.slug ? { game: game.value.slug } : {} })
}

function close() {
  if (router.options.history.state?.back) router.back()
  else router.push('/')
}

function onKeydown(e) {
  if (trailerOpen.value) {
    if (e.key === 'Escape') trailerOpen.value = false
    return
  }
  if (selectedScreenshot.value) {
    if (e.key === 'Escape')     { closeScreenshot(); return }
    if (e.key === 'ArrowLeft')  prevScreenshot()
    if (e.key === 'ArrowRight') nextScreenshot()
    return
  }
  if (e.key === 'Escape') close()
}
onUnmounted(() => {
  document.body.style.overflow = ''
  document.removeEventListener('keydown', onKeydown)
  window.removeEventListener('resize', updateCarouselIndex)
})

function openScreenshot(id) { selectedScreenshot.value = id }
function closeScreenshot()  { selectedScreenshot.value = null }
function onScreenshotKey(e, id) {
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openScreenshot(id) }
}

function prevScreenshot() {
  const ids = carouselImages.value
  if (!ids.length) return
  const i = ids.indexOf(selectedScreenshot.value)
  selectedScreenshot.value = ids[(i - 1 + ids.length) % ids.length]
}

function nextScreenshot() {
  const ids = carouselImages.value
  if (!ids.length) return
  const i = ids.indexOf(selectedScreenshot.value)
  selectedScreenshot.value = ids[(i + 1) % ids.length]
}
</script>

<template>
  <div class="fixed inset-0 z-[var(--z-detail)] bg-base-100" :style="cssVars">
    <!-- Loading / not found -->
    <div v-if="gamesStore.loading || !game" class="fixed inset-0 z-[var(--z-detail)] bg-base-100 flex flex-col">
      <BackBar label="Retour" @back="close" />
      <div class="flex flex-1 items-center justify-center">
        <span v-if="gamesStore.loading" class="loading loading-spinner loading-lg text-game-accent"></span>
        <p v-else class="text-base-content/50">Jeu introuvable.</p>
      </div>
    </div>

    <!-- Main view -->
    <div v-else class="fixed inset-0 z-[var(--z-detail)]">

      <!-- Hero backdrop — driven by the cover, not screenshots -->
      <ArtworkBackdrop :cover-image-id="coverImageId" intensity="hero" />

      <!-- Content -->
      <div class="detail-content relative h-full flex flex-col">

        <!-- Back bar -->
        <BackBar label="Retour" @back="close" />

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
                    ? `${igdbUrl(coverImageId,'t_cover_big')} 1x, ${igdbUrl(coverImageId,'t_cover_big_2x')} 2x`
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
                <div class="flex items-center gap-0.5 mt-1">
                  <button
                    v-if="admin && pickerTarget"
                    class="btn btn-xs btn-ghost text-white/35 hover:text-white/70 px-1 min-h-0 h-6"
                    aria-label="Corriger la fiche IGDB"
                    title="Corriger la fiche IGDB"
                    @click="pickerOpen = true"
                  >
                    <Wrench :size="13" :stroke-width="2.25" />
                  </button>
                  <button
                    class="btn btn-xs btn-ghost text-white/35 hover:text-white/70 px-1 min-h-0 h-6"
                    :disabled="igdbRefreshing"
                    :aria-label="igdbRefreshing ? 'Actualisation IGDB…' : 'Rafraîchir IGDB'"
                    @click="refreshIgdb"
                  >
                    <RotateCw :size="13" :stroke-width="2.25" :class="{ 'animate-spin': igdbRefreshing }" />
                  </button>
                </div>
              </div>

              <!-- Stats strip: Metacritic · IGDB · Durée de vie -->
              <div v-if="igdb?.metacritic || igdb?.rating || igdb?.timeToBeatHours" class="flex flex-wrap gap-2">
                <div v-if="igdb?.metacritic" class="score-block" :class="getScoreClass(igdb.metacritic)">
                  <span class="score-number">{{ igdb.metacritic }}</span>
                  <span class="score-label">Metacritic</span>
                </div>
                <div v-if="igdb?.rating" class="score-block igdb-rating">
                  <span class="score-number">{{ igdb.rating }}</span>
                  <span class="score-label">IGDB</span>
                </div>
                <div v-if="igdb?.timeToBeatHours" class="score-block stat-block">
                  <span class="score-number"><Clock :size="15" :stroke-width="2.5" /> {{ igdb.timeToBeatHours }} h</span>
                  <span class="score-label">Durée de vie</span>
                </div>
              </div>

              <!-- Tags: year + genres + franchise (accent) · modes/perspectives/themes (neutral) -->
              <div
                v-if="igdb?.released || igdb?.genres?.length || igdb?.modes?.length || igdb?.perspectives?.length || igdb?.themes?.length || igdb?.franchise"
                class="flex flex-wrap gap-1.5"
              >
                <span v-if="igdb?.released" class="chip chip-accent">{{ igdb.released }}</span>
                <span v-for="g in igdb?.genres ?? []" :key="'g'+g" class="chip chip-accent">{{ g }}</span>
                <span v-if="igdb?.franchise" class="chip chip-accent">{{ igdb.franchise }}</span>
                <span v-for="m in igdb?.modes ?? []" :key="'m'+m" class="chip">{{ m }}</span>
                <span v-for="pv in igdb?.perspectives ?? []" :key="'pv'+pv" class="chip">{{ pv }}</span>
                <span v-for="t in igdb?.themes ?? []" :key="'t'+t" class="chip">{{ t }}</span>
              </div>

              <!-- Platforms — monochrome brand glyph + generation label -->
              <div
                v-if="platformChips.length"
                class="flex flex-wrap items-center gap-2"
              >
                <span v-for="(p, i) in platformChips" :key="'p'+i" class="chip" :title="p.label">
                  <svg v-if="platformIconPath(p.family)" class="chip__icon" viewBox="0 0 24 24" aria-hidden="true">
                    <path :d="platformIconPath(p.family)" fill="currentColor" />
                  </svg>
                  <Gamepad2 v-else class="chip__icon" />
                  {{ p.label }}
                </span>
              </div>

              <!-- Studio · publisher · PEGI -->
              <div
                v-if="igdb?.developer || igdb?.publisher || igdb?.esrb"
                class="flex items-center flex-wrap gap-2 text-[0.78rem]"
              >
                <span v-if="igdb?.developer || igdb?.publisher" class="text-white/65 font-medium">
                  {{ igdb.developer || igdb.publisher }}<template v-if="igdb.developer && igdb.publisher && igdb.publisher !== igdb.developer"> · {{ igdb.publisher }}</template>
                </span>
                <span v-if="igdb?.esrb" class="chip !text-[0.65rem]">{{ igdb.esrb }}</span>
              </div>

              <!-- Description + storyline -->
              <p
                v-if="igdb?.description"
                class="text-[0.9rem] text-white/82 leading-relaxed"
              >{{ igdb.description }}</p>
              <p
                v-if="igdb?.storyline"
                class="text-[0.84rem] text-white/60 leading-relaxed whitespace-pre-line"
              >{{ igdb.storyline }}</p>

              <!-- Action row -->
              <div class="detail-action-row">
                <a
                  v-if="igdb?.steamUrl"
                  :href="igdb.steamUrl" target="_blank" rel="noopener noreferrer"
                  class="steam-pill"
                >Steam <ExternalLink :size="13" :stroke-width="2.5" /></a>
                <a
                  v-if="igdb?.officialUrl"
                  :href="igdb.officialUrl" target="_blank" rel="noopener noreferrer"
                  class="link-pill"
                >Site officiel <ExternalLink :size="12" :stroke-width="2.25" /></a>
                <a
                  v-if="igdb?.wikiUrl"
                  :href="igdb.wikiUrl" target="_blank" rel="noopener noreferrer"
                  class="link-pill"
                >Wikipédia <ExternalLink :size="12" :stroke-width="2.25" /></a>
                <span class="chip chip-accent">{{ epCount }}</span>
              </div>
            </div>

            <!-- Episodes -->
            <div class="detail-hero__episodes">
              <div class="panel panel--tinted p-3">
                <div class="text-[0.68rem] uppercase tracking-[0.12em] font-extrabold text-white/55 mb-2 px-1">
                  Épisodes
                </div>
                <div v-if="episodesLoading" class="flex flex-col gap-2">
                  <div
                    v-for="i in 4"
                    :key="i"
                    class="skeleton-shimmer h-[56px] rounded-xl"
                    aria-hidden="true"
                  />
                </div>
                <div v-else class="flex flex-col gap-2">
                  <EpisodeCard
                    v-for="ep in episodes"
                    :key="ep.slug"
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

          <!-- Trailer + artwork + screenshots carousel -->
          <section v-if="igdb?.trailerId || carouselImages.length" class="detail-carousel">
            <div class="detail-carousel__track" ref="carouselTrack" @scroll.passive="updateCarouselIndex">
              <!-- Lead slide: trailer poster -->
              <button
                v-if="igdb?.trailerId"
                type="button"
                class="detail-carousel__slide detail-carousel__trailer"
                aria-label="Lire la bande-annonce"
                @click="trailerOpen = true"
              >
                <img
                  :src="`https://i.ytimg.com/vi/${igdb.trailerId}/maxresdefault.jpg`"
                  @error="e => e.target.src = `https://i.ytimg.com/vi/${igdb.trailerId}/hqdefault.jpg`"
                  alt="" loading="lazy"
                />
                <span class="detail-carousel__play"><Play :size="26" fill="currentColor" :stroke-width="0" /></span>
                <span class="detail-carousel__trailer-label">Bande-annonce</span>
              </button>
              <img
                v-for="id in carouselImages"
                :key="id"
                class="detail-carousel__slide"
                role="button"
                tabindex="0"
                aria-label="Agrandir la capture d’écran"
                :src="igdbUrl(id, 't_screenshot_big')"
                :srcset="`${igdbUrl(id, 't_screenshot_med')} 1x, ${igdbUrl(id, 't_screenshot_huge')} 2x`"
                alt=""
                loading="lazy"
                @click="openScreenshot(id)"
                @keydown="e => onScreenshotKey(e, id)"
              />
            </div>
            <button
              v-if="carouselSlideCount > 1"
              class="detail-carousel__arrow detail-carousel__arrow--prev"
              :disabled="carouselIndex === 0"
              aria-label="Précédent"
              @click="carouselPrev"
            ><ChevronLeft :size="20" :stroke-width="2.25" /></button>
            <button
              v-if="carouselSlideCount > 1"
              class="detail-carousel__arrow detail-carousel__arrow--next"
              :disabled="carouselIndex >= carouselSlideCount - 1"
              aria-label="Suivant"
              @click="carouselNext"
            ><ChevronRight :size="20" :stroke-width="2.25" /></button>
            <div v-if="carouselSlideCount > 1" class="detail-carousel__dots">
              <button
                v-for="i in carouselSlideCount"
                :key="i"
                class="detail-carousel__dot"
                :class="{ 'is-active': i - 1 === carouselIndex }"
                :aria-label="`Média ${i}`"
                @click="carouselGoTo(i - 1)"
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
        <button class="lightbox-btn lightbox-close" @click="closeScreenshot" aria-label="Fermer"><X :size="20" :stroke-width="2.25" /></button>
        <button v-if="carouselImages.length > 1" class="lightbox-btn lightbox-prev" @click="prevScreenshot" aria-label="Précédent"><ChevronLeft :size="28" :stroke-width="2.25" /></button>
        <button v-if="carouselImages.length > 1" class="lightbox-btn lightbox-next" @click="nextScreenshot" aria-label="Suivant"><ChevronRight :size="28" :stroke-width="2.25" /></button>
        <img
          class="lightbox-img"
          :src="igdbUrl(selectedScreenshot, 't_screenshot_huge')"
          :srcset="`${igdbUrl(selectedScreenshot, 't_screenshot_huge')} 1280w, ${igdbUrl(selectedScreenshot, 't_1080p')} 1920w`"
          sizes="100vw"
          alt=""
        />
        <div v-if="carouselImages.length > 1" class="lightbox-dots">
          <span
            v-for="id in carouselImages"
            :key="id"
            class="lightbox-dot"
            :class="{ active: id === selectedScreenshot }"
            @click="selectedScreenshot = id"
          />
        </div>
      </div>
    </Teleport>

    <!-- Admin: pin the IGDB game this podcast name resolves to -->
    <Teleport to="body">
      <IgdbPickerModal
        v-if="pickerOpen && pickerTarget"
        :game="pickerTarget"
        :has-correction="corrected"
        @close="pickerOpen = false"
        @saved="onCorrectionSaved"
      />
    </Teleport>

    <!-- Trailer modal — bare overlay, like the screenshot lightbox -->
    <Teleport to="body">
      <div v-if="trailerOpen && igdb?.trailerId" class="trailer-modal" @click.self="trailerOpen = false">
        <button class="lightbox-btn lightbox-close" @click="trailerOpen = false" aria-label="Fermer"><X :size="20" :stroke-width="2.25" /></button>
        <div class="trailer-card__frame">
          <iframe
            :src="`https://www.youtube-nocookie.com/embed/${igdb.trailerId}?autoplay=1&rel=0`"
            title="Bande-annonce"
            allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
            allowfullscreen
            frameborder="0"
          />
        </div>
      </div>
    </Teleport>
  </div>
</template>
