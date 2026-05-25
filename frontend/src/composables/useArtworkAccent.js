import { ref, watch } from 'vue'
import { Vibrant } from 'node-vibrant/browser'
import { igdbUrl } from '../lib/igdbCdn.js'

const cache = new Map()

const DEFAULT_PALETTE = {
  accent:       'rgb(233, 69, 96)',
  accentText:   '#ffffff',
  backdropTint: 'rgb(15, 15, 28)',
  mutedBg:      'rgb(26, 26, 46)',
}

function fromSwatch(s, fallback) {
  if (!s) return fallback
  return s.hex
}
function fgFor(s, fallback) {
  if (!s) return fallback
  return s.bodyTextColor === '#000000' ? '#0a0a14' : '#ffffff'
}

function extract(imageId) {
  if (!imageId) return Promise.resolve(DEFAULT_PALETTE)
  if (cache.has(imageId)) return cache.get(imageId)

  const url = igdbUrl(imageId, 't_cover_small')
  const promise = Vibrant.from(url)
    .quality(5)
    .getPalette()
    .then(p => {
      const accentSwatch  = p.Vibrant   || p.LightVibrant || p.Muted
      const bgSwatch      = p.DarkMuted || p.DarkVibrant  || p.Muted
      return {
        accent:       fromSwatch(accentSwatch, DEFAULT_PALETTE.accent),
        accentText:   fgFor(accentSwatch,      DEFAULT_PALETTE.accentText),
        backdropTint: fromSwatch(bgSwatch,     DEFAULT_PALETTE.backdropTint),
        mutedBg:      fromSwatch(p.Muted,      DEFAULT_PALETTE.mutedBg),
      }
    })
    .catch(() => DEFAULT_PALETTE)

  cache.set(imageId, promise)
  return promise
}

/**
 * Reactive accent palette derived from an IGDB cover image id.
 * Returns { palette, cssVars } — cssVars is a plain object you can bind via :style
 * so consumers can set --game-accent / --game-accent-fg / --game-backdrop scoped
 * to their element without touching the global CSS.
 *
 * Pass `enabledRef` (a ref<boolean>) to gate extraction — useful for catalog tiles
 * that should only run vibrant once they scroll into view. Defaults to always-on.
 */
export function useArtworkAccent(imageIdRef, enabledRef = ref(true)) {
  const palette = ref(DEFAULT_PALETTE)
  const cssVars = ref(toCssVars(DEFAULT_PALETTE))

  function run() {
    const id = imageIdRef.value
    if (!id || !enabledRef.value) {
      palette.value = DEFAULT_PALETTE
      cssVars.value = toCssVars(DEFAULT_PALETTE)
      return
    }
    const cb = () => extract(id).then(p => {
      palette.value = p
      cssVars.value = toCssVars(p)
    })
    if ('requestIdleCallback' in window) window.requestIdleCallback(cb, { timeout: 1500 })
    else setTimeout(cb, 0)
  }

  watch([imageIdRef, enabledRef], run, { immediate: true })
  return { palette, cssVars }
}

function toCssVars(p) {
  return {
    '--game-accent':    p.accent,
    '--game-accent-fg': p.accentText,
    '--game-backdrop':  p.backdropTint,
    '--game-muted-bg':  p.mutedBg,
  }
}
