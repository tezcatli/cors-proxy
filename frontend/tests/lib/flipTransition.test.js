import { describe, it, expect, vi, beforeEach } from 'vitest'
import { captureSource, playInto } from '../../src/lib/flipTransition.js'

const rect = (top, left, height, width) => ({ top, left, height, width, bottom: top + height, right: left + width })

// A tile in a scrolling list that starts at y = 64 (below the header), and the
// game page's cover it flies into.
function scene(tileTop) {
  document.body.innerHTML = '<div id="list" style="overflow: auto"><img id="tile"></div><button id="cover"></button>'
  const list = document.getElementById('list'), tile = document.getElementById('tile'), cover = document.getElementById('cover')
  list.getBoundingClientRect  = () => rect(64, 0, 700, 400)
  tile.getBoundingClientRect  = () => rect(tileTop, 20, 160, 120)
  cover.getBoundingClientRect = () => rect(80, 100, 320, 240)
  cover.animate = vi.fn()
  return { tile, cover }
}

beforeEach(() => {
  vi.stubGlobal('matchMedia', () => ({ matches: false }))
  Object.assign(window, { innerWidth: 400, innerHeight: 800 })
})

describe('the cover’s flight', () => {
  it.each([
    ['flies from a tile seen whole', 200, 1],
    ['stays put when the tile is partly scrolled under the header', 20, 0],
  ])('%s', (_, tileTop, flights) => {
    const { tile, cover } = scene(tileTop)
    captureSource('cover:a', tile)
    playInto('cover:a', cover)
    expect(cover.animate).toHaveBeenCalledTimes(flights)
  })
})
