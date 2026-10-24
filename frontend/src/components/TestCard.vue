<script setup>
import { computed } from 'vue'
import { Play, Pause } from 'lucide-vue-next'
import { formatShortDate, testHref } from '../lib/utils.js'
import { igdbUrl } from '../lib/igdbCdn.js'
import { verdictMeta } from '../lib/verdicts.js'
import { useGameTheme } from '../composables/useGameTheme.js'

// One test of the home feed — a game an episode tests — told by its cover: the
// verdict's word on it, then the show and the date (the game's name is on the
// cover, and in the accessible name). The card opens the game's page on that
// test (`testHref`); a test without a page opens its episode.
// `featured`: the newest test, large, with its own play button.
const props = defineProps({
  item:      Object,     // { ep, test }
  featured:  Boolean,
  isPlaying: Boolean,
  isPaused:  Boolean,
})
const emit = defineEmits(['play', 'togglePause', 'view'])

const ep      = computed(() => props.item.ep)
const test    = computed(() => props.item.test)
const name    = computed(() => test.value.resolvedName ?? test.value.name)
const verdict = computed(() => verdictMeta(test.value.verdict)?.label ?? null)
const show    = computed(() => ep.value.podcast?.name ?? '')
const date    = computed(() => formatShortDate(ep.value.pubTs))
const href    = computed(() => testHref(props.item))
const label   = computed(() => [name.value, show.value, date.value, verdict.value].filter(Boolean).join(' · '))
const hasAudio = computed(() => !!ep.value.audioUrl)

// The card reads its colours from its own cover once loaded; the featured one
// fetches them at once, for its play button.
const { style: theme, learn } = useGameTheme(() => test.value.coverImageId ?? null, { fetch: props.featured })

function onOpen(e) {
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return
  e.preventDefault()
  emit('view', props.item)
}
function onPlay() {
  if (!hasAudio.value) return
  props.isPlaying ? emit('togglePause') : emit('play', props.item)
}
</script>

<template>
  <article v-if="featured" class="hero" :style="theme">
    <a class="hero__cover corners" :href="href" :aria-label="label" @click="onOpen">
      <img v-if="test.coverImageId" :src="igdbUrl(test.coverImageId, 't_cover_big_2x')" alt="" />
      <span v-else class="hero__nocover cond">{{ name }}</span>
    </a>
    <div class="hero__text">
      <div class="lab hero__kicker">Dernier test · {{ show }} · {{ date }}</div>
      <h2 class="cond hero__name">{{ name }}</h2>
      <p class="hero__ep">{{ ep.title }}</p>
      <span v-if="verdict" class="hero__verdict">{{ verdict }}</span>
      <button type="button" class="btn-play hero__play" :disabled="!hasAudio" @click="onPlay">
        <Pause v-if="isPlaying && !isPaused" :size="14" fill="currentColor" :stroke-width="0" />
        <Play v-else :size="14" fill="currentColor" :stroke-width="0" />
        {{ isPlaying && !isPaused ? 'Pause' : 'Écouter le test' }}
      </button>
    </div>
  </article>

  <a v-else class="card" :href="href" :style="theme" :aria-label="label" @click="onOpen">
    <span class="card__cover corners">
      <img v-if="test.coverImageId" :src="igdbUrl(test.coverImageId, 't_cover_big')" alt="" loading="lazy" decoding="async" crossorigin="anonymous" @load="learn($event.target)" />
      <span v-else class="card__nocover cond">{{ name }}</span>
      <span v-if="verdict" class="card__verdict">{{ verdict }}</span>
      <span v-if="isPlaying" class="card__onair onair" aria-hidden="true"></span>
    </span>
    <span class="card__show">{{ show }}</span>
    <span class="card__date mono">{{ date }}</span>
  </a>
</template>

<style scoped>
/* ─── A card ─────────────────────────────────────────────────────────── */
.card { display: flex; flex-direction: column; gap: 6px; min-width: 0; color: var(--c-fg); text-decoration: none; }
.card__cover {
  --corner: 14px;
  display: block;
  aspect-ratio: 3 / 4;
  background: var(--c-surface);
  box-shadow: 0 0 0 1px var(--c-line), 0 12px 26px rgba(0, 0, 0, 0.5);
  transition: box-shadow var(--dur-med) var(--ease-out-soft);
}
.card__cover::before, .card__cover::after { opacity: 0; transition: opacity var(--dur-med); }
.card:hover .card__cover, .card:focus-visible .card__cover { box-shadow: 0 0 0 1px var(--c-accent), 0 0 36px var(--game-glow), 0 12px 26px rgba(0, 0, 0, 0.5); }
.card:hover .card__cover::before, .card:hover .card__cover::after,
.card:focus-visible .card__cover::before, .card:focus-visible .card__cover::after { opacity: 1; }
.card:focus-visible { outline: none; }
.card__cover img { width: 100%; height: 100%; object-fit: cover; display: block; }
.card__nocover { display: flex; align-items: flex-end; height: 100%; padding: 10px; box-sizing: border-box; font-size: 17px; color: var(--c-fg-2); }
.card__verdict {
  position: absolute;
  left: 0;
  bottom: 0;
  padding: 5px 9px;
  background: rgba(9, 9, 12, 0.88);
  box-shadow: inset 0 -2px 0 var(--c-accent);
  font-family: var(--font-display);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.card__onair { position: absolute; top: 10px; right: 10px; }
.card__show { font-family: var(--font-display); font-weight: 600; font-size: 14px; line-height: 1.2; margin-top: 4px; }
.card__date { color: var(--c-fg-2); font-size: 12px; }

/* ─── The newest test ────────────────────────────────────────────────── */
.hero {
  position: relative;
  display: grid;
  grid-template-columns: 150px minmax(0, 1fr);
  gap: 16px;
  align-items: end;
  padding: 8px 0 0;
}
.hero__cover {
  --corner: 20px;
  --corner-out: 9px;
  position: relative;
  z-index: 1;
  display: block;
  aspect-ratio: 3 / 4;
  background: var(--c-surface);
  box-shadow: var(--shadow-cover);
}
.hero__cover img { width: 100%; height: 100%; object-fit: cover; display: block; }
.hero__nocover { display: flex; align-items: flex-end; height: 100%; padding: 12px; box-sizing: border-box; font-size: 20px; }
.hero__text { position: relative; z-index: 1; display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.hero__kicker { color: var(--c-accent); }
.hero__name { margin: 0; font-size: 26px; overflow-wrap: anywhere; }
.hero__ep { margin: 0; color: var(--c-fg-2); font-size: var(--text-sm); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.hero__verdict {
  align-self: flex-start;
  padding: 5px 10px;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.22);
  font-family: var(--font-display);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.hero__play { align-self: flex-start; margin-top: 6px; }
@media (min-width: 768px) {
  .hero { grid-template-columns: 260px minmax(0, 1fr); gap: 40px; padding-top: 24px; }
  .hero__name { font-size: var(--text-hero); }
  .hero__ep { font-size: var(--text-md); }
}
</style>
