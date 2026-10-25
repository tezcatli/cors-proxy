import { ref, computed, watch, unref } from 'vue'
import { igdbUrl } from '../lib/igdbCdn.js'

// A game's light, read from its cover (DECISIONS.md, « Interface »: one page,
// one light, the page itself black). The cover's most vivid hue becomes the
// accent, lifted until it reads at 4.5:1 on the black ground; it and a second
// hue of the cover, far enough from the first, colour the halo (--game-glow,
// --game-glow-2). `style` overrides those tokens on the subtree it is bound to;
// the ground and the panels stay neutral. IGDB's CDN allows reading the pixels
// (Access-Control-Allow-Origin: *); when it can't be read the tokens stay
// neutral.
//
// A palette is read once per cover and kept (memory, then localStorage), so a
// game seen before opens in its colours at once. A tile that shows the cover
// anyway reads it from its own <img> (`learn`) rather than fetch it again.

const SAMPLE_W = 36
const SAMPLE_H = 48
const STORE_KEY = 'ludo.palettes.v2'  // v2: the second hue (glow2)
const STORE_MAX = 800                // ~200 bytes each
const cache = new Map()              // cover id → palette (null: unreadable), or the promise of one
let stored = null                    // localStorage's palettes, read on first use

function storedPalettes() {
  if (stored) return stored
  try { stored = JSON.parse(localStorage.getItem(STORE_KEY)) ?? {} } catch { stored = {} }
  return stored
}

/** The palette already known for a cover: a palette, null (unreadable), or undefined (not read yet). */
function known(id) {
  if (cache.has(id)) {
    const v = cache.get(id)
    return v instanceof Promise ? undefined : v
  }
  const s = storedPalettes()
  if (id in s) { cache.set(id, s[id]); return s[id] }
  return undefined
}

function remember(id, palette) {
  cache.set(id, palette)
  if (!palette) return
  const s = storedPalettes()
  delete s[id]
  s[id] = palette                    // newest last: the oldest go first
  const ids = Object.keys(s)
  for (const old of ids.slice(0, Math.max(0, ids.length - STORE_MAX))) delete s[old]
  try { localStorage.setItem(STORE_KEY, JSON.stringify(s)) } catch { /* full or blocked: memory only */ }
}

/** The palette of RGBA pixels (an ImageData's data): {accent, on, glow, glow2}. */
export function paletteOf(pixels) {
  const bins = Array.from({ length: 24 }, () => ({ n: 0, w: 0, r: 0, g: 0, b: 0 }))
  for (let i = 0; i < pixels.length; i += 4) {
    const r = pixels[i], g = pixels[i + 1], b = pixels[i + 2]
    const [h, s, l] = hsl(r, g, b)
    if (s < 0.28 || l < 0.18 || l > 0.85) continue   // greys, shadows, highlights
    const bin = bins[Math.floor(h * 24) % 24]
    bin.n++
    bin.w += s * (1 - Math.abs(l - 0.5))              // vivid, mid-light pixels weigh most
    bin.r += r; bin.g += g; bin.b += b
  }
  const vivid = bin => (bin && bin.n >= 8 ? lift(hsl(bin.r / bin.n, bin.g / bin.n, bin.b / bin.n)) : null)
  const at = bins.indexOf(bins.reduce((a, b) => (b.w > a.w ? b : a)))
  const accent = vivid(bins[at]) ?? [0, 0, 0.9]       // no hue to speak of: near-white
  // The halo's second colour: the weightiest hue at least 45° from the first
  // (and worth a tenth of it), else the first again.
  const far = bins
    .filter((b, i) => Math.min(Math.abs(i - at), 24 - Math.abs(i - at)) >= 3 && b.w >= bins[at].w / 10)
    .reduce((a, b) => (!a || b.w > a.w ? b : a), null)
  return paletteAround(accent, vivid(far) ?? accent)
}

/**
 * The palette around a colour given by hand (a podcast's, `lib/podcasts.js`,
 * whose image can't be read: its host sends no CORS header); null for none.
 */
export function paletteFromAccent(color) {
  if (!color) return null
  const [r, g, b] = [1, 3, 5].map(i => parseInt(color.slice(i, i + 2), 16))
  const accent = lift(hsl(r, g, b))
  return paletteAround(accent, accent)
}

