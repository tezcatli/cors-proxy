<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { formatShortDate, formatEpisodeCount, formatTime } from '../lib/utils.js'
import { frLabel } from '../lib/igdbLabels.js'
import { igdbUrl } from '../lib/igdbCdn.js'
import { verdictCounts } from '../lib/verdicts.js'
import { podcastMeta } from '../lib/podcasts.js'
import { useGamesStore } from '../stores/games.js'
import { usePlayerStore } from '../stores/player.js'
import { fetchGameDetail, refreshGameIgdb } from '../lib/games.js'
import { isAdmin } from '../lib/auth.js'
import { useEpisodePlayer } from '../composables/useEpisodePlayer.js'
import { playInto } from '../lib/flipTransition.js'
import { useGameTheme } from '../composables/useGameTheme.js'
import BackBar from './BackBar.vue'
import VerdictMark from './VerdictMark.vue'
import IgdbPickerModal from './IgdbPickerModal.vue'
import { RotateCw, ChevronLeft, ChevronRight, X, Play, Pause, Wrench } from 'lucide-vue-next'

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
// The page wears the game's colours, read from its cover.
const { style: theme } = useGameTheme(coverImageId)

const platforms = computed(() =>
  (igdb.value?.platforms ?? []).map(p => typeof p === 'string' ? p : p.label))

const coverFailed  = ref(false)
const lightboxAt   = ref(null)    // index into lightboxImages, null = closed
const trailerOpen  = ref(false)

// Screenshots first: they show the game, where key art often repeats its logo
// (already on the cover and in the title). Artworks follow.
const screenshotIds = computed(() => igdb.value?.screenshotIds ?? [])
const mediaImages = computed(() => [
  ...screenshotIds.value,
  ...(igdb.value?.artworkIds ?? []),
])
// Beside the cover: three screenshots (they show the game; artworks often
// repeat the logo).
const heroShots = computed(() => screenshotIds.value.slice(0, 3))
// The lightbox runs through the cover, then the images.
const lightboxImages = computed(() => [
  ...(coverImageId.value && !coverFailed.value ? [coverImageId.value] : []),
  ...mediaImages.value,
])
// The lightbox takes the focus and gives it back to what opened it.
const lightboxEl = ref(null)
let lightboxOpener = null
async function openLightbox(id) {
  lightboxOpener = document.activeElement
  lightboxAt.value = Math.max(0, lightboxImages.value.indexOf(id))
  await nextTick()
  lightboxEl.value?.querySelector('.lightbox__close')?.focus()
}
function closeLightbox() {
  lightboxAt.value = null
  lightboxOpener?.focus?.()
  lightboxOpener = null
}
// Tab stays inside the lightbox while it is open.
function trapTab(e) {
  const els = [...(lightboxEl.value?.querySelectorAll('button') ?? [])]
  if (!els.length) return
  const i = els.indexOf(document.activeElement)
  e.preventDefault()
  els[(i + (e.shiftKey ? -1 : 1) + els.length) % els.length].focus()
}
const lightboxId = computed(() => lightboxAt.value == null ? null : lightboxImages.value[lightboxAt.value])

// The board shows six tiles (the trailer counts as one); the last says « +n ».
const BOARD_TILES = 6
const boardImages = computed(() => {
  const shown = mediaImages.value.slice(0, BOARD_TILES - (igdb.value?.trailerId ? 1 : 0))
  // The « +n » tile wears a screenshot: an artwork may be a logo on nothing.
  if (mediaImages.value.length > shown.length) {
    const i = shown.findLastIndex(id => screenshotIds.value.includes(id))
    if (i >= 0 && i < shown.length - 1) shown.push(...shown.splice(i, 1))
  }
  return shown
})
const boardMore   = computed(() => mediaImages.value.length - boardImages.value.length)

// The back bar floats over the cover's backdrop until the page scrolls.
const scrolled = ref(false)
function onScroll(e) {
  scrolled.value = e.target.scrollTop > 40
}

const heroCoverEl = ref(null)

const episodes        = ref([])
const episodesLoading = ref(false)
const igdbRefreshing  = ref(false)
// The podcast name(s) behind this entry — what the corrections API keys on.
const nameSlugs   = ref([])
const corrected   = ref(false)
// Current display_name override and true IGDB name — pre-fill the picker so an
// existing rename isn't shown as empty (and « Actuellement » shows the real
// resolution, not the override).
const displayName = ref(null)
const igdbName    = ref(null)
const pickerOpen  = ref(false)
const admin       = isAdmin()

