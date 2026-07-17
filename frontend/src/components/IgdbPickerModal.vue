<script setup>
// Admin tool: pin the IGDB game a podcast name resolves to. Unlike the resolver's
// own search this shows IGDB's raw matches (ports, remakes, versions) with their
// release year, because telling those apart is the whole point of correcting.
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { searchIgdb, setCorrection, deleteCorrection } from '../lib/games.js'
import { igdbUrl } from '../lib/igdbCdn.js'
import { podcastMeta } from '../lib/podcasts.js'
import placeholderCover from '../assets/placeholder-cover.svg'
import { X, Search, Loader2, Check, Undo2 } from 'lucide-vue-next'

const props = defineProps({
  // { name, nameSlug, nameSlugs?, podcasts: string[], igdbName, igdbSlug, displayName }
  game:         { type: Object, required: true },
  hasCorrection: Boolean,
  // False in prod, where corrections.json is in the read-only image layer.
  writable:     { type: Boolean, default: true },
})
const emit = defineEmits(['close', 'saved'])

const query    = ref(props.game.name || '')
const results  = ref([])
const searching = ref(false)
const saving   = ref(false)
const error    = ref(null)
// Empty = show whatever the resolution produced. Renaming and pinning are
// independent, so this can be saved on its own — and doing so costs no IGDB call.
const displayName = ref(props.game.displayName || '')
const nameDirty = computed(() => displayName.value !== (props.game.displayName || ''))
// '' = every podcast. Only offered when the game spans both shows, since that's
// the only case where the two can legitimately need different IGDB games.
const scope    = ref('')

const scopeOptions = computed(() => {
  const ids = props.game.podcasts ?? []
  if (ids.length < 2) return []
  return [{ id: '', name: 'Les deux podcasts' },
          ...ids.map(id => ({ id, name: podcastMeta(id)?.name || id }))]
})

// A correction is keyed by ONE podcast name. When several spellings merged into
// this entry, pinning `nameSlug` would move only that spelling's episodes and
// leave the rest behind — say so rather than let it look like it all worked.
const otherNames = computed(() =>
  (props.game.nameSlugs ?? []).filter(ns => ns !== props.game.nameSlug))

let _seq = 0
async function runSearch() {
  const q = query.value.trim()
  if (!q) { results.value = []; return }
  const seq = ++_seq
  searching.value = true
  error.value = null
  try {
    const found = await searchIgdb(q)
    if (seq === _seq) results.value = found          // ignore a stale response
  } catch (e) {
    if (seq === _seq) error.value = e.message
  } finally {
    if (seq === _seq) searching.value = false
  }
}

let _debounce
watch(query, () => {
  clearTimeout(_debounce)
  _debounce = setTimeout(runSearch, 350)
})

async function save({ igdbId } = {}) {
  saving.value = true
  error.value  = null
  try {
    const detail = await setCorrection({
      nameSlug:  props.game.nameSlug,
      podcastId: scope.value,
      igdbId,
      // Send it only when it changed, so pinning a game doesn't rewrite the name
      // and renaming doesn't have to restate the pin.
      ...(nameDirty.value ? { displayName: displayName.value.trim() } : {}),
    })
    emit('saved', detail)
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}

const pick = (result) => save({ igdbId: result.id })

async function clearCorrection() {
  saving.value = true
  error.value  = null
  try {
    const detail = await deleteCorrection({
      nameSlug:  props.game.nameSlug,
      podcastId: scope.value,
    })
    emit('saved', detail)
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}

function onKeydown(e) { if (e.key === 'Escape' && !saving.value) emit('close') }
onMounted(() => {
  document.addEventListener('keydown', onKeydown)
  runSearch()
})
onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
  clearTimeout(_debounce)
})
</script>

