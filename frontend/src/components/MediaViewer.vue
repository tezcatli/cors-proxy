<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { igdbUrl } from '../lib/igdbCdn.js'
import { ChevronLeft, ChevronRight, X, Play } from 'lucide-vue-next'

// A game's media, one after the other — its cover, its trailer, its screenshots,
// its artworks — passed with a swipe (the finger, a trackpad), the arrows or the
// keyboard. The swipe is the browser's own scrolling, snapped a slide at a time:
// no gesture code. An image loads when it is shown or next to it; the trailer
// plays once asked, and stops when left (its iframe goes).
const props = defineProps({
  items:    { type: Array, required: true },    // [{kind: 'image' | 'video', id}]
  start:    { type: Number, default: 0 },
  autoplay: { type: Boolean, default: false },  // opened from the trailer: play at once
})
const emit = defineEmits(['close'])

const at      = ref(Math.min(Math.max(props.start, 0), props.items.length - 1))
const seen    = ref(new Set([at.value]))
const playing = ref(props.autoplay && props.items[at.value]?.kind === 'video')
const root    = ref(null)
const track   = ref(null)

const near = i => Math.abs(i - at.value) <= 1 || seen.value.has(i)

// Leaving the trailer stops it.
watch(at, i => {
  seen.value = new Set(seen.value).add(i)
  if (props.items[i]?.kind !== 'video') playing.value = false
})

const reduced = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

// While the arrows or the keys glide the track to a slide, the positions it
// passes through are not the current slide: `target` holds them off. Whatever
// ends a scroll — reaching the slide, a finger taking over — the slide in view
// becomes the current one once the track has settled.
let target = null
let settle = null

function go(i) {
  const n = Math.min(Math.max(i, 0), props.items.length - 1)
  if (n === at.value) return
  at.value = n
  target = n
  const el = track.value
  el?.scrollTo?.({ left: n * el.clientWidth, behavior: reduced() ? 'auto' : 'smooth' })
}

function sync() {
  const el = track.value
  if (!el?.clientWidth) return
  const i = Math.round(el.scrollLeft / el.clientWidth)
  if (i !== at.value && i >= 0 && i < props.items.length) at.value = i
}
// A swipe moves the track: the slide most in view is the current one.
function onScroll() {
  clearTimeout(settle)
  settle = setTimeout(() => { target = null; sync() }, 150)
  if (target == null) sync()
}
// The track shows the current slide once it has its width (on opening, and
// when the window changes size).
function place() {
  const el = track.value
  if (!el?.clientWidth) return
  target = null
  el.scrollTo?.({ left: at.value * el.clientWidth, behavior: 'instant' })
  if (!el.scrollTo) el.scrollLeft = at.value * el.clientWidth
}

function onKeydown(e) {
  if (e.key === 'Escape')     { emit('close'); return }
  if (e.key === 'ArrowLeft')  { go(at.value - 1); return }
  if (e.key === 'ArrowRight') { go(at.value + 1); return }
  if (e.key === 'Tab') {                       // the focus stays in the viewer
    const els = [...(root.value?.querySelectorAll('button') ?? [])]
    if (!els.length) return
    e.preventDefault()
    const i = els.indexOf(document.activeElement)
    els[(i + (e.shiftKey ? -1 : 1) + els.length) % els.length].focus()
  }
}

let opener = null
let sizes  = null
onMounted(async () => {
  opener = document.activeElement
  document.addEventListener('keydown', onKeydown)
  await nextTick()
  if (typeof ResizeObserver !== 'undefined') {
    sizes = new ResizeObserver(place)
    sizes.observe(track.value)
  } else place()
  root.value?.querySelector('.viewer__close')?.focus()
})
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  sizes?.disconnect()
  clearTimeout(settle)
  opener?.focus?.()
})

const count = computed(() => `${at.value + 1} / ${props.items.length}`)
</script>