async function _loadEpisodes(g) {
  if (!g) { episodes.value = []; return }
  episodesLoading.value = true
  try {
    const detail = await fetchGameDetail(g.slug)
    episodes.value    = detail.episodes
    nameSlugs.value   = detail.nameSlugs ?? []
    corrected.value   = !!detail.corrected
    displayName.value = detail.displayName ?? null
    igdbName.value    = detail.igdbName ?? null
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
    name:        game.value.name,
    nameSlug:    nameSlugs.value[0],
    nameSlugs:   nameSlugs.value,
    podcasts:    game.value.podcasts ?? [],
    igdbName:    igdbName.value,
    igdbSlug:    game.value.slug,
    displayName: displayName.value,
  }
})

async function onCorrectionSaved(detail) {
  pickerOpen.value = false
  await gamesStore.load()
  // Pinning a different game moves the entry to a new igdb_slug — follow it,
  // or we'd sit on a route that no longer exists in the catalog.
  if (detail?.slug && detail.slug !== route.params.slug) {
    router.replace(`/game/${encodeURIComponent(detail.slug)}`)
  } else if (detail) {
    episodes.value    = detail.episodes ?? episodes.value
    nameSlugs.value   = detail.nameSlugs ?? nameSlugs.value
    corrected.value   = !!detail.corrected
    displayName.value = detail.displayName ?? null
    igdbName.value    = detail.igdbName ?? null
  }
}

watch(game, g => {
  coverFailed.value = false
  lightboxAt.value = null
  _loadEpisodes(g)
}, { immediate: true })

onMounted(async () => {
  document.body.style.overflow = 'hidden'
  document.addEventListener('keydown', onKeydown)
  await nextTick()
  if (game.value && heroCoverEl.value) playInto(`cover:${game.value.slug}`, heroCoverEl.value)
})