// A hue made vivid enough to light a page.
function lift([h, s, l]) { return [h, Math.max(s, 0.55), Math.min(Math.max(l, 0.55), 0.7)] }

const GROUND = [9, 9, 12]   // --c-bg: the page stays black

function paletteAround(accent, second) {
  const a = [...accent]
  while (contrast(rgb(a), GROUND) < 4.5 && a[2] < 0.95) a[2] += 0.03
  const ar = rgb(a)
  return {
    accent: hex(ar),
    on:     contrast(ar, GROUND) >= contrast(ar, [255, 255, 255]) ? '#09090c' : '#ffffff',
    glow:   `rgba(${ar.join(',')}, 0.5)`,
    glow2:  `rgba(${rgb(second).join(',')}, 0.4)`,
  }
}

/** The CSS variables a palette sets on a subtree: its light only, never the ground; {} for none. */
export function themeStyle(p) {
  if (!p) return {}
  return {
    '--c-accent':    p.accent,
    '--c-accent-fg': p.on,
    '--game-glow':   p.glow,
    '--game-glow-2': p.glow2 ?? p.glow,
    '--c-mark':      p.accent,
  }
}

/** The palette of a loaded image (a cover), or null when its pixels can't be read. */
export function paletteFromImage(img) {
  try {
    const canvas = document.createElement('canvas')
    canvas.width = SAMPLE_W
    canvas.height = SAMPLE_H
    const ctx = canvas.getContext('2d', { willReadFrequently: true })
    if (!ctx) return null
    ctx.drawImage(img, 0, 0, SAMPLE_W, SAMPLE_H)
    return paletteOf(ctx.getImageData(0, 0, SAMPLE_W, SAMPLE_H).data)
  } catch {
    return null   // a tainted canvas: stay neutral
  }
}

function read(id) {
  const k = known(id)
  if (k !== undefined) return Promise.resolve(k)
  if (cache.has(id)) return cache.get(id)
  const pending = new Promise(resolve => {
    if (typeof document === 'undefined') return resolve(null)
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => resolve(paletteFromImage(img))
    img.onerror = () => resolve(null)
    img.src = igdbUrl(id, 't_cover_small')
  }).then(p => { remember(id, p); return p })
  cache.set(id, pending)
  return pending
}

/**
 * The theme of the game whose cover id is `coverId` (a ref, getter or value).
 * `fetch: false` for a component that shows the cover itself: it calls
 * `learn(img)` once its <img> has loaded instead of fetching it twice.
 */
export function useGameTheme(coverId, { fetch = true } = {}) {
  const current = () => (typeof coverId === 'function' ? coverId() : unref(coverId))
  const palette = ref(null)
  watch(current, async id => {
    palette.value = id ? (known(id) ?? null) : null
    if (!id || !fetch || known(id) !== undefined) return
    const p = await read(id)
    if (current() === id) palette.value = p
  }, { immediate: true })

  function learn(img) {
    const id = current()
    if (!id || known(id) !== undefined) return
    remember(id, paletteFromImage(img))
    palette.value = known(id) ?? null
  }

  return { palette, style: computed(() => themeStyle(palette.value)), learn }
}

function hsl(r, g, b) {
  r /= 255; g /= 255; b /= 255
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2
  let h = 0, s = 0
  if (mx !== mn) {
    const d = mx - mn
    s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn)
    h = mx === r ? (g - b) / d + (g < b ? 6 : 0) : mx === g ? (b - r) / d + 2 : (r - g) / d + 4
    h /= 6
  }
  return [h, s, l]
}

function rgb([h, s, l]) {
  const f = n => {
    const k = (n + h * 12) % 12, a = s * Math.min(l, 1 - l)
    return Math.round(255 * (l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1))))
  }
  return [f(0), f(8), f(4)]
}

const hex = c => '#' + c.map(v => v.toString(16).padStart(2, '0')).join('')

function luminance(c) {
  const [r, g, b] = c.map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4 })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

export function contrast(a, b) {
  const x = luminance(a), y = luminance(b)
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05)
}