<template>
  <Teleport to="body">
    <div ref="root" class="viewer" role="dialog" aria-modal="true" aria-label="Images et bande-annonce">
      <div ref="track" class="viewer__track" @scroll.passive="onScroll">
        <div
          v-for="(item, i) in items"
          :key="item.kind + item.id"
          class="viewer__slide"
          :aria-hidden="i !== at"
          @click.self="emit('close')"
        >
          <template v-if="item.kind === 'video'">
            <div class="viewer__video">
              <iframe
                v-if="playing && i === at"
                :src="`https://www.youtube-nocookie.com/embed/${item.id}?autoplay=1&rel=0`"
                title="Bande-annonce"
                allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
                allowfullscreen
              />
              <button v-else type="button" class="viewer__poster" aria-label="Lire la bande-annonce" @click="playing = true">
                <img v-if="near(i)" :src="`https://i.ytimg.com/vi/${item.id}/hqdefault.jpg`" alt="" />
                <span class="viewer__play"><Play :size="28" fill="currentColor" :stroke-width="0" /></span>
              </button>
            </div>
          </template>
          <img
            v-else-if="near(i)"
            class="viewer__img"
            :src="igdbUrl(item.id, 't_1080p')"
            :srcset="`${igdbUrl(item.id, 't_screenshot_huge')} 1280w, ${igdbUrl(item.id, 't_1080p')} 1920w`"
            sizes="92vw"
            alt=""
            draggable="false"
          />
        </div>
      </div>

      <button type="button" class="icon-action viewer__close" aria-label="Fermer" @click="emit('close')"><X :size="20" :stroke-width="2" /></button>
      <button v-if="at > 0" type="button" class="icon-action viewer__prev" aria-label="Précédente" @click="go(at - 1)"><ChevronLeft :size="24" :stroke-width="2" /></button>
      <button v-if="at < items.length - 1" type="button" class="icon-action viewer__next" aria-label="Suivante" @click="go(at + 1)"><ChevronRight :size="24" :stroke-width="2" /></button>
      <div v-if="items.length > 1" class="lab viewer__count" aria-live="polite">{{ count }}</div>
    </div>
  </Teleport>
</template>

<style scoped>
.viewer { position: fixed; inset: 0; z-index: var(--z-lightbox); background: rgba(0, 0, 0, 0.94); }
.viewer__track {
  display: flex;
  height: 100%;
  overflow-x: auto;
  overflow-y: hidden;
  scroll-snap-type: x mandatory;
  overscroll-behavior: contain;
  scrollbar-width: none;
}
.viewer__track::-webkit-scrollbar { display: none; }
.viewer__slide {
  flex: 0 0 100%;
  height: 100%;
  scroll-snap-align: center;
  scroll-snap-stop: always;
  display: flex;
  align-items: center;
  justify-content: center;
}
.viewer__img { max-width: 92vw; max-height: 84vh; object-fit: contain; user-select: none; }
.viewer__video { width: min(92vw, 1100px); aspect-ratio: 16 / 9; }
.viewer__video iframe { width: 100%; height: 100%; border: 0; display: block; }
.viewer__poster { position: relative; width: 100%; height: 100%; padding: 0; border: 0; background: #000; cursor: pointer; }
.viewer__poster img { width: 100%; height: 100%; object-fit: cover; display: block; }
.viewer__play {
  position: absolute;
  inset: 0;
  margin: auto;
  width: 72px;
  height: 72px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--c-accent);
  color: var(--c-accent-fg);
}
.viewer__close { position: absolute; top: calc(8px + env(safe-area-inset-top, 0px)); right: 8px; color: #fff; }
.viewer__prev  { position: absolute; left: 8px; top: 50%; transform: translateY(-50%); color: #fff; }
.viewer__next  { position: absolute; right: 8px; top: 50%; transform: translateY(-50%); color: #fff; }
.viewer__count { position: absolute; left: 0; right: 0; bottom: calc(16px + env(safe-area-inset-bottom, 0px)); text-align: center; color: #fff; pointer-events: none; }
</style>
