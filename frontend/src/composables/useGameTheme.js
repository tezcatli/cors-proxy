import { ref, computed, watch, unref } from 'vue'
import { igdbUrl } from '../lib/igdbCdn.js'

// A game's colours, read from its cover (DECISIONS.md, « Interface »: each game
// page pays homage to its game). The cover's most vivid hue becomes the accent,
// lifted until it reads at 4.5:1 on the game's own panel; the ground and the
// panels are that hue, nearly black. `style` overrides the --c-* tokens on the
// subtree it is bound to, so everything there that reads --c-accent, --c-bg,
// --c-surface or --c-line takes the game's colours. IGDB's CDN allows reading
// the pixels (Access-Control-Allow-Origin: *); when it can't be read the tokens
// stay neutral.
//
// A palette is read once per cover and kept (memory, then localStorage), so a
// game seen before opens in its colours at once. A tile that shows the cover
// anyway reads it from its own <img> (`learn`) rather than fetch it again.

const SAMPLE_W = 36
const SAMPLE_H = 48
const STORE_KEY = 'ludo.palettes'
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

/** The palette of RGBA pixels (an ImageData's data): {accent, on, bg, panel, line, glow, veil}. */
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
  const best = bins.reduce((a, b) => (b.w > a.w ? b : a))
  let accent = [0, 0, 0.9]                             // no hue to speak of: near-white
  if (best.n >= 8) {
    const [h, s, l] = hsl(best.r / best.n, best.g / best.n, best.b / best.n)
    accent = [h, Math.max(s, 0.55), Math.min(Math.max(l, 0.55), 0.7)]
  }
  const sat   = Math.min(accent[1], 0.45) * 0.5
  const bg    = rgb([accent[0], sat, 0.06])
  const panel = rgb([accent[0], sat, 0.1])
  const a = [...accent]
  while (contrast(rgb(a), panel) < 4.5 && a[2] < 0.95) a[2] += 0.03
  const ar = rgb(a)
  return {
    accent: hex(ar),
    on:     contrast(ar, [9, 9, 12]) >= contrast(ar, [255, 255, 255]) ? '#09090c' : '#ffffff',
    bg:     hex(bg),
    panel:  hex(panel),
    line:   `rgba(${ar.join(',')}, 0.35)`,
    glow:   `rgba(${ar.join(',')}, 0.4)`,
    veil:   `rgba(${bg.join(',')}, 0.75)`,
  }
}

/** The CSS variables a palette sets on a subtree; {} for none (the neutral tokens). */
export function themeStyle(p) {
  if (!p) return {}
  return {
    '--c-accent':    p.accent,
    '--c-accent-fg': p.on,
    '--c-bg':        p.bg,
    '--c-surface':   p.panel,
    '--c-line':      p.line,
    '--game-glow':   p.glow,
    '--game-veil':   p.veil,
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
