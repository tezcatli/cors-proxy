// Frontend podcast registry — mirrors backend/podcasts.py. Drives the catalog
// filter and the source badges. `id`/`label`/`name` match what the API returns
// in catalog `podcasts` and episode `podcast` fields; `label` is the sigle shown
// in mono wherever a row is tight.

export const PODCASTS = [
  { id: 'silence-on-joue', label: 'SOJ', name: 'Silence on Joue' },
  { id: 'fin-du-game',     label: 'FDG', name: 'Fin du Game' },
  { id: 'triple-click',    label: 'TC',  name: 'Triple Click' },
  { id: 'the-besties',     label: 'BES', name: 'The Besties' },
]

export const PODCAST_BY_ID = Object.fromEntries(PODCASTS.map(p => [p.id, p]))

export function podcastMeta(id) {
  return PODCAST_BY_ID[id] || null
}
