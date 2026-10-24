<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { PROGRESS_MIN_PCT } from '../lib/utils.js'
import { igdbUrl } from '../lib/igdbCdn.js'
import { useProgress } from '../composables/useProgress.js'
import { useGameTheme } from '../composables/useGameTheme.js'
import { captureSource } from '../lib/flipTransition.js'

// A catalog tile: the cover alone, framed in the game's colour — the page is for
// browsing; the name is on the cover (and in the accessible name), the verdicts
// on the game's page (DECISIONS.md, « Interface »).
const props  = defineProps({ game: Object })
const router = useRouter()
const imgEl  = ref(null)
const { gameProgress } = useProgress()

const coverImageId = computed(() => props.game?.igdb?.coverImageId ?? null)
const progress     = computed(() => gameProgress(props.game.slug))
const href         = computed(() => '/game/' + encodeURIComponent(props.game.slug))
const { style: theme } = useGameTheme(coverImageId)

function open(e) {
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return
  e.preventDefault()
  captureSource(`cover:${props.game.slug}`, imgEl.value)
  router.push(href.value)
}
</script>

<template>
  <a class="tile corners" :href="href" :style="theme" :aria-label="game.name" @click="open">
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
  </a>
</template>

<style scoped>
.tile {
  --corner: 14px;
  display: block;
  aspect-ratio: 3 / 4;
  min-width: 0;
  background: var(--c-surface);
  box-shadow: 0 0 0 1px var(--c-line), 0 14px 30px rgba(0, 0, 0, 0.5);
  color: var(--c-fg);
  text-decoration: none;
  transition: box-shadow var(--dur-med) var(--ease-out-soft), transform var(--dur-med) var(--ease-out-soft);
}
.tile::before, .tile::after { opacity: 0; transition: opacity var(--dur-med); }
.tile:hover, .tile:focus-visible {
  box-shadow: 0 0 0 1px var(--c-accent), 0 0 40px var(--game-glow), 0 18px 36px rgba(0, 0, 0, 0.6);
  transform: translateY(-2px);
}
.tile:hover::before, .tile:hover::after, .tile:focus-visible::before, .tile:focus-visible::after { opacity: 1; }
.tile:focus-visible { outline: none; }
.tile img { width: 100%; height: 100%; object-fit: cover; display: block; }
.tile__nocover {
  display: flex;
  align-items: flex-end;
  height: 100%;
  padding: 10px;
  box-sizing: border-box;
  font-size: 18px;
  color: var(--c-fg-2);
}
.tile__progress {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 4px;
  background: rgba(9, 9, 12, 0.75);
}
.tile__progress span { display: block; height: 100%; background: var(--c-accent); }
.tile__progress.is-done span { background: var(--c-fg); }
</style>