async function refreshIgdb() {
  if (!game.value) return
  igdbRefreshing.value = true
  try {
    const result = await refreshGameIgdb(game.value.slug)
    // Re-resolution can move the entry to a different igdb_slug — follow it
    // (same as onCorrectionSaved), or we'd sit on a route with no catalog entry.
    if (result.slug && result.slug !== route.params.slug) {
      await gamesStore.load()
      router.replace(`/game/${encodeURIComponent(result.slug)}`)
      return
    }
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

// ── The tests ────────────────────────────────────────────────────────────────
const counts = computed(() => verdictCounts(episodes.value.map(ep => ep.critique?.verdict ?? null)))
// « 9 positifs · 1 mitigé »: the tests counted by verdict (never averaged).
const PLURAL = { positive: ['positif', 'positifs'], mixed: ['mitigé', 'mitigés'], negative: ['négatif', 'négatifs'] }
const verdictLine = computed(() => Object.entries(PLURAL)
  .filter(([k]) => counts.value[k])
  .map(([k, [one, many]]) => `${counts.value[k]} ${counts.value[k] > 1 ? many : one}`)
  .join(' · '))

// The game's gauges: its Metacritic score, and the share of its tests the hosts
// liked (a count of verdicts, shown as a bar).
const gauges = computed(() => {
  const out = []
  const mc = igdb.value?.metacritic
  if (mc) out.push({ label: 'Metacritic', value: String(mc), pct: Math.min(100, mc) })
  const judged = counts.value.positive + counts.value.mixed + counts.value.negative
  if (judged) out.push({ label: 'Avis positifs', value: `${counts.value.positive} sur ${judged}`, pct: Math.round(100 * counts.value.positive / judged) })
  return out
})
const kicker = computed(() => [
  ...(igdb.value?.genres ?? []).slice(0, 2).map(frLabel),
  igdb.value?.released,
].filter(Boolean).join(' · '))
const byline = computed(() => [igdb.value?.developer, platforms.value.join(' · ')].filter(Boolean).join(' · '))

const gameCtx = computed(() => ({
  name:         game.value?.name,
  slug:         game.value?.slug,
  coverImageId: coverImageId.value,
}))
const { isEpPlaying, playEp, togglePause } = useEpisodePlayer(gameCtx)

// One test row is open on its « pour / contre »: the one playing, else the one
// picked, else the first that has any.
const picked = ref(null)
const openSlug = computed(() => {
  if (picked.value !== null) return picked.value || null
  const playing = episodes.value.find(ep => isEpPlaying(ep))
  if (playing) return playing.slug
  return episodes.value.find(ep => ep.critique?.pros?.length || ep.critique?.cons?.length)?.slug ?? null
})
function toggleRow(ep) { picked.value = openSlug.value === ep.slug ? '' : ep.slug }

function onPlay(ep) {
  if (isEpPlaying(ep)) togglePause()
  else playEp(ep)
}

// The main button: resume the test of this game left partway, else play the
// newest. `playEp` resumes on its own (`resumeTimeFor`); this only picks which.
const resumeEntry = computed(() =>
  playerStore.inProgress.find(p => p.gameSlug === game.value?.slug && episodes.value.some(ep => ep.slug === p.episodeSlug)) ?? null)
const leadEp = computed(() =>
  (resumeEntry.value && episodes.value.find(ep => ep.slug === resumeEntry.value.episodeSlug)) ?? episodes.value[0] ?? null)
const leadLabel = computed(() => {
  const ep = leadEp.value
  if (!ep) return ''
  const show = ep.podcast?.name ?? podcastMeta(ep.podcast?.id)?.name ?? ''
  if (isEpPlaying(ep)) return playerStore.paused ? `Reprendre · ${show}` : 'Pause'
  if (resumeEntry.value) return `Reprendre à ${formatTime(resumeEntry.value.currentTime)} · ${show}`
  return `Écouter le dernier test · ${show}`
})

// Other games tested in this game's episodes: the way out of the page.
const SAME_MAX = 12
const sameEpisodeGames = computed(() => {
  const seen = new Set([game.value?.slug])
  const out = []
  for (const ep of episodes.value)
    for (const g of ep.games ?? [])
      if (g.slug && !seen.has(g.slug) && out.length < SAME_MAX) {
        seen.add(g.slug)
        out.push({ slug: g.slug, name: g.resolvedName ?? g.name, cover: g.coverImageId ?? null })
      }
  return out
})

function viewEp(ep) {
  router.push({ path: `/episode/${encodeURIComponent(ep.urlSlug)}`, query: game.value.slug ? { game: game.value.slug } : {} })
}

// Say where « back » goes when we know it.
const backFrom  = String(router.options.history.state?.back ?? '')
const backLabel = backFrom.startsWith('/jeux') ? 'Jeux'
  : backFrom === '/' || backFrom.startsWith('/?') ? 'Tests'
  : backFrom.startsWith('/episode/') ? 'Épisode'
  : 'Retour'

function close() {
  if (router.options.history.state?.back) router.back()
  else router.push('/jeux')
}

function onKeydown(e) {
  if (trailerOpen.value) {
    if (e.key === 'Escape') trailerOpen.value = false
    return
  }
  if (lightboxAt.value != null) {
    if (e.key === 'Escape')     { closeLightbox(); return }
    if (e.key === 'Tab')        { trapTab(e); return }
    if (e.key === 'ArrowLeft')  stepLightbox(-1)
    if (e.key === 'ArrowRight') stepLightbox(1)
    return
  }
  if (e.key === 'Escape' && !pickerOpen.value) close()
}
onUnmounted(() => {
  document.body.style.overflow = ''
  document.removeEventListener('keydown', onKeydown)
})

function stepLightbox(dir) {
  const n = lightboxImages.value.length
  if (n) lightboxAt.value = (lightboxAt.value + dir + n) % n
}

const facts = computed(() => {
  const d = igdb.value
  if (!d) return []
  const studio = [d.developer, d.publisher !== d.developer ? d.publisher : null].filter(Boolean).join(' · ')
  return [
    ['Sortie',      d.released],
    ['Studio',      studio],
    ['Plateformes', platforms.value.join(' · ')],
    ['Genres',      (d.genres ?? []).map(frLabel).join(' · ')],
    ['Mode',        [...(d.modes ?? []), ...(d.perspectives ?? [])].map(frLabel).join(' · ')],
    ['Série',       d.franchise],
    ['Durée',       d.timeToBeatHours ? `${d.timeToBeatHours} h` : null],
    ['Metacritic',  d.metacritic],
  ].filter(([, v]) => v)
})
</script>

<template>
  <div class="overlay-page" :style="[theme, { zIndex: 'var(--z-detail)' }]">
    <BackBar :label="backLabel" :overlay="!!game" :solid="scrolled" @back="close">
      <template #actions>
        <button
          v-if="admin && pickerTarget"
          type="button"
          class="icon-action"
          aria-label="Corriger la fiche IGDB"
          title="Corriger la fiche IGDB"
          @click="pickerOpen = true"
        ><Wrench :size="16" :stroke-width="2" /></button>
        <button
          v-if="admin && game"
          type="button"
          class="icon-action"
          :disabled="igdbRefreshing"
          :aria-label="igdbRefreshing ? 'Actualisation IGDB…' : 'Rafraîchir IGDB'"
          title="Rafraîchir IGDB"
          @click="refreshIgdb"
        ><RotateCw :size="16" :stroke-width="2" :class="{ 'animate-spin': igdbRefreshing }" /></button>
      </template>
    </BackBar>

    <div v-if="gamesStore.loading || !game" class="state">
      <span v-if="gamesStore.loading" class="lab">Chargement…</span>
      <p v-else class="cond state__title">Jeu introuvable</p>
    </div>

    <div v-else class="detail scroll-area" @scroll.passive="onScroll">
      <!-- The cover, blurred, is the page's backdrop: the page bathes in the game. -->
      <div v-if="coverImageId && !coverFailed" class="backdrop" aria-hidden="true">
        <img :src="igdbUrl(coverImageId, 't_cover_big')" alt="" />
      </div>

      <div class="content">

        <!-- Hero: the cover, large and framed; beside it the game -->
        <section class="gamehead">
          <button
            v-if="coverImageId && !coverFailed"
            ref="heroCoverEl"
            type="button"
            class="gamehead__cover corners"
            aria-label="Agrandir la pochette"
            @click="openLightbox(coverImageId)"
          >
            <img
              :src="igdbUrl(coverImageId, 't_cover_big_2x')"
              :srcset="`${igdbUrl(coverImageId,'t_cover_big')} 264w, ${igdbUrl(coverImageId,'t_cover_big_2x')} 528w, ${igdbUrl(coverImageId,'t_720p')} 720w`"
              sizes="(min-width: 900px) 460px, 62vw"
              :alt="`Pochette de ${game.name}`"
              fetchpriority="high"
              @error="coverFailed = true"
            />
          </button>
          <div v-else ref="heroCoverEl" class="gamehead__cover gamehead__cover--none corners cond">{{ game.name }}</div>

          <div class="gamehead__main">
            <div v-if="kicker" class="lab gamehead__kicker">{{ kicker }}</div>
            <h1 class="gamehead__title cond">{{ game.name }}</h1>
            <p v-if="byline" class="gamehead__byline">{{ byline }}</p>
            <div v-if="gauges.length" class="gauges">
              <div v-for="g in gauges" :key="g.label" class="gauge">
                <div class="gauge__head lab"><span>{{ g.label }}</span><span>{{ g.value }}</span></div>
                <div class="gauge__bar"><span :style="{ width: g.pct + '%' }"></span></div>
              </div>
            </div>
            <p v-if="verdictLine" class="gamehead__verdicts">{{ verdictLine }}</p>
            <div class="gamehead__actions">
              <button v-if="leadEp?.audioUrl" type="button" class="btn-play gamehead__play" @click="onPlay(leadEp)">
                <Pause v-if="isEpPlaying(leadEp) && !playerStore.paused" :size="14" fill="currentColor" :stroke-width="0" />
                <Play v-else :size="14" fill="currentColor" :stroke-width="0" />
                {{ leadLabel }}
              </button>
              <button v-if="igdb?.trailerId" type="button" class="btn-line" @click="trailerOpen = true">Bande-annonce</button>
            </div>
            <div v-if="heroShots.length" class="gamehead__shots">
              <button v-for="id in heroShots" :key="id" type="button" class="shot" aria-label="Agrandir l’image" @click="openLightbox(id)">
                <img :src="igdbUrl(id, 't_screenshot_med')" alt="" />
              </button>
            </div>
          </div>
        </section>

        <!-- The tests: a journal, one row per test -->
        <section class="panel journal" aria-labelledby="h-tests">
          <div class="journal__head">
            <h2 id="h-tests" class="lab journal__title">Journal des tests</h2>
            <span class="journal__count">{{ formatEpisodeCount(episodes.length || game.episodeCount) }}</span>
          </div>

          <div v-if="episodesLoading" aria-hidden="true">
            <div v-for="i in 3" :key="i" class="skeleton-shimmer test__skel" />
          </div>

          <template v-else>
          <article
            v-for="ep in episodes"
            :key="ep.slug"
            class="test"
            :class="{ 'is-open': openSlug === ep.slug, 'is-playing': isEpPlaying(ep) }"
          >
            <div class="test__row">
              <button
                type="button"
                class="test__toggle"
                :aria-expanded="openSlug === ep.slug"
                @click="toggleRow(ep)"
              >
                <span class="test__mark" aria-hidden="true">{{ openSlug === ep.slug ? '▾' : '▸' }}</span>
                <span class="test__who">
                  <span class="test__show">{{ ep.podcast?.name ?? '' }}</span>
                  <span class="test__when mono">{{ formatShortDate(ep.pubTs) }} · début {{ formatTime(ep.timestampSeconds) }}</span>
                </span>
                <VerdictMark :verdict="ep.critique?.verdict ?? null" class="test__verdict" />
                <span class="test__title ellipsis">{{ ep.title }}</span>
              </button>
              <div class="test__actions">
                <button
                  type="button"
                  :class="isEpPlaying(ep) ? 'btn-play' : 'btn-line'"
                  :disabled="!ep.audioUrl"
                  :aria-label="isEpPlaying(ep) && !playerStore.paused ? 'Pause' : `Écouter le test de ${ep.podcast?.name ?? ''} à ${formatTime(ep.timestampSeconds)}`"
                  @click="onPlay(ep)"
                >
                  <Pause v-if="isEpPlaying(ep) && !playerStore.paused" :size="12" fill="currentColor" :stroke-width="0" />
                  <Play v-else :size="12" fill="currentColor" :stroke-width="0" />
                  Écouter
                </button>
                <button type="button" class="btn-line" :aria-label="`L'épisode : ${ep.title}`" @click="viewEp(ep)">
                  Épisode <ChevronRight :size="14" :stroke-width="2" aria-hidden="true" />
                </button>
              </div>
            </div>

            <div v-if="openSlug === ep.slug" class="test__opinion">
              <template v-if="ep.critique?.pros?.length || ep.critique?.cons?.length">
                <div>
                  <div class="lab test__side test__side--pro">Points forts</div>
                  <ul><li v-for="p in ep.critique.pros" :key="p"><span class="sign">+</span>{{ p }}</li></ul>
                </div>
                <div>
                  <div class="lab test__side">Points faibles</div>
                  <ul><li v-for="c in ep.critique.cons" :key="c"><span class="sign">−</span>{{ c }}</li></ul>
                </div>
              </template>
              <p v-else class="test__empty">Pas encore de lecture de ce test : ni verdict, ni points forts, ni points faibles.</p>
            </div>
          </article>
          </template>
        </section>

        <!-- Gallery: the trailer first, then key art and screenshots -->
        <section v-if="igdb?.trailerId || mediaImages.length" class="panel board" aria-labelledby="h-board">
          <div class="journal__head">
            <h2 id="h-board" class="lab journal__title">Galerie</h2>
            <span class="journal__count">{{ mediaImages.length }} images<template v-if="igdb?.trailerId"> · bande-annonce</template></span>
          </div>
          <div class="board__grid">
            <button v-if="igdb?.trailerId" type="button" class="board__tile board__trailer" aria-label="Lire la bande-annonce" @click="trailerOpen = true">
              <img
                :src="`https://i.ytimg.com/vi/${igdb.trailerId}/maxresdefault.jpg`"
                alt=""
                loading="lazy"
                @error="e => e.target.src = `https://i.ytimg.com/vi/${igdb.trailerId}/hqdefault.jpg`"
              />
              <span class="board__play"><Play :size="22" fill="currentColor" :stroke-width="0" /></span>
              <span class="lab board__label">Bande-annonce</span>
            </button>
            <button
              v-for="(id, i) in boardImages"
              :key="id"
              type="button"
              class="board__tile"
              :aria-label="boardMore && i === boardImages.length - 1 ? `Voir les ${mediaImages.length} images` : 'Agrandir l’image'"
              @click="openLightbox(id)"
            >
              <img :src="igdbUrl(id, 't_screenshot_big')" :srcset="`${igdbUrl(id,'t_screenshot_med')} 569w, ${igdbUrl(id,'t_screenshot_big')} 889w, ${igdbUrl(id,'t_screenshot_huge')} 1280w`" sizes="(min-width: 900px) 33vw, 50vw" alt="" loading="lazy" />
              <span v-if="boardMore && i === boardImages.length - 1" class="board__more cond">+{{ boardMore }}</span>
            </button>
          </div>
        </section>

        <!-- Way out: the other games these episodes test (covers alone) -->
        <section v-if="sameEpisodeGames.length" class="same" aria-labelledby="h-same">
          <div class="section-head">
            <h2 id="h-same">Dans les mêmes épisodes</h2>
            <span class="lab">{{ sameEpisodeGames.length }}</span>
          </div>
          <div class="same__grid">
            <RouterLink v-for="g in sameEpisodeGames" :key="g.slug" :to="`/game/${encodeURIComponent(g.slug)}`" class="same__tile" :aria-label="g.name">
              <img v-if="g.cover" :src="igdbUrl(g.cover, 't_cover_big')" alt="" loading="lazy" />
              <span v-else class="same__nocover cond">{{ g.name }}</span>
            </RouterLink>
          </div>
        </section>

        <!-- Fiche technique -->
        <section v-if="facts.length || igdb?.steamUrl || igdb?.officialUrl || igdb?.wikiUrl" class="panel facts" aria-labelledby="h-facts">
          <div class="journal__head">
            <h2 id="h-facts" class="lab journal__title">Fiche technique</h2>
          </div>
          <dl class="facts__grid">
            <div v-for="[k, v] in facts" :key="k" class="facts__cell">
              <dt class="lab">{{ k }}</dt><dd>{{ v }}</dd>
            </div>
            <div v-if="igdb?.steamUrl || igdb?.officialUrl || igdb?.wikiUrl" class="facts__cell">
              <dt class="lab">Liens</dt>
              <dd class="facts__links">
                <a v-if="igdb?.steamUrl" :href="igdb.steamUrl" target="_blank" rel="noopener noreferrer">Steam</a>
                <a v-if="igdb?.officialUrl" :href="igdb.officialUrl" target="_blank" rel="noopener noreferrer">Site officiel</a>
                <a v-if="igdb?.wikiUrl" :href="igdb.wikiUrl" target="_blank" rel="noopener noreferrer">Wikipédia</a>
              </dd>
            </div>
          </dl>
          <details v-if="igdb?.description || igdb?.storyline" class="about">
            <summary class="lab">Présentation <span class="about__src">(IGDB, en anglais)</span></summary>
            <p v-if="igdb?.description">{{ igdb.description }}</p>
            <p v-if="igdb?.storyline" class="about__story">{{ igdb.storyline }}</p>
          </details>
        </section>

      </div>
    </div>

    <!-- Lightbox: the cover, then the images -->
    <Teleport to="body">
      <div v-if="lightboxId" ref="lightboxEl" class="lightbox" role="dialog" aria-modal="true" aria-label="Images" @click.self="closeLightbox">
        <button type="button" class="icon-action lightbox__close" aria-label="Fermer" @click="closeLightbox"><X :size="20" :stroke-width="2" /></button>
        <button v-if="lightboxImages.length > 1" type="button" class="icon-action lightbox__prev" aria-label="Précédente" @click="stepLightbox(-1)"><ChevronLeft :size="24" :stroke-width="2" /></button>
        <button v-if="lightboxImages.length > 1" type="button" class="icon-action lightbox__next" aria-label="Suivante" @click="stepLightbox(1)"><ChevronRight :size="24" :stroke-width="2" /></button>
        <img
          class="lightbox__img"
          :src="igdbUrl(lightboxId, 't_1080p')"
          :srcset="`${igdbUrl(lightboxId, 't_screenshot_huge')} 1280w, ${igdbUrl(lightboxId, 't_1080p')} 1920w`"
          sizes="92vw"
          alt=""
        />
        <div class="lab lightbox__count">{{ lightboxAt + 1 }} / {{ lightboxImages.length }}</div>
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

    <!-- Trailer -->
    <Teleport to="body">
      <div v-if="trailerOpen && igdb?.trailerId" class="lightbox" @click.self="trailerOpen = false">
        <button type="button" class="icon-action lightbox__close" aria-label="Fermer" @click="trailerOpen = false"><X :size="20" :stroke-width="2" /></button>
        <div class="trailer">
          <iframe
            :src="`https://www.youtube-nocookie.com/embed/${igdb.trailerId}?autoplay=1&rel=0`"
            title="Bande-annonce"
            allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
            allowfullscreen
          />
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.state { flex: 1; display: flex; align-items: center; justify-content: center; }
.state__title { font-size: var(--text-2xl); }

.detail { position: relative; }
/* ─── Backdrop: the cover, blurred, fading into the game's ground ──────── */
.backdrop {
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  height: 900px;
  overflow: hidden;
  pointer-events: none;
}
.backdrop img {
  position: absolute;
  inset: -120px;
  width: calc(100% + 240px);
  height: calc(100% + 240px);
  object-fit: cover;
  filter: blur(60px) saturate(1.3);
  opacity: 0.55;
}
.backdrop::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, rgba(0, 0, 0, 0.15) 0%, var(--game-veil) 55%, var(--c-bg) 100%);
}
.detail .content { position: relative; }

