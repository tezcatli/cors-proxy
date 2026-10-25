// Frontend podcast registry — mirrors backend/podcasts.py. Drives the podcasts'
// row and pages, and the source badges. `id`/`label`/`name` match what the API returns
// in catalog `podcasts` and episode `podcast` fields; `label` is the sigle shown
// in mono wherever a row is tight. `accent` is the podcast's colour, picked by
// hand from its image (whose host sends no CORS header, so it can't be read like
// a cover); null keeps the neutral tokens.

export const PODCASTS = [
  { id: 'silence-on-joue',    label: 'SOJ',  name: 'Silence on Joue',        accent: null },
  { id: 'fin-du-game',        label: 'FDG',  name: 'Fin du Game',            accent: '#e0a24a' },
  { id: 'triple-click',       label: 'TC',   name: 'Triple Click',           accent: '#2bb5bf' },
  { id: 'the-besties',        label: 'BES',  name: 'The Besties',            accent: '#ffcf3f' },
  { id: 'origami',            label: 'ORI',  name: "ORIGAMI L'Hebdo",        accent: '#ffcc33' },
  { id: 'zqsd',               label: 'ZQSD', name: 'ZQSD',                   accent: '#e8403a' },
  { id: 'game-informer-show', label: 'GI',   name: 'The Game Informer Show', accent: '#4a6ff0' },
]

export const PODCAST_BY_ID = Object.fromEntries(PODCASTS.map(p => [p.id, p]))

export function podcastMeta(id) {
  return PODCAST_BY_ID[id] || null
}
