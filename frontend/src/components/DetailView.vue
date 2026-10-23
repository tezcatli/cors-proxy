<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { formatShortDate, formatEpisodeCount } from '../lib/utils.js'
import { igdbUrl } from '../lib/igdbCdn.js'
import { verdictCounts } from '../lib/verdicts.js'
import { podcastMeta } from '../lib/podcasts.js'
import { useGamesStore } from '../stores/games.js'
import { usePlayerStore } from '../stores/player.js'
import { fetchGameDetail, refreshGameIgdb } from '../lib/games.js'
import { isAdmin } from '../lib/auth.js'
import { useEpisodePlayer } from '../composables/useEpisodePlayer.js'
import { playInto } from '../lib/flipTransition.js'
import BackBar from './BackBar.vue'
import VerdictMark from './VerdictMark.vue'
import IgdbPickerModal from './IgdbPickerModal.vue'
import { RotateCw, ChevronLeft, ChevronRight, X, Play, Pause, Wrench, ArrowUpRight } from 'lucide-vue-next'

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

const platforms = computed(() =>
  (igdb.value?.platforms ?? []).map(p => typeof p === 'string' ? p : p.label))

const coverFailed        = ref(false)
const selectedScreenshot = ref(null)
const trailerOpen        = ref(false)

// Media strip: key art first, then gameplay screenshots.
const mediaImages = computed(() => [
  ...(igdb.value?.artworkIds ?? []),
  ...(igdb.value?.screenshotIds ?? []),
])
const mediaTrack = ref(null)
function scrollMedia(dir) {
  const t = mediaTrack.value
  if (t) t.scrollBy({ left: dir * t.clientWidth * 0.8, behavior: 'smooth' })
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
  selectedScreenshot.value = null
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

function viewEp(ep) {
  router.push({ path: `/episode/${encodeURIComponent(ep.urlSlug)}`, query: game.value.slug ? { game: game.value.slug } : {} })
}

function close() {
  if (router.options.history.state?.back) router.back()
  else router.push('/jeux')
}

function onKeydown(e) {
  if (trailerOpen.value) {
    if (e.key === 'Escape') trailerOpen.value = false
    return
  }
  if (selectedScreenshot.value) {
    if (e.key === 'Escape')     { selectedScreenshot.value = null; return }
    if (e.key === 'ArrowLeft')  stepScreenshot(-1)
    if (e.key === 'ArrowRight') stepScreenshot(1)
    return
  }
  if (e.key === 'Escape' && !pickerOpen.value) close()
}
onUnmounted(() => {
  document.body.style.overflow = ''
  document.removeEventListener('keydown', onKeydown)
})

function stepScreenshot(dir) {
  const ids = mediaImages.value
  if (!ids.length) return
  const i = ids.indexOf(selectedScreenshot.value)
  selectedScreenshot.value = ids[(i + dir + ids.length) % ids.length]
}

const facts = computed(() => {
  const d = igdb.value
  if (!d) return []
  const studio = [d.developer, d.publisher !== d.developer ? d.publisher : null].filter(Boolean).join(' · ')
  return [
    ['Sortie',      d.released],
    ['Studio',      studio],
    ['Plateformes', platforms.value.join(' · ')],
    ['Genres',      (d.genres ?? []).join(' · ')],
    ['Mode',        [...(d.modes ?? []), ...(d.perspectives ?? [])].join(' · ')],
    ['Série',       d.franchise],
    ['Durée',       d.timeToBeatHours ? `${d.timeToBeatHours} h` : null],
    ['Metacritic',  d.metacritic],
    ['Classement',  d.esrb],
  ].filter(([, v]) => v)
})
</script>

<template>
  <div class="overlay-page" :style="{ zIndex: 'var(--z-detail)' }">
    <BackBar label="Retour" @back="close">
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

    <div v-else class="detail scroll-area">
      <div class="content">

        <!-- Hero: cover · mono facts · giant title · counts -->
        <section class="hero">
          <div ref="heroCoverEl" class="hero__cover">
            <img
              v-if="coverImageId && !coverFailed"
              :src="igdbUrl(coverImageId, 't_cover_big')"
              :srcset="`${igdbUrl(coverImageId,'t_cover_big')} 1x, ${igdbUrl(coverImageId,'t_cover_big_2x')} 2x`"
              :alt="`Pochette de ${game.name}`"
              @error="coverFailed = true"
            />
          </div>
          <div class="hero__main">
            <div class="hero__facts lab">
              <span v-if="igdb?.developer">{{ igdb.developer }}</span>
              <span v-if="igdb?.released">{{ igdb.released }}</span>
              <span v-if="platforms.length">{{ platforms.join(' · ') }}</span>
              <span v-if="igdb?.metacritic">MC {{ igdb.metacritic }}</span>
            </div>
            <h1 class="hero__title cond">{{ game.name }}</h1>
            <dl class="counts">
              <div><dt class="lab">Tests</dt><dd class="cond">{{ episodes.length || game.episodeCount }}</dd></div>
              <div v-if="counts.positive"><dt class="lab">Positif</dt><dd class="cond">▲ {{ counts.positive }}</dd></div>
              <div v-if="counts.mixed"><dt class="lab">Mitigé</dt><dd class="cond">◆ {{ counts.mixed }}</dd></div>
              <div v-if="counts.negative"><dt class="lab">Négatif</dt><dd class="cond">▼ {{ counts.negative }}</dd></div>
              <div v-if="counts.none"><dt class="lab">Non lu</dt><dd class="cond counts__none">○ {{ counts.none }}</dd></div>
            </dl>
          </div>
        </section>

        <!-- The tests -->
        <section class="tests" aria-labelledby="h-tests">
          <div class="section-head">
            <h2 id="h-tests">Les tests</h2>
            <span class="lab">{{ formatEpisodeCount(episodes.length || game.episodeCount) }}</span>
          </div>

          <div class="tests__head lab" aria-hidden="true">
            <span>Émission</span><span>Date</span><span>Verdict</span><span>Début</span><span>Épisode</span><span></span>
          </div>

          <div v-if="episodesLoading" aria-hidden="true">
            <div v-for="i in 3" :key="i" class="skeleton-shimmer tests__skel" />
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
                :aria-label="`${ep.podcast?.name ?? ''}, ${formatShortDate(ep.pubTs)} : pour et contre`"
                @click="toggleRow(ep)"
              >
                <span class="test__show">{{ ep.podcast?.name ?? '' }}<span class="test__sigle mono">{{ podcastMeta(ep.podcast?.id)?.label }}</span></span>
                <span class="mono test__date">{{ formatShortDate(ep.pubTs) }}</span>
                <VerdictMark :verdict="ep.critique?.verdict ?? null" class="test__verdict" />
                <span class="mono test__start">{{ ep.timestamp ?? '0:00' }}</span>
                <span class="test__title ellipsis">{{ ep.title }}</span>
              </button>
              <div class="test__actions">
                <button
                  type="button"
                  :class="isEpPlaying(ep) ? 'btn-play' : 'btn-line'"
                  :disabled="!ep.audioUrl"
                  :aria-label="isEpPlaying(ep) && !playerStore.paused ? 'Pause' : `Écouter le test de ${ep.podcast?.name ?? ''} à ${ep.timestamp ?? '0:00'}`"
                  @click="onPlay(ep)"
                >
                  <Pause v-if="isEpPlaying(ep) && !playerStore.paused" :size="12" fill="currentColor" :stroke-width="0" />
                  <Play v-else :size="12" fill="currentColor" :stroke-width="0" />
                  Écouter
                </button>
                <button type="button" class="icon-action icon-action--boxed" :aria-label="`L'épisode : ${ep.title}`" @click="viewEp(ep)">
                  <ArrowUpRight :size="16" :stroke-width="2" />
                </button>
              </div>
            </div>

            <div v-if="openSlug === ep.slug" class="test__opinion">
              <template v-if="ep.critique?.pros?.length || ep.critique?.cons?.length">
                <div>
                  <div class="lab">Pour</div>
                  <ul><li v-for="p in ep.critique.pros" :key="p"><span class="mono sign">+</span>{{ p }}</li></ul>
                </div>
                <div>
                  <div class="lab">Contre</div>
                  <ul><li v-for="c in ep.critique.cons" :key="c"><span class="mono sign">−</span>{{ c }}</li></ul>
                </div>
              </template>
              <p v-else class="test__empty">Pas encore de lecture de ce test : ni verdict, ni pour, ni contre.</p>
            </div>
          </article>
          </template>
        </section>

        <!-- Fiche technique -->
        <section v-if="facts.length || igdb?.steamUrl || igdb?.officialUrl || igdb?.wikiUrl" class="facts" aria-labelledby="h-facts">
          <h2 id="h-facts" class="lab facts__title">Fiche technique</h2>
          <dl class="facts__grid">
            <div v-for="[k, v] in facts" :key="k" class="facts__cell">
              <dt class="lab">{{ k }}</dt><dd>{{ v }}</dd>
            </div>
            <div v-if="igdb?.steamUrl || igdb?.officialUrl || igdb?.wikiUrl || igdb?.trailerId" class="facts__cell">
              <dt class="lab">Liens</dt>
              <dd class="facts__links">
                <a v-if="igdb?.steamUrl" :href="igdb.steamUrl" target="_blank" rel="noopener noreferrer">Steam</a>
                <a v-if="igdb?.officialUrl" :href="igdb.officialUrl" target="_blank" rel="noopener noreferrer">Site officiel</a>
                <a v-if="igdb?.wikiUrl" :href="igdb.wikiUrl" target="_blank" rel="noopener noreferrer">Wikipédia</a>
                <button v-if="igdb?.trailerId" type="button" class="facts__trailer" @click="trailerOpen = true">Bande-annonce</button>
              </dd>
            </div>
          </dl>
          <details v-if="igdb?.description || igdb?.storyline" class="about">
            <summary class="lab">Présentation <span class="about__src">(IGDB, en anglais)</span></summary>
            <p v-if="igdb?.description">{{ igdb.description }}</p>
            <p v-if="igdb?.storyline" class="about__story">{{ igdb.storyline }}</p>
          </details>
        </section>

        <!-- Media -->
        <section v-if="mediaImages.length" class="media" aria-label="Images">
          <div ref="mediaTrack" class="media__track">
            <button
              v-for="id in mediaImages"
              :key="id"
              type="button"
              class="media__slide"
              aria-label="Agrandir l’image"
              @click="selectedScreenshot = id"
            >
              <img :src="igdbUrl(id, 't_screenshot_big')" :srcset="`${igdbUrl(id, 't_screenshot_med')} 1x, ${igdbUrl(id, 't_screenshot_huge')} 2x`" alt="" loading="lazy" />
            </button>
          </div>
          <div v-if="mediaImages.length > 2" class="media__nav">
            <button type="button" class="icon-action icon-action--boxed" aria-label="Images précédentes" @click="scrollMedia(-1)"><ChevronLeft :size="18" :stroke-width="2" /></button>
            <button type="button" class="icon-action icon-action--boxed" aria-label="Images suivantes" @click="scrollMedia(1)"><ChevronRight :size="18" :stroke-width="2" /></button>
          </div>
        </section>
      </div>
    </div>

    <!-- Screenshot lightbox -->
    <Teleport to="body">
      <div v-if="selectedScreenshot" class="lightbox" @click.self="selectedScreenshot = null">
        <button type="button" class="icon-action lightbox__close" aria-label="Fermer" @click="selectedScreenshot = null"><X :size="20" :stroke-width="2" /></button>
        <button v-if="mediaImages.length > 1" type="button" class="icon-action lightbox__prev" aria-label="Précédente" @click="stepScreenshot(-1)"><ChevronLeft :size="24" :stroke-width="2" /></button>
        <button v-if="mediaImages.length > 1" type="button" class="icon-action lightbox__next" aria-label="Suivante" @click="stepScreenshot(1)"><ChevronRight :size="24" :stroke-width="2" /></button>
        <img
          class="lightbox__img"
          :src="igdbUrl(selectedScreenshot, 't_screenshot_huge')"
          :srcset="`${igdbUrl(selectedScreenshot, 't_screenshot_huge')} 1280w, ${igdbUrl(selectedScreenshot, 't_1080p')} 1920w`"
          sizes="100vw"
          alt=""
        />
        <div class="lab lightbox__count">{{ mediaImages.indexOf(selectedScreenshot) + 1 }} / {{ mediaImages.length }}</div>
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

.hero {
  display: grid;
  grid-template-columns: 112px minmax(0, 1fr);
  gap: 16px 20px;
  padding: 24px 0 32px;
}
.hero__cover { width: 112px; aspect-ratio: 3 / 4; background: var(--c-surface); box-shadow: var(--shadow-cover); }
.hero__cover img { width: 100%; height: 100%; object-fit: cover; display: block; }
.hero__main { display: contents; }
.hero__facts { grid-column: 2; align-self: end; display: flex; flex-direction: column; gap: 6px; }
.hero__title {
  grid-column: 1 / -1;
  margin: 0;
  font-size: clamp(44px, 12vw, 132px);
  font-weight: 800;
  line-height: 0.86;
  overflow-wrap: anywhere;
}
.counts {
  grid-column: 1 / -1;
  justify-self: stretch;
  width: 100%;
  display: flex;
  flex-wrap: wrap;
  margin: 0;
  box-shadow: inset 0 0 0 1px var(--c-line);
}
.counts > div { flex: 1 1 0; min-width: 80px; padding: 12px 16px; box-shadow: 1px 0 0 var(--c-line); }
.counts dd { margin: 4px 0 0; font-size: 32px; }
.counts__none { color: var(--c-fg-3); }

@media (min-width: 768px) {
  .hero { grid-template-columns: 240px minmax(0, 1fr); gap: 40px; padding: 48px 0 56px; }
  .hero__cover { width: 240px; grid-column: 1; grid-row: 1; }
  .hero__main { grid-column: 2; grid-row: 1; display: flex; flex-direction: column; justify-content: space-between; gap: 24px; min-width: 0; }
  .hero__facts { flex-direction: row; flex-wrap: wrap; gap: 8px 24px; align-self: flex-start; }
  .hero__title { font-size: clamp(56px, 8vw, 132px); }
}

/* ─── Tests table ─────────────────────────────────────────────────────── */
.tests { margin-bottom: 56px; }
.tests__head { display: none; }
.tests__skel { height: 72px; margin-bottom: 1px; }
.test { border-top: 1px solid var(--c-line); }
.test:last-child { border-bottom: 1px solid var(--c-line); }
.test.is-open { background: var(--c-surface); box-shadow: inset 3px 0 0 var(--c-accent); }
.test__row { display: flex; flex-direction: column; gap: 12px; padding: 14px 12px; }
.test__toggle {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  grid-template-areas: "show verdict" "date start" "title title";
  gap: 4px 12px;
  border: 0;
  background: transparent;
  color: var(--c-fg);
  text-align: left;
  padding: 0;
  cursor: pointer;
}
.test__show { grid-area: show; font-weight: 600; font-size: var(--text-lg); }
.test__sigle { display: none; }
.test__date { grid-area: date; color: var(--c-fg-2); }
.test__verdict { grid-area: verdict; justify-self: end; }
.test__start { grid-area: start; justify-self: end; color: var(--c-fg-2); }
.test__title { grid-area: title; color: var(--c-fg-3); min-width: 0; }
.test__actions { display: flex; gap: 8px; }
.test__actions .btn-play, .test__actions .btn-line { flex: 1; }

.test__opinion {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 20px;
  padding: 4px 12px 20px;
}
.test__opinion ul { list-style: none; margin: 8px 0 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.test__opinion li { display: flex; gap: 10px; color: var(--c-fg-2); line-height: 1.5; }
.sign { color: var(--c-accent); font-weight: 700; }
.test__opinion div:nth-child(2) .sign { color: var(--c-fg); }
.test__empty { margin: 0; color: var(--c-fg-3); }

@media (min-width: 900px) {
  .tests__head, .test__toggle {
    grid-template-columns: 200px 120px 140px 90px minmax(0, 1fr);
    grid-template-areas: none;
    align-items: center;
  }
  .tests__head { display: grid; gap: 16px; padding: 0 172px 10px 12px; }
  .test__row { flex-direction: row; align-items: center; gap: 16px; min-height: 64px; padding: 8px 12px; }
  .test__toggle { flex: 1 1 0; min-width: 0; overflow: hidden; gap: 16px; }
  .test__toggle > * { grid-area: auto; justify-self: start; }
  .test__toggle > .test__title { justify-self: stretch; }
  .test__show { font-size: var(--text-md); }
  .test__actions .btn-play, .test__actions .btn-line { flex: 0 0 auto; width: 120px; }
  .test__opinion { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 32px; padding: 0 12px 24px; }
}

/* ─── Fiche technique ─────────────────────────────────────────────────── */
.facts { margin-bottom: 56px; }
.facts__title { margin: 0; padding: 14px 16px; box-shadow: inset 0 0 0 1px var(--c-line); }
.facts__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin: 0;
  gap: 1px;
  background: var(--c-line);
  box-shadow: 0 0 0 1px var(--c-line);
}
@media (min-width: 900px) { .facts__grid { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
.facts__cell { background: var(--c-bg); padding: 14px 16px; min-width: 0; }
.facts__cell dd { margin: 6px 0 0; color: var(--c-fg); overflow-wrap: anywhere; }
.facts__links { display: flex; flex-wrap: wrap; gap: 4px 14px; }
.facts__links a, .facts__trailer { color: var(--c-fg); text-decoration: underline; text-underline-offset: 3px; background: none; border: 0; padding: 0; cursor: pointer; font: inherit; }
.facts__links a:hover, .facts__trailer:hover { color: var(--c-accent); }
.about { box-shadow: inset 0 0 0 1px var(--c-line); margin-top: -1px; padding: 0 16px; }
.about summary { min-height: 44px; display: flex; align-items: center; cursor: pointer; }
.about__src { margin-left: 8px; letter-spacing: 0.04em; text-transform: none; }
.about p { color: var(--c-fg-2); max-width: 75ch; margin: 0 0 16px; }
.about__story { white-space: pre-line; }

/* ─── Media ───────────────────────────────────────────────────────────── */
.media { margin-bottom: 40px; }
.media__track { display: flex; gap: 12px; overflow-x: auto; scroll-snap-type: x mandatory; scrollbar-width: none; }
.media__track::-webkit-scrollbar { display: none; }
.media__slide { flex: 0 0 85%; aspect-ratio: 16 / 9; padding: 0; border: 0; background: var(--c-surface); cursor: zoom-in; scroll-snap-align: start; }
@media (min-width: 768px) { .media__slide { flex-basis: calc((100% - 24px) / 3); } }
.media__slide img { width: 100%; height: 100%; object-fit: cover; display: block; }
.media__nav { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; }

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