/* ─── Hero ────────────────────────────────────────────────────────────── */
.gamehead {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  justify-items: center;
  gap: 18px;
  padding: 72px 0 40px;
  text-align: center;
}
.gamehead__cover {
  --corner: 22px;
  --corner-out: 10px;
  width: min(62vw, 260px);
  aspect-ratio: 3 / 4;
  padding: 0;
  border: 0;
  background: var(--c-surface);
  box-shadow: var(--shadow-cover);
  cursor: zoom-in;
}
.gamehead__cover img { width: 100%; height: 100%; object-fit: cover; display: block; }
.gamehead__cover--none {
  display: flex;
  align-items: flex-end;
  padding: 14px;
  font-size: 24px;
  color: var(--c-fg-2);
  cursor: default;
  box-sizing: border-box;
}
.gamehead__main { display: flex; flex-direction: column; align-items: center; gap: 14px; min-width: 0; width: 100%; }
.gamehead__kicker { color: var(--c-accent); }
.gamehead__title { margin: 0; font-size: clamp(30px, 8vw, 72px); line-height: 1; overflow-wrap: anywhere; }
.gamehead__byline { margin: 0; color: var(--c-fg-2); }
.gamehead__verdicts { margin: 0; font-family: var(--font-display); font-weight: 600; font-size: var(--text-sm); letter-spacing: 0.04em; }
.gauges { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px 24px; width: 100%; max-width: 560px; text-align: left; }
.gauge__head { display: flex; justify-content: space-between; gap: 8px; color: var(--c-fg); }
.gauge__bar { height: 8px; margin-top: 6px; background: rgba(255, 255, 255, 0.12); box-shadow: inset 0 0 0 1px var(--c-line); }
.gauge__bar span { display: block; height: 100%; background: var(--c-accent); }
.gamehead__actions { display: flex; flex-wrap: wrap; gap: 10px; justify-content: center; width: 100%; }
.gamehead__play { min-height: 52px; flex: 1 1 100%; }
.gamehead__shots { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; width: 100%; max-width: 600px; }
.shot { aspect-ratio: 16 / 9; padding: 3px; border: 0; background: rgba(0, 0, 0, 0.35); box-shadow: inset 0 0 0 1px var(--c-line); cursor: zoom-in; }
.shot img { width: 100%; height: 100%; object-fit: cover; display: block; }

