import { describe, it, expect } from 'vitest'
import { paletteOf, themeStyle, contrast, useGameTheme } from '../../src/composables/useGameTheme.js'

const hexRgb = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16))

// `n` RGBA pixels of one colour, in an ImageData's layout.
function pixels(n, [r, g, b]) {
  const d = new Uint8ClampedArray(n * 4)
  for (let i = 0; i < n; i++) d.set([r, g, b, 255], i * 4)
  return d
}

describe('paletteOf', () => {
  it('takes its accent from the cover’s vivid hue, readable on the black page', () => {
    const p = paletteOf(pixels(200, [200, 40, 30]))
    const [r, g, b] = hexRgb(p.accent)
    expect(r).toBeGreaterThan(g)
    expect(r).toBeGreaterThan(b)
    expect(contrast(hexRgb(p.accent), [9, 9, 12])).toBeGreaterThanOrEqual(4.5)
  })

  it('lights the halo with a second hue of the cover, far from the first', () => {
    const p = paletteOf(new Uint8ClampedArray([...pixels(150, [200, 40, 30]), ...pixels(100, [30, 90, 220])]))
    const [r, , b] = p.glow2.match(/\d+/g).map(Number)
    expect(b).toBeGreaterThan(r)
  })

  it('stays near-white for a cover without colour', () => {
    const p = paletteOf(pixels(200, [120, 120, 120]))
    expect(hexRgb(p.accent).every(v => v > 220)).toBe(true)
  })

  it('writes on the accent in whichever of black or white reads better', () => {
    expect(paletteOf(pixels(200, [250, 220, 40])).on).toBe('#09090c')
  })
})

describe('themeStyle', () => {
  it('sets nothing without a palette, so the neutral tokens hold', () => {
    expect(themeStyle(null)).toEqual({})
  })

  it('sets the game’s light, never the ground: the page stays black', () => {
    const p = paletteOf(pixels(200, [30, 90, 220]))
    const style = themeStyle(p)
    expect(style).toMatchObject({ '--c-accent': p.accent, '--game-glow': p.glow, '--game-glow-2': p.glow2 })
    expect(style).not.toHaveProperty('--c-bg')
    expect(style).not.toHaveProperty('--c-surface')
  })
})

describe('useGameTheme', () => {
  it('applies a palette kept from an earlier visit at once, without reading the cover', () => {
    const kept = paletteOf(pixels(200, [40, 200, 90]))
    localStorage.setItem('ludo.palettes.v2', JSON.stringify({ coKept: kept }))
    const { style } = useGameTheme('coKept', { fetch: false })
    expect(style.value['--c-accent']).toBe(kept.accent)
  })
})
