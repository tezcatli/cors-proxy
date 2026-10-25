import { ref } from 'vue'

// When each podcast's page was last seen — its newest episode's date then — so
// the Ludothèque's tiles can mark a podcast with an episode out since
// (`ludo.podcastsSeen`, {id: pubTs}). A podcast never visited counts as seen at
// its newest episode: on first use, no tile is marked.

const KEY  = 'ludo.podcastsSeen'
const seen = ref(read())

function read() {
  try { return JSON.parse(localStorage.getItem(KEY)) ?? {} } catch { return {} }
}
function write() {
  try { localStorage.setItem(KEY, JSON.stringify(seen.value)) } catch { /* blocked: memory only */ }
}

export function usePodcastsSeen() {
  /** Whether `id` has an episode newer than its page's last visit. */
  function isNew(id, latestTs) {
    return !!latestTs && id in seen.value && latestTs > seen.value[id]
  }
  /** A podcast met for the first time counts as seen at `latestTs`. */
  function meet(id, latestTs) {
    if (!latestTs || id in seen.value) return
    seen.value = { ...seen.value, [id]: latestTs }
    write()
  }
  /** The page of `id` was seen, its newest episode dated `latestTs`. */
  function markSeen(id, latestTs) {
    if (!latestTs || seen.value[id] >= latestTs) return
    seen.value = { ...seen.value, [id]: latestTs }
    write()
  }
  return { isNew, meet, markSeen }
}