@media (min-width: 900px) {
  .gamehead { grid-template-columns: 460px minmax(0, 1fr); justify-items: stretch; align-items: center; gap: 56px; padding: 48px 0 56px; text-align: left; }
  .gamehead__cover { width: 460px; }
  .gamehead__main { align-items: flex-start; gap: 20px; }
  .gamehead__actions { justify-content: flex-start; }
  .gamehead__play { flex: 0 0 auto; }
}

/* ─── Panels: the journal, the gallery, the facts ─────────────────────── */
.panel { margin-bottom: 32px; background: var(--c-surface); box-shadow: inset 0 0 0 1px var(--c-line); }
.journal__head { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; padding: 14px 20px; border-bottom: 1px solid var(--c-line); }
.journal__title { margin: 0; color: var(--c-fg); font-size: 13px; }
.journal__count { color: var(--c-fg-2); font-size: var(--text-sm); }

.test__skel { height: 64px; margin: 1px 0; }
.test { border-bottom: 1px solid var(--c-line); }
.test:last-child { border-bottom: 0; }
.test.is-open { background: rgba(255, 255, 255, 0.04); box-shadow: inset 3px 0 0 var(--c-accent); }
.test__row { display: flex; flex-direction: column; gap: 10px; padding: 12px 16px; }
.test__toggle {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr) auto;
  grid-template-areas: "mark who verdict" ". title title";
  gap: 4px 10px;
  align-items: center;
  border: 0;
  background: transparent;
  color: var(--c-fg);
  text-align: left;
  padding: 0;
  cursor: pointer;
}
.test__mark { grid-area: mark; color: var(--c-accent); }
.test__who { grid-area: who; display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.test__show { font-weight: 600; font-size: var(--text-md); }
.test__when { color: var(--c-fg-2); font-size: var(--text-xs); }
.test__verdict { grid-area: verdict; }
.test__title { grid-area: title; color: var(--c-fg-2); font-size: var(--text-sm); min-width: 0; }
.test__toggle:hover .test__show { text-decoration: underline; text-underline-offset: 3px; }
.test__actions { display: flex; gap: 8px; }
.test__actions > * { flex: 1; min-height: 40px; padding: 0 12px; font-size: 12px; }

.test__opinion { display: grid; grid-template-columns: minmax(0, 1fr); gap: 18px; padding: 0 16px 18px 42px; }
.test__side { color: var(--c-fg-2); }
.test__side--pro { color: var(--c-accent); }
.test__opinion ul { list-style: none; margin: 8px 0 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.test__opinion li { display: flex; gap: 10px; line-height: 1.45; }
.sign { font-weight: 700; color: var(--c-fg-2); }
.test__opinion div:first-child .sign { color: var(--c-accent); }
.test__empty { margin: 0; color: var(--c-fg-2); }

@media (min-width: 900px) {
  .test__row { flex-direction: row; align-items: center; gap: 16px; min-height: 60px; padding: 8px 20px; }
  .test__toggle {
    flex: 1 1 0;
    min-width: 0;
    grid-template-columns: 16px 240px 120px minmax(0, 1fr);
    grid-template-areas: "mark who verdict title";
    gap: 16px;
  }
  .test__actions > * { flex: 0 0 auto; width: 128px; }
  .test__opinion { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 32px; padding: 0 20px 20px 52px; }
}

/* ─── Gallery ─────────────────────────────────────────────────────────── */
.board__grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; padding: 16px; }
@media (min-width: 900px) { .board__grid { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; padding: 20px; } }
.board__tile {
  position: relative;
  aspect-ratio: 16 / 9;
  padding: 0;
  border: 0;
  background: var(--c-bg);
  overflow: hidden;
  cursor: zoom-in;
}
.board__tile img { width: 100%; height: 100%; object-fit: cover; display: block; transition: transform var(--dur-med) var(--ease-out-soft); }
.board__tile:hover img { transform: scale(1.03); }
.board__trailer { grid-column: 1 / -1; cursor: pointer; }
@media (min-width: 900px) { .board__trailer { grid-column: span 2; grid-row: span 2; aspect-ratio: auto; } }
.board__trailer::after { content: ''; position: absolute; inset: 0; background: linear-gradient(180deg, rgba(9, 9, 12, 0) 50%, rgba(9, 9, 12, 0.75) 100%); }
.board__play {
  position: absolute;
  left: 16px;
  bottom: 16px;
  z-index: 1;
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--c-accent);
  color: var(--c-accent-fg);
}
.board__label { position: absolute; left: 88px; bottom: 34px; z-index: 1; color: var(--c-fg); }
.board__more {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(9, 9, 12, 0.7);
  font-size: 40px;
  color: var(--c-fg);
}