<template>
  <div class="fixed inset-0 z-[var(--z-modal)] flex items-center justify-center p-4">
    <Transition name="modal-pop" appear>
      <div class="absolute inset-0 bg-black/60 backdrop-blur-sm" @click="emit('close')" />
    </Transition>
    <Transition name="modal-pop" appear>
      <div class="panel relative p-5 w-full max-w-lg shadow-e4 flex flex-col max-h-[85vh]">
        <div class="flex items-start justify-between gap-3 mb-3">
          <div class="min-w-0">
            <h2 class="text-base font-extrabold tracking-[-0.01em] truncate">
              Corriger « {{ game.name }} »
            </h2>
            <p v-if="game.igdbName" class="text-xs text-white/50 truncate mt-0.5">
              Actuellement : {{ game.igdbName }}
            </p>
          </div>
          <button
            class="btn btn-circle btn-ghost !size-8 !min-h-8 hover:bg-white/10 flex-shrink-0"
            aria-label="Fermer"
            @click="emit('close')"
          ><X :size="16" :stroke-width="2.25" /></button>
        </div>

        <p v-if="!writable" class="picker-warn mb-3">
          Lecture seule : corrections.json est dans l’image de production. Corrigez
          en dev (le dépôt y est monté), puis committez le fichier.
        </p>

        <p v-if="otherNames.length" class="picker-warn mb-3">
          Cette fiche regroupe plusieurs orthographes
          ({{ [game.nameSlug, ...otherNames].join(', ') }}). La correction ne
          s’applique qu’à « {{ game.nameSlug }} » ; corrigez les autres depuis
          leur propre fiche.
        </p>

        <!-- Scope: only meaningful for a game both shows cover -->
        <div v-if="scopeOptions.length" class="flex flex-wrap gap-1.5 mb-3">
          <button
            v-for="opt in scopeOptions"
            :key="opt.id"
            class="chip"
            :class="{ 'chip-accent': scope === opt.id }"
            @click="scope = opt.id"
          >{{ opt.name }}</button>
        </div>

        <!-- Renaming is independent of the pin: it changes the title shown in the
             catalogue, not which IGDB game this is. -->
        <label class="picker-field">
          <span class="picker-field__label">Nom affiché</span>
          <input
            v-model="displayName"
            class="app-input picker-field__input"
            type="text"
            :disabled="!writable"
            :placeholder="game.igdbName || game.name"
          />
        </label>
        <div v-if="nameDirty" class="picker-save">
          <button class="btn btn-sm btn-outline gap-2 border-white/15 hover:bg-white/10"
                  :disabled="saving" @click="save()">
            <Check :size="14" :stroke-width="2.5" />
            {{ displayName.trim() ? 'Enregistrer le nom' : 'Utiliser le nom IGDB' }}
          </button>
          <span class="picker-save__hint">sans re-résoudre</span>
        </div>

        <div class="picker-sep"><span>ou choisir une autre fiche IGDB</span></div>

        <label class="search-wrap !flex mb-3">
          <Search :size="15" class="search-wrap__icon" />
          <input
            v-model="query"
            class="search-input"
            type="search"
            autofocus
            placeholder="Rechercher sur IGDB…"
            @keydown.enter="runSearch"
          />
        </label>

        <p v-if="error" class="text-xs text-error mb-2">{{ error }}</p>

        <div class="flex-1 overflow-y-auto -mx-1 px-1">
          <div v-if="searching && !results.length" class="flex flex-col gap-2">
            <div v-for="i in 4" :key="i" class="skeleton-shimmer h-[54px] rounded-xl" aria-hidden="true" />
          </div>
          <p v-else-if="!results.length" class="text-sm text-white/45 py-8 text-center">
            Aucun résultat.
          </p>
          <div v-else class="flex flex-col gap-1.5">
            <button
              v-for="r in results"
              :key="r.id"
              class="igdb-result"
              :class="{ 'is-current': r.slug === game.igdbSlug }"
              :disabled="saving || !writable"
              @click="pick(r)"
            >
              <img
                class="igdb-result__cover"
                :src="r.coverImageId ? igdbUrl(r.coverImageId, 't_cover_small') : placeholderCover"
                alt=""
                loading="lazy"
              />
              <span class="min-w-0 flex-1 text-left">
                <span class="block text-sm font-semibold truncate">{{ r.name }}</span>
                <span class="block text-[0.7rem] text-white/45 truncate">
                  {{ r.released || 'année inconnue' }} · {{ r.slug }}
                </span>
              </span>
              <Check v-if="r.slug === game.igdbSlug" :size="15" :stroke-width="2.5" class="text-game-accent flex-shrink-0" />
            </button>
          </div>
        </div>

        <div v-if="hasCorrection && writable" class="pt-3 mt-1 border-t border-white/8">
          <button class="btn btn-ghost btn-sm gap-2 text-white/60 hover:text-white" :disabled="saving" @click="clearCorrection">
            <Undo2 :size="14" :stroke-width="2.25" />
            Retirer la correction
          </button>
        </div>

        <div v-if="saving" class="absolute inset-0 rounded-[var(--radius-xl)] bg-black/45 grid place-items-center">
          <Loader2 :size="26" class="animate-spin text-game-accent" />
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.igdb-result {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 6px;
  border-radius: var(--radius-lg, 0.75rem);
  border: 1px solid transparent;
  background: rgba(255, 255, 255, 0.04);
  transition: background 0.15s, border-color 0.15s;
}
.igdb-result:hover:not(:disabled) { background: rgba(255, 255, 255, 0.09); }
.igdb-result.is-current { border-color: var(--border-accent); }
.igdb-result:disabled { opacity: 0.5; }
.igdb-result__cover {
  width: 32px;
  height: 42px;
  object-fit: cover;
  border-radius: 4px;
  flex-shrink: 0;
  background: rgba(255, 255, 255, 0.06);
}
.picker-warn {
  padding: 7px 10px;
  border-radius: var(--radius-lg);
  font-size: 0.72rem;
  line-height: 1.4;
  background: rgba(var(--rgb-mid), 0.14);
  border: 1px solid rgba(var(--rgb-mid), 0.35);
  color: var(--col-mid-text);
}

.picker-field { display: block; }
.picker-field__label {
  display: block;
  font-size: 0.6rem;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: rgba(var(--rgb-line), 0.45);
  margin-bottom: 4px;
}
.picker-field__input { height: 2.25rem; }
.picker-save {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}
.picker-save__hint { font-size: 0.68rem; color: rgba(var(--rgb-line), 0.35); }

/* Separates the two independent decisions: what it's called, and which game it is. */
.picker-sep {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 14px 0 10px;
  font-size: 0.6rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: rgba(var(--rgb-line), 0.3);
}
.picker-sep::before,
.picker-sep::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border-subtle);
}
</style>
