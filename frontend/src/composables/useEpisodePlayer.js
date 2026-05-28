import { usePlayerStore } from '../stores/player.js'

export function useEpisodePlayer(gameContext = null) {
  // gameContext: a computed ref returning { name, slug, coverImageId }
  // or null (feed context — derives from episode.games[0])
  const playerStore = usePlayerStore()

  function isEpPlaying(ep) {
    return !!playerStore.current && ep.audioUrl === playerStore.current.url
  }

  function playEp(ep) {
    const ctx     = gameContext?.value
    const name    = ctx?.name  ?? ep.games?.[0]?.name ?? 'Silence on Joue'
    const slug    = ctx?.slug  ?? ep.games?.[0]?.slug ?? null
    const coverId = ctx?.coverImageId
      ?? ep.chapters?.find(ch => ch.slug === slug)?.coverImageId
      ?? null
    playerStore.play({
      game:            name,
      slug,
      episode:         ep.title,
      url:             ep.audioUrl,
      ts:              ep.timestampSeconds || 0,
      timestamp:       ep.timestamp || null,
      episodeImageUrl: ep.imageUrl ?? null,
      pubTs:           ep.pubTs,
      episodeSlug:     ep.slug,
      coverImageId:    coverId,
      chapters:        ep.chapters ?? [],
    })
  }

  function togglePause() { playerStore.setPaused(!playerStore.paused) }

  return { playerStore, isEpPlaying, playEp, togglePause }
}