/* ─── Dans les mêmes épisodes: covers alone ──────────────────────────── */
.same { margin-bottom: 32px; }
.same__grid {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: 112px;
  gap: 12px;
  overflow-x: auto;
  scroll-snap-type: x proximity;
  padding: 4px 4px 8px;
}
@media (min-width: 900px) { .same__grid { grid-auto-columns: 150px; gap: 16px; } }
.same__tile { display: block; aspect-ratio: 3 / 4; scroll-snap-align: start; box-shadow: 0 0 0 1px var(--c-line); transition: box-shadow var(--dur-fast); }
.same__tile:hover, .same__tile:focus-visible { box-shadow: 0 0 0 1px var(--c-accent); outline: none; }
.same__tile img { width: 100%; height: 100%; object-fit: cover; display: block; }
.same__nocover { display: flex; align-items: flex-end; height: 100%; padding: 8px; box-sizing: border-box; font-size: 15px; background: var(--c-surface); color: var(--c-fg-2); }

/* ─── Fiche technique ─────────────────────────────────────────────────── */
.facts__grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); margin: 0; }
@media (min-width: 900px) { .facts__grid { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
.facts__cell { padding: 14px 20px; min-width: 0; border-bottom: 1px solid var(--c-line); }
.facts__cell dd { margin: 6px 0 0; color: var(--c-fg); overflow-wrap: anywhere; }
.facts__links { display: flex; flex-wrap: wrap; gap: 4px 14px; }
.facts__links a { color: var(--c-fg); text-decoration: underline; text-underline-offset: 3px; }
.facts__links a:hover { color: var(--c-accent); }
.about { padding: 0 20px; }
.about summary { min-height: 48px; display: flex; align-items: center; cursor: pointer; }
.about__src { margin-left: 8px; letter-spacing: 0.04em; text-transform: none; }
.about p { color: var(--c-fg-2); max-width: 75ch; margin: 0 0 16px; }
.about__story { white-space: pre-line; }

.lightbox {
  position: fixed;
  inset: 0;
  z-index: var(--z-lightbox);
  background: rgba(0, 0, 0, 0.94);
  display: flex;
  align-items: center;
  justify-content: center;
}
.lightbox__img { max-width: 92vw; max-height: 84vh; object-fit: contain; }
.lightbox__close { position: absolute; top: calc(8px + env(safe-area-inset-top, 0px)); right: 8px; }
.lightbox__prev  { position: absolute; left: 8px; top: 50%; transform: translateY(-50%); }
.lightbox__next  { position: absolute; right: 8px; top: 50%; transform: translateY(-50%); }
.lightbox__count { position: absolute; bottom: calc(16px + env(safe-area-inset-bottom, 0px)); }
.trailer { width: min(92vw, 1100px); aspect-ratio: 16 / 9; }
.trailer iframe { width: 100%; height: 100%; border: 0; display: block; }
</style>
