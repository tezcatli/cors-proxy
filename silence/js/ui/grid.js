import { state } from '../state.js';
import { fetchImage, getCachedMeta } from '../rawg.js';
import { escHtml, getScoreClass } from '../utils.js';
import { sortedGames } from './sort.js';
import { openDetail } from './detail.js';

const gameGrid       = document.getElementById('gameGrid');
const searchInput    = document.getElementById('searchInput');
const clearSearchBtn = document.getElementById('clearSearch');
const filteredCount  = document.getElementById('filteredCount');
const emptyState     = document.getElementById('emptyState');
const emptyMsg       = document.getElementById('emptyMsg');

function loadCardImage(card) {
  const img = card.querySelector('.card-img');
  if (!img || img.dataset.loaded) return;
  img.dataset.loaded = 'true';
  const ph      = card.querySelector('.card-ph');
  const scoreEl = card.querySelector('.card-score');
  ph?.classList.add('loading');
  fetchImage(img.dataset.game).then(url => {
    ph?.classList.remove('loading');
    if (scoreEl) {
      const meta = getCachedMeta(img.dataset.game);
      if (meta) {
        scoreEl.textContent = meta;
        scoreEl.classList.add('visible', getScoreClass(meta));
      }
    }
    if (!url) return;
    img.src = url;
    img.style.display = 'block';
    if (ph) ph.style.display = 'none';
    img.onerror = () => { img.style.display = 'none'; if (ph) ph.style.display = 'flex'; };
  });
}

const imageObserver = new IntersectionObserver(entries => {
  for (const { isIntersecting, target } of entries) {
    if (!isIntersecting) continue;
    imageObserver.unobserve(target);
    loadCardImage(target);
  }
}, { rootMargin: '300px' });

function renderGrid(games) {
  imageObserver.disconnect();
  if (games.length === 0) {
    gameGrid.innerHTML = '';
    emptyState.style.display = 'flex';
    emptyMsg.textContent = state.allGames.length === 0
      ? 'Aucun jeu dans le catalogue. Essayez d\'actualiser.'
      : 'Aucun jeu ne correspond à votre recherche.';
    return;
  }
  emptyState.style.display = 'none';
  gameGrid.innerHTML = games.map(g => `
    <div class="game-card" tabindex="0" role="button" aria-label="${escHtml(g.name)}">
      <div class="card-img-wrap">
        <img class="card-img" data-game="${escHtml(g.name)}" alt="${escHtml(g.name)}" style="display:none">
        <div class="card-ph">🎮</div>
        <div class="card-score"></div>
      </div>
      <div class="card-body">
        <div class="card-name">${escHtml(g.name)}</div>
        <div class="card-meta">${g.episodes.length} épisode${g.episodes.length > 1 ? 's' : ''}</div>
      </div>
    </div>`).join('');

  gameGrid.querySelectorAll('.game-card').forEach((card, i) => {
    const game = games[i];
    card.addEventListener('click', () => openDetail(game));
    card.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openDetail(game); }
    });
    imageObserver.observe(card);
  });
}

export function applyFilter() {
  const q = searchInput.value.trim().toLowerCase();
  clearSearchBtn.style.display = q ? 'flex' : 'none';
  const result = sortedGames(q ? state.allGames.filter(g => g.name.toLowerCase().includes(q)) : state.allGames);
  filteredCount.textContent = q ? `${result.length} / ${state.allGames.length}` : '';
  renderGrid(result);
}

searchInput.addEventListener('input', applyFilter);
clearSearchBtn.addEventListener('click', () => { searchInput.value = ''; applyFilter(); searchInput.focus(); });

export function setLoading() {
  emptyState.style.display = 'none';
  gameGrid.innerHTML = '';
}

export function setError(msg) {
  emptyState.style.display = 'flex';
  emptyMsg.textContent = msg;
}
