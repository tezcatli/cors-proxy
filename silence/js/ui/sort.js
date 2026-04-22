import { state } from '../state.js';
import { getCachedMeta } from '../rawg.js';
import { latestDate } from '../utils.js';

export function sortedGames(games) {
  const dir = state.sortAsc ? 1 : -1;
  return [...games].sort((a, b) => {
    if (state.sortMode === 'date') return dir * (latestDate(a) - latestDate(b));
    if (state.sortMode === 'meta') {
      const ma = getCachedMeta(a.name), mb = getCachedMeta(b.name);
      if (ma === null && mb === null) return a.name.localeCompare(b.name, 'fr', { sensitivity: 'base' });
      if (ma === null) return 1;
      if (mb === null) return -1;
      return dir * (ma - mb);
    }
    return dir * a.name.localeCompare(b.name, 'fr', { sensitivity: 'base' });
  });
}

export function updateSortUI() {
  document.querySelectorAll('[data-mode]').forEach(b => {
    const active = b.dataset.mode === state.sortMode;
    b.classList.toggle('active', active);
    const dirEl = b.querySelector('.sort-dir');
    if (dirEl) dirEl.textContent = active ? (state.sortAsc ? '↑' : '↓') : '';
  });
}
