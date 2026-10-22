<script setup>
// The lab, under an episode's chapters (dev only, admin): every game the pipeline
// sees in the episode — attached or only read — with what decided it, and the
// curator's judgment of what it should be. Renders nothing where the lab isn't
// (prod answers 404).
import { ref, computed, onMounted } from 'vue'
import { Play } from 'lucide-vue-next'
import { fetchLabEpisode, setLabJudgment } from '../lib/games.js'
import { formatTime } from '../lib/utils.js'

const props = defineProps({ episodeSlug: { type: String, required: true } })
const emit  = defineEmits(['play'])

const view  = ref(null)
const busy  = ref(null)
const error = ref(null)

const VERDICTS = [
  { id: 'consacré',       label: 'Consacré' },
  { id: 'évoqué',         label: 'Évoqué' },
  { id: 'absent',         label: 'Absent' },
  { id: 'mauvaise-fiche', label: 'Mauvaise fiche' },
]
const KINDS = { review: 'critique', impressions: 'impressions', ranking: 'palmarès',
                news: 'actualité', recommendation: 'conseil', mention: 'mention' }
const SOURCES = { titre: 'titre', description: 'description', lecture: 'lecture' }

onMounted(async () => {
  try { view.value = await fetchLabEpisode(props.episodeSlug) } catch { view.value = null }
})

const judged = computed(() => view.value?.games.filter(g => g.judgment).length ?? 0)

async function judge(row, verdict) {
  busy.value = row.game
  error.value = null
  try {
    view.value = await setLabJudgment(view.value.episode, row.game,
                                      row.judgment === verdict ? null : verdict, row.igdb?.slug)
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = null
  }
}
</script>

<template>
  <div v-if="view" class="lab panel p-5">
    <div class="lab__head">
      <span class="lab__title">Labo</span>
      <span class="lab__count">{{ judged }}/{{ view.games.length }} jugés</span>
      <span v-if="!view.read" class="chip">pas encore lu</span>
    </div>
    <p v-if="!view.games.length" class="text-sm text-white/55">Aucun jeu vu dans cet épisode.</p>
    <p v-if="error" class="text-sm text-error mb-2">{{ error }}</p>
    <div v-for="row in view.games" :key="row.game" class="lab__row" :class="{ 'lab__row--loose': !row.attached }">
      <button v-if="row.start != null" class="lab__play" :aria-label="`Écouter ${row.game}`"
              @click="emit('play', row.start)">
        <Play :size="12" fill="currentColor" :stroke-width="0" />
      </button>
      <span v-else class="lab__play lab__play--none" />
      <div class="lab__what">
        <div class="lab__name">
          {{ row.game }}
          <span v-if="row.igdb && row.igdb.name !== row.game" class="lab__igdb">
            → {{ row.igdb.name }}<template v-if="row.igdb.released"> ({{ String(row.igdb.released).slice(0, 4) }})</template>
          </span>
          <span v-else-if="row.attached && !row.igdb" class="lab__igdb lab__igdb--none">→ non résolu</span>
        </div>
        <div class="lab__facts">
          <span>{{ row.attached ? 'rattaché' : 'non rattaché' }}</span>
          <span>{{ SOURCES[row.source] }}</span>
          <span v-if="row.kind">{{ KINDS[row.kind] ?? row.kind }}</span>
          <span v-if="row.minutes != null">{{ row.minutes }} min</span>
          <span v-if="row.start != null">à {{ formatTime(row.start) }}</span>
          <span v-if="row.verdict">avis {{ row.verdict }}</span>
        </div>
      </div>
      <div class="lab__verdicts" role="group" :aria-label="`Jugement pour ${row.game}`">
        <button v-for="v in VERDICTS" :key="v.id" class="lab__verdict"
                :class="{ 'lab__verdict--on': row.judgment === v.id }"
                :aria-pressed="row.judgment === v.id" :disabled="busy === row.game"
                @click="judge(row, v.id)">{{ v.label }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.lab { margin-top: 1rem; border: 1px dashed rgba(var(--rgb-line), 0.25); }
.lab__head { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.75rem; }
.lab__title { font-size: 0.7rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase;
              color: rgba(var(--rgb-line), 0.55); }
.lab__count { font-family: var(--font-mono); font-size: 0.68rem; color: rgba(var(--rgb-line), 0.45); }
.lab__row { display: flex; align-items: center; gap: 0.6rem; padding: 0.5rem 0;
            border-top: 1px solid var(--border-subtle); }
.lab__row--loose .lab__name { color: rgba(var(--rgb-line), 0.6); }
.lab__play { width: 26px; height: 26px; flex-shrink: 0; border-radius: 999px; display: grid; place-items: center;
             background: rgba(var(--rgb-line), 0.08); color: rgba(var(--rgb-line), 0.8); }
.lab__play--none { background: none; }
.lab__what { flex: 1; min-width: 0; }
.lab__name { font-size: 0.85rem; font-weight: 600; color: rgba(var(--rgb-line), 0.92); }
.lab__igdb { font-weight: 400; color: rgba(var(--rgb-line), 0.55); }
.lab__igdb--none { color: var(--color-warning); }
.lab__facts { display: flex; flex-wrap: wrap; gap: 0 0.6rem; font-family: var(--font-mono);
              font-size: 0.64rem; color: rgba(var(--rgb-line), 0.45); }
.lab__verdicts { display: flex; flex-wrap: wrap; gap: 0.25rem; justify-content: flex-end; max-width: 50%; }
.lab__verdict { font-size: 0.66rem; padding: 0.2rem 0.5rem; border-radius: 999px;
                border: 1px solid rgba(var(--rgb-line), 0.18); color: rgba(var(--rgb-line), 0.7); }
.lab__verdict--on { background: var(--game-accent, #e94560); border-color: transparent; color: #fff; }
.lab__verdict:disabled { opacity: 0.5; }
</style>
