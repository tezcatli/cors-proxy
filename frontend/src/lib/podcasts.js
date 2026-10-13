// Frontend podcast registry — mirrors backend/podcasts.py. Drives the catalog
// filter and the source badges. `id`/`label`/`name` match what the API returns
// in catalog `podcasts` and episode `podcast` fields; `color` is badge-only.

export const PODCASTS = [
  { id: 'silence-on-joue', label: 'SoJ', name: 'Silence on Joue', color: '#e94560' },
  { id: 'fin-du-game',     label: 'FDG', name: 'Fin du Game',     color: '#3bb6a6' },
  { id: 'triple-click',    label: 'TC',  name: 'Triple Click',    color: '#f2a541' },
  { id: 'the-besties',     label: 'BES', name: 'The Besties',     color: '#8e7cc3' },
]

export const PODCAST_BY_ID = Object.fromEntries(PODCASTS.map(p => [p.id, p]))

export function podcastMeta(id) {
  return PODCAST_BY_ID[id] || null
}
