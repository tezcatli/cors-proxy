import { apiFetch } from './auth.js'

export async function parseFeed() {
  const r = await apiFetch('/rss/games')
  if (!r.ok) throw new Error(`RSS ${r.status}`)
  return r.json()
}
