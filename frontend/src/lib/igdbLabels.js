// IGDB's genre, mode and perspective names are English and finite: their French
// for the game page's fiche technique. A name not listed shows as IGDB gives it.
const FR = {
  // Genres
  'Adventure':                  'Aventure',
  'Arcade':                     'Arcade',
  'Card & Board Game':          'Cartes et plateau',
  'Fighting':                   'Combat',
  "Hack and slash/Beat 'em up": "Beat'em all",
  'Indie':                      'Indé',
  'MOBA':                       'MOBA',
  'Music':                      'Musique',
  'Pinball':                    'Flipper',
  'Platform':                   'Plateforme',
  'Point-and-click':            'Point & click',
  'Puzzle':                     'Réflexion',
  'Quiz/Trivia':                'Quiz',
  'Racing':                     'Course',
  'Real Time Strategy (RTS)':   'Stratégie en temps réel',
  'Role-playing (RPG)':         'Jeu de rôle',
  'Shooter':                    'Tir',
  'Simulator':                  'Simulation',
  'Sport':                      'Sport',
  'Strategy':                   'Stratégie',
  'Tactical':                   'Tactique',
  'Turn-based strategy (TBS)':  'Stratégie au tour par tour',
  'Visual Novel':               'Visual novel',
  // Modes
  'Single player':                         'Solo',
  'Multiplayer':                           'Multijoueur',
  'Co-operative':                          'Coopération',
  'Split screen':                          'Écran partagé',
  'Massively Multiplayer Online (MMO)':    'MMO',
  'Battle Royale':                         'Battle royale',
  // Perspectives
  'First person':          'Vue subjective',
  'Third person':          'Troisième personne',
  'Side view':             'Vue de côté',
  'Bird view / Isometric': 'Vue de dessus / isométrique',
  'Virtual Reality':       'Réalité virtuelle',
  'Text':                  'Textuel',
  'Auditory':              'Audio',
}

export function frLabel(name) {
  return FR[name] ?? name
}
