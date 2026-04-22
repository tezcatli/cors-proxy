import { parseFeed } from './rss.js';
import { state, MODE_DEFAULT_ASC } from './state.js';
import { timeAgo } from './utils.js';
import { updateSortUI } from './ui/sort.js';
import { applyFilter, setLoading, setError } from './ui/grid.js';
import { isLoggedIn, getUserEmail, logout } from './auth.js';
import { initLoginOverlay, showLoginOverlay, hideLoginOverlay } from './ui/login.js';

const gameCountEl   = document.getElementById('gameCount');
const lastRefreshEl = document.getElementById('lastRefresh');
const nextRefreshEl = document.getElementById('nextRefresh');
const refreshBtn    = document.getElementById('refreshBtn');
const refreshIcon   = document.getElementById('refreshIcon');
const spinner       = document.getElementById('spinner');
const userEmailEl   = document.getElementById('userEmail');
const logoutBtn     = document.getElementById('logoutBtn');

async function loadGames() {
  spinner.style.display = 'flex';
  setLoading();
  refreshBtn.disabled   = true;
  refreshIcon.classList.add('spinning');
  try {
    state.allGames  = await parseFeed();
    state.lastFetch = new Date().toISOString();
    gameCountEl.textContent   = `${state.allGames.length} jeu${state.allGames.length > 1 ? 'x' : ''}`;
    lastRefreshEl.textContent = `Mis à jour ${timeAgo(state.lastFetch)}`;
    nextRefreshEl.textContent = '';
    applyFilter();
  } catch (err) {
    setError(`Erreur : ${err.message}`);
  } finally {
    spinner.style.display = 'none';
    refreshBtn.disabled   = false;
    refreshIcon.classList.remove('spinning');
  }
}

function startApp() {
  state.userEmail     = getUserEmail();
  userEmailEl.textContent = state.userEmail || '';
  logoutBtn.hidden    = false;
  loadGames();
}

function waitForLogin() {
  showLoginOverlay();
  document.addEventListener('auth:success', () => {
    hideLoginOverlay();
    startApp();
  }, { once: true });
}

document.querySelector('.sort-bar').addEventListener('click', e => {
  const btn = e.target.closest('[data-mode]');
  if (!btn) return;
  const mode = btn.dataset.mode;
  if (mode === state.sortMode) { state.sortAsc = !state.sortAsc; }
  else { state.sortMode = mode; state.sortAsc = MODE_DEFAULT_ASC[mode]; }
  updateSortUI();
  applyFilter();
});

refreshBtn.addEventListener('click', loadGames);

logoutBtn.addEventListener('click', () => {
  logout();
  state.allGames  = [];
  state.userEmail = null;
  userEmailEl.textContent = '';
  logoutBtn.hidden = true;
  gameCountEl.textContent   = '';
  lastRefreshEl.textContent = '';
  waitForLogin();
});

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}

initLoginOverlay();

if (isLoggedIn()) {
  startApp();
} else {
  waitForLogin();
}
