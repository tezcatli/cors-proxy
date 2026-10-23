<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { PROGRESS_MIN_PCT } from '../lib/utils.js'
import { igdbUrl } from '../lib/igdbCdn.js'
import { verdictMeta } from '../lib/verdicts.js'
import { useProgress } from '../composables/useProgress.js'
import { captureSource } from '../lib/flipTransition.js'

// A catalog tile: the bare cover (nothing laid over the art), then the name and
// one verdict glyph per test, newest first — no average across shows.
const MAX_MARKS = 4

const props  = defineProps({ game: Object })
const router = useRouter()
const imgEl  = ref(null)

const { gameProgress } = useProgress()

const coverImageId = computed(() => props.game?.igdb?.coverImageId ?? null)
const progress     = computed(() => gameProgress(props.game.slug))
const href         = computed(() => '/game/' + encodeURIComponent(props.game.slug))

const verdicts = computed(() => props.game.verdicts ?? [])
const marks    = computed(() => verdicts.value.slice(0, MAX_MARKS).map(v => verdictMeta(v)))
const more     = computed(() => Math.max(0, verdicts.value.length - MAX_MARKS))
const marksLabel = computed(() => verdicts.value.map(v => verdictMeta(v).label).join(', '))

function open(e) {
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return
  e.preventDefault()
  captureSource(`cover:${props.game.slug}`, imgEl.value)
  router.push(href.value)
}
</script>

<template>
  <a class="tile" :href="href" @click="open">
    <div class="tile__cover">
      <img
        v-if="coverImageId"
        ref="imgEl"
        :src="igdbUrl(coverImageId, 't_cover_big')"
        :srcset="`${igdbUrl(coverImageId,'t_cover_small')} 90w, ${igdbUrl(coverImageId,'t_cover_big')} 264w, ${igdbUrl(coverImageId,'t_cover_big_2x')} 528w`"
        sizes="(min-width:900px) 200px, 33vw"
        alt=""
        loading="lazy"
        decoding="async"
      />
      <span v-else ref="imgEl" class="tile__nocover cond">{{ game.name }}</span>
      <span v-if="progress.pct > PROGRESS_MIN_PCT" class="tile__progress" :class="{ 'is-done': progress.done }">
        <span :style="{ width: progress.pct + '%' }"></span>
      </span>
    </div>
    <span class="tile__name cond clamp-2">{{ game.name }}</span>
    <span class="tile__marks mono" :aria-label="`Verdicts : ${marksLabel}`">
      <span v-for="(m, i) in marks" :key="i" :class="{ 'is-none': m.glyph === '○' }" aria-hidden="true">{{ m.glyph }}</span>
      <span v-if="more" aria-hidden="true">+{{ more }}</span>
    </span>
  </a>
</template>

<style scoped>
.tile {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
  text-decoration: none;
  color: var(--c-fg);
}
.tile__cover {
  position: relative;
  aspect-ratio: 3 / 4;
  background: var(--c-surface);
  overflow: hidden;
}
.tile__cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  transition: transform var(--dur-med) var(--ease-out-soft);
}
.tile:hover .tile__cover img { transform: scale(1.03); }
.tile:focus-visible { outline-offset: 4px; }
.tile__nocover {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: flex-end;
  padding: 10px;
  font-size: 20px;
  color: var(--c-fg-2);
  box-shadow: inset 0 0 0 1px var(--c-line);
}
.tile__progress {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 4px;
  background: rgba(11, 11, 11, 0.75);
}
.tile__progress span { display: block; height: 100%; background: var(--c-accent); }
.tile__progress.is-done span { background: var(--c-fg); }
.tile__name { font-size: 17px; line-height: 1.05; }
.tile__marks { display: flex; gap: 6px; font-size: var(--text-xs); color: var(--c-fg); min-height: 16px; }
.tile__marks .is-none { color: var(--c-fg-3); }
@media (min-width: 768px) { .tile__name { font-size: 19px; } }
</style>
