import { usePlayerStore } from '../stores/player.js'

export function useEpisodePlayer(gameContext = null) {
  // gameContext: a computed ref returning { name, slug, coverImageId }
  // or null (feed context — derives from episode.games[0])
  const playerStore = usePlayerStore()

  // On a game's page, the same episode audio playing another game's review is
  // not "this" review: a tap must jump to this game, not pause/resume the other.
  function isEpPlaying(ep) {
    const cur = playerStore.current
    if (!cur || ep.audioUrl !== cur.url) return false
    const slug = gameContext?.value?.slug
    return !slug || cur.slug === slug
  }

  function playEp(ep) {
    const ctx     = gameContext?.value
    const name    = ctx?.name  ?? ep.games?.[0]?.name ?? ep.podcast?.name ?? 'Ludothèque'
    const slug    = ctx?.slug  ?? ep.games?.[0]?.slug ?? null
    const coverId = ctx?.coverImageId
      ?? ep.chapters?.find(ch => ch.slug === slug)?.coverImageId
      ?? null

    playerStore.play({
      game:            name,
      slug,
      episode:         ep.title,
      url:             ep.audioUrl,
      // Resume from saved progress when partway through; untouched/finished restarts.
      ts:              playerStore.resumeTimeFor(ep.slug, ep.timestampSeconds || 0),
      timestamp:       ep.timestamp || null,
      episodeImageUrl: ep.imageUrl ?? null,
      pubTs:           ep.pubTs,
      episodeSlug:     ep.slug,
      episodeUrlSlug:  ep.urlSlug ?? null,
      coverImageId:    coverId,
      chapters:        ep.chapters ?? [],
      podcast:         ep.podcast ?? null,
      tests:           ep.games ?? [],
    })
  }

  function togglePause() { playerStore.togglePlayback() }

  return { playerStore, isEpPlaying, playEp, togglePause }
}
