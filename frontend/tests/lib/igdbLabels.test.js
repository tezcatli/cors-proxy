import { describe, it, expect } from 'vitest'
import { frLabel } from '../../src/lib/igdbLabels.js'

describe('frLabel', () => {
  it('translates the IGDB genres, modes and perspectives it knows', () => {
    expect(frLabel('Role-playing (RPG)')).toBe('Jeu de rôle')
    expect(frLabel('Single player')).toBe('Solo')
    expect(frLabel('Third person')).toBe('Troisième personne')
  })

  it('shows an unknown name as IGDB gives it', () => {
    expect(frLabel('Roguelike deckbuilder')).toBe('Roguelike deckbuilder')
  })
})
