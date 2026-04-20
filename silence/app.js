// ─── Config ───────────────────────────────────────────────────────────────────
const RSS_URL  = 'https://feeds.acast.com/public/shows/silence-on-joue';

//const PROXIES  = [
//  url => `http://main.tezcat.fr/proxy?url=${url}`
//];

// ─── State ───────────────────────────────────────────────────────────────────
let allGames  = [];
let lastFetch = null;
let sortMode  = 'alpha';
let sortAsc   = true;

const MODE_DEFAULT_ASC = { alpha: true, date: false, meta: false };

// ─── RSS parsing helpers ──────────────────────────────────────────────────────

function stripHtml(html) {
  if (!html) return '';
  return html
    .replace(/<\/p>/gi, '\n').replace(/<br\s*\/?>/gi, '\n').replace(/<[^>]*>/g, '')
    .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&nbsp;/g, ' ')
    .replace(/[ \t]+/g, ' ').replace(/\n[ \t]+/g, '\n').trim();
}

function timestampToSeconds(ts) {
  if (!ts) return 0;
  ts = ts.trim();
  const colonMatch = ts.match(/^(\d+):(\d{2})(?::(\d{2}))?$/);
  if (colonMatch) {
    const [, a, b, c] = colonMatch;
    return c !== undefined
      ? parseInt(a, 10) * 3600 + parseInt(b, 10) * 60 + parseInt(c, 10)
      : parseInt(a, 10) * 60 + parseInt(b, 10);
  }
  const hBareMin = ts.match(/^(\d+)\s*h(?:eure?s?)?(\d+)$/i);
  if (hBareMin) return parseInt(hBareMin[1], 10) * 3600 + parseInt(hBareMin[2], 10) * 60;
  const hmsMatch = ts.match(/(?:(\d+)\s*h(?:eure?s?)?)?\s*(?:(\d+)\s*m(?:in(?:utes?)?)?)?\s*(?:(\d+)\s*s(?:ec(?:ondes?)?)?)?/i);
  if (hmsMatch) {
    const total = parseInt(hmsMatch[1]||'0',10)*3600 + parseInt(hmsMatch[2]||'0',10)*60 + parseInt(hmsMatch[3]||'0',10);
    if (total > 0) return total;
  }
  return 0;
}

function extractGameNamesFromTitle(title) {
  if (!title) return [];
  return [...title.matchAll(/«([^»]+)»/g)].map(m => m[1].trim()).filter(n => n.length > 1);
}

function extractChapters(text) {
  const chapters = [];
  for (const line of text.split(/[\n\r]+/)) {
    const m = line.trim().match(/^(\d{1,2}:\d{2}(?::\d{2})?)\s+(.+)$/);
    if (m) chapters.push({ timestampSeconds: timestampToSeconds(m[1]), timestamp: m[1], title: m[2].trim() });
  }
  return chapters;
}

const NON_GAME_CHAPTERS = [
  /^intro$/i, /^les?\s+news?/i, /^com\s+des?\s+coms?/i, /^la?\s+minute\s+culturelle/i,
  /^et\s+quand\s+vous\s+ne\s+jouez/i, /^bande.?annonce/i, /^jeux?\s+de\s+soci/i,
  /^la?\s+chronique/i, /^outro$/i, /^g[eé]n[eé]rique/i, /^\s*$/,
];

function isNonGameChapter(title) { return NON_GAME_CHAPTERS.some(re => re.test(title)); }

function normalizeForMatch(s) {
  return s.toLowerCase().replace(/[«»:,\.!\?'"()\[\]]/g, '').replace(/\s+/g, ' ').trim();
}

function findTimestampForGame(gameName, chapters) {
  const normGame = normalizeForMatch(gameName);
  let best = null, bestScore = 0;
  for (const chapter of chapters) {
    if (isNonGameChapter(chapter.title)) continue;
    const normChapter = normalizeForMatch(chapter.title);
    let score = 0;
    if (normChapter === normGame) {
      score = 3;
    } else if (normChapter.includes(normGame) || normGame.includes(normChapter)) {
      score = 2;
    } else {
      const gameWords    = new Set(normGame.split(' ').filter(w => w.length > 2));
      const chapterWords = new Set(normChapter.split(' ').filter(w => w.length > 2));
      let overlap = 0;
      for (const w of gameWords) if (chapterWords.has(w)) overlap++;
      if (overlap > 0) score = overlap / Math.max(gameWords.size, chapterWords.size);
    }
    if (score > bestScore) { bestScore = score; best = chapter; }
  }
  return bestScore >= 0.5 && best ? { timestamp: best.timestamp, timestampSeconds: best.timestampSeconds } : null;
}

function getAudioUrl(item) {
  const enc = item.querySelector('enclosure');
  if (enc?.getAttribute('url')) return enc.getAttribute('url');
  const media = item.getElementsByTagName('media:content')[0];
  if (media?.getAttribute('url')) return media.getAttribute('url');
  const link = item.querySelector('link')?.textContent || '';
  return /\.(mp3|m4a|ogg|aac)/i.test(link) ? link : null;
}

function xmlText(item, tag) {
  return (item.getElementsByTagName(tag)[0]?.textContent || '').trim();
}

async function fetchRss() {
  let lastErr;
  for (const proxy of PROXIES) {
    try {
      const r = await fetch(proxy(RSS_URL), (PROXY_SECRET != null) ? {headers:{'Cors-Proxy-Auth':PROXY_SECRET}} : {} );
      if (r.ok) return r.text();
      lastErr = new Error(`HTTP ${r.status}`);
    } catch (err) {
      lastErr = err;
    }
  }
  throw new Error(`RSS indisponible : ${lastErr?.message}`);
}

async function parseFeed() {
  const xml     = await fetchRss();
  const cleaned = xml.replace(/<\?xml[^?]*\?>\s*/i, '');
  const doc     = new DOMParser().parseFromString(cleaned, 'text/xml');
  const parseErr = doc.querySelector('parsererror');
  if (parseErr) throw new Error(`XML invalide : ${parseErr.textContent.trim().slice(0, 120)}`);
  const items = [...doc.querySelectorAll('item')];

  const gamesMap = new Map();

  for (const item of items) {
    const episodeTitle = xmlText(item, 'title') || 'Episode sans titre';

    if (/^quel(le)?\s/i.test(episodeTitle) || /bande.?annonce/i.test(episodeTitle) ||
        /^\[reportage\]/i.test(episodeTitle) || /^\[hors-série\]\s*(la\s+faq|le\s+bilan)/i.test(episodeTitle)) continue;

    const gameNames = extractGameNamesFromTitle(episodeTitle);
    if (gameNames.length === 0) continue;

    const audioUrl  = getAudioUrl(item);
    const pubDate   = xmlText(item, 'pubDate') || null;
    const rawDesc   = xmlText(item, 'content:encoded') || xmlText(item, 'description') || '';
    const plainText = stripHtml(rawDesc);
    const chapters  = extractChapters(plainText);

    for (let name of gameNames) {
      name = name.replace(/^[,\s]+/, '').trim();
      if (name.length < 2) continue;
      const key = name.toLowerCase();
      if (!gamesMap.has(key)) gamesMap.set(key, { name, episodes: [] });
      const ts = findTimestampForGame(name, chapters);
      gamesMap.get(key).episodes.push({
        title: episodeTitle, audioUrl, pubDate,
        timestamp: ts?.timestamp || null,
        timestampSeconds: ts?.timestampSeconds || 0,
      });
    }
  }

  return Array.from(gamesMap.values()).sort((a, b) =>
    a.name.localeCompare(b.name, 'fr', { sensitivity: 'base' })
  );
}

// ─── RAWG image + metacritic ──────────────────────────────────────────────────

const RAWG_LS_KEY = 'soj-rawg-v4';
const RAWG_TTL_MS = 30 * 24 * 60 * 60 * 1000; // 30 days

const imageCache = new Map();

function loadRawgCache() {
  try {
    const stored = JSON.parse(localStorage.getItem(RAWG_LS_KEY) || '{}');
    const now = Date.now();
    for (const [key, { data, ts }] of Object.entries(stored)) {
      if (now - ts < RAWG_TTL_MS) imageCache.set(key, data);
    }
  } catch { /* localStorage unavailable */ }
}

function saveRawgEntry(key, data) {
  try {
    const stored = JSON.parse(localStorage.getItem(RAWG_LS_KEY) || '{}');
    stored[key] = { data, ts: Date.now() };
    localStorage.setItem(RAWG_LS_KEY, JSON.stringify(stored));
  } catch { /* storage full or unavailable */ }
}

loadRawgCache();

function normName(s) {
  return s.toLowerCase()
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]/g, '');
}

async function rawgSearch(query) {
  const url = `https://api.rawg.io/api/games?key=${RAWG_KEY}&search=${encodeURIComponent(query)}&page_size=10`;
  const data = await fetch(url).then(r => r.json());
  return data.results || [];
}

function rankResults(results, gameName) {
  const q    = normName(gameName);
  const base = normName(gameName.replace(/\s*[:\-–].+$/, '').trim());
  return [...results].sort((a, b) => {
    const score = r => {
      const n = normName(r.name);
      if (n === q)                          return 4;
      if (n === base)                       return 3;
      if (n.startsWith(q) || q.startsWith(n)) return 2;
      if (n.startsWith(base) || base.startsWith(n)) return 1;
      return 0;
    };
    return score(b) - score(a);
  });
}

function simplifyPlatform(name) {
  if (/playstation/i.test(name)) return 'PlayStation';
  if (/xbox/i.test(name))        return 'Xbox';
  if (/switch|nintendo/i.test(name)) return 'Switch';
  if (/pc|windows/i.test(name))  return 'PC';
  if (/mac/i.test(name))         return 'Mac';
  if (/ios|iphone/i.test(name))  return 'iOS';
  if (/android/i.test(name))     return 'Android';
  return null;
}

async function fetchRawgData(gameName) {
  try {
    let results = await rawgSearch(gameName);
    const baseName = gameName.replace(/\s*[:\-–].+$/, '').trim();
    if ((!results.length || normName(results[0]?.name) !== normName(gameName)) && baseName !== gameName) {
      const baseResults = await rawgSearch(baseName);
      if (baseResults.length) results = [...results, ...baseResults];
    }
    if (!results.length) return null;

    const ranked  = rankResults(results, gameName);
    const best    = ranked[0];
    const withImg = ranked.find(r => r.background_image);

    const metacritic = best.metacritic || null;
    const genres     = (best.genres || []).slice(0, 3).map(g => g.name);
    const released   = best.released ? best.released.slice(0, 4) : null;
    const platforms  = [...new Set((best.platforms || [])
      .map(p => simplifyPlatform(p.platform.name)).filter(Boolean))].slice(0, 4);
    const rating     = best.rating   ? parseFloat(best.rating.toFixed(1)) : null;
    const esrb       = best.esrb_rating?.name || null;
    const playtime   = best.playtime ? Math.round(best.playtime) : null;

    let url         = withImg?.background_image || best.background_image || null;
    let description = null;
    let developer   = null;

    if (best?.slug) {
      try {
        const detail = await fetch(
          `https://api.rawg.io/api/games/${encodeURIComponent(best.slug)}?key=${RAWG_KEY}`
        ).then(r => r.json());
        if (!url) url = detail.background_image || detail.background_image_additional || null;
        developer = detail.developers?.[0]?.name || null;
        const rawDesc = (detail.description_raw || '').trim();
        if (rawDesc) description = rawDesc.split(/\n\n/)[0].trim().slice(0, 500);
      } catch {}
    }

    return { url, metacritic, genres, released, platforms, rating, esrb, playtime, description, developer };
  } catch (err) {
    console.warn(`[RAWG] ${gameName}: ${err.message}`);
    return undefined;
  }
}

async function fetchImage(name) {
  const key = name.toLowerCase();
  if (imageCache.has(key)) return imageCache.get(key)?.url || null;
  const result = await fetchRawgData(name);
  if (result === undefined) return null; // network error — don't cache
  imageCache.set(key, result);
  saveRawgEntry(key, result);
  return result?.url || null;
}

function getCachedMeta(name) {
  return imageCache.get(name.toLowerCase())?.metacritic || null;
}

// ─── Card image lazy loader ───────────────────────────────────────────────────

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
        scoreEl.classList.add('visible', meta >= 75 ? 'score-high' : meta >= 50 ? 'score-mid' : 'score-low');
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

// ─── DOM refs ─────────────────────────────────────────────────────────────────
const gameGrid      = document.getElementById('gameGrid');
const searchInput   = document.getElementById('searchInput');
const clearSearchBtn= document.getElementById('clearSearch');
const filteredCount = document.getElementById('filteredCount');
const gameCountEl   = document.getElementById('gameCount');
const lastRefreshEl = document.getElementById('lastRefresh');
const nextRefreshEl = document.getElementById('nextRefresh');
const refreshBtn    = document.getElementById('refreshBtn');
const refreshIcon   = document.getElementById('refreshIcon');
const spinner       = document.getElementById('spinner');
const emptyState    = document.getElementById('emptyState');
const emptyMsg      = document.getElementById('emptyMsg');

const detailView     = document.getElementById('detailView');
const detailBack     = document.getElementById('detailBack');
const detailImg      = document.getElementById('detailImg');
const detailImgPh    = document.getElementById('detailImgPh');
const detailTitle    = document.getElementById('detailTitle');
const detailRawgInfo = document.getElementById('detailRawgInfo');
const detailEpCount  = document.getElementById('detailEpCount');
const detailEpisodes = document.getElementById('detailEpisodes');
const detailSheet      = document.getElementById('detailSheet');
const detailNowPlaying = document.getElementById('detailNowPlaying');
const detailNpTitle    = document.getElementById('detailNpTitle');

const audioPlayer   = document.getElementById('audioPlayer');
const audioWrap     = document.getElementById('audioWrap');
const audioEl       = document.getElementById('audioEl');
const playerGame    = document.getElementById('playerGame');
const playerEpisode = document.getElementById('playerEpisode');
const playerTs      = document.getElementById('playerTs');
const playerClose   = document.getElementById('playerClose');

// ─── Utilities ────────────────────────────────────────────────────────────────
function formatDate(str) {
  if (!str) return '';
  try { return new Date(str).toLocaleDateString('fr-FR', { year: 'numeric', month: 'long', day: 'numeric' }); }
  catch { return str; }
}

function timeAgo(iso) {
  if (!iso) return '';
  const mins = Math.floor((Date.now() - new Date(iso)) / 60000);
  if (mins < 2)  return 'à l\'instant';
  if (mins < 60) return `il y a ${mins} min`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24)  return `il y a ${hrs}h`;
  const days = Math.floor(hrs / 24);
  return `il y a ${days} jour${days > 1 ? 's' : ''}`;
}

function escHtml(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

const latestDate = g => Math.max(0, ...g.episodes.map(ep => ep.pubDate ? +new Date(ep.pubDate) : 0));

// ─── Sort ─────────────────────────────────────────────────────────────────────
function sortedGames(games) {
  const dir = sortAsc ? 1 : -1;
  return [...games].sort((a, b) => {
    if (sortMode === 'date') return dir * (latestDate(a) - latestDate(b));
    if (sortMode === 'meta') {
      const ma = getCachedMeta(a.name), mb = getCachedMeta(b.name);
      if (ma === null && mb === null) return a.name.localeCompare(b.name, 'fr', { sensitivity: 'base' });
      if (ma === null) return 1;
      if (mb === null) return -1;
      return dir * (ma - mb);
    }
    return dir * a.name.localeCompare(b.name, 'fr', { sensitivity: 'base' });
  });
}

function updateSortUI() {
  document.querySelectorAll('[data-mode]').forEach(b => {
    const active = b.dataset.mode === sortMode;
    b.classList.toggle('active', active);
    const dirEl = b.querySelector('.sort-dir');
    if (dirEl) dirEl.textContent = active ? (sortAsc ? '↑' : '↓') : '';
  });
}

document.querySelector('.sort-bar').addEventListener('click', e => {
  const btn = e.target.closest('[data-mode]');
  if (!btn) return;
  const mode = btn.dataset.mode;
  if (mode === sortMode) { sortAsc = !sortAsc; } else { sortMode = mode; sortAsc = MODE_DEFAULT_ASC[mode]; }
  updateSortUI();
  applyFilter();
});

// ─── Grid ─────────────────────────────────────────────────────────────────────
function renderGrid(games) {
  imageObserver.disconnect();
  if (games.length === 0) {
    gameGrid.innerHTML = '';
    emptyState.style.display = 'flex';
    emptyMsg.textContent = allGames.length === 0
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

function applyFilter() {
  const q = searchInput.value.trim().toLowerCase();
  clearSearchBtn.style.display = q ? 'flex' : 'none';
  const result = sortedGames(q ? allGames.filter(g => g.name.toLowerCase().includes(q)) : allGames);
  filteredCount.textContent = q ? `${result.length} / ${allGames.length}` : '';
  renderGrid(result);
}

searchInput.addEventListener('input', applyFilter);
clearSearchBtn.addEventListener('click', () => { searchInput.value = ''; applyFilter(); searchInput.focus(); });

// ─── Detail view ──────────────────────────────────────────────────────────────
function renderRawgInfo(rawg) {
  if (!rawg) { detailRawgInfo.innerHTML = ''; return; }
  const { metacritic, genres, released, platforms, rating, esrb, playtime, description, developer } = rawg;

  const badges = [];
  if (metacritic) {
    const cls = metacritic >= 75 ? 'score-high' : metacritic >= 50 ? 'score-mid' : 'score-low';
    badges.push(`<span class="rawg-badge ${cls}">Metacritic ${metacritic}</span>`);
  }
  if (rating)    badges.push(`<span class="rawg-badge rawg-rating">★ ${rating}/5</span>`);
  if (released)  badges.push(`<span class="rawg-badge">${released}</span>`);
  if (esrb)      badges.push(`<span class="rawg-badge">${escHtml(esrb)}</span>`);
  if (playtime)  badges.push(`<span class="rawg-badge">~${playtime}h</span>`);
  if (genres.length)    badges.push(`<span class="rawg-badge">${escHtml(genres.join(' · '))}</span>`);
  if (platforms.length) badges.push(`<span class="rawg-badge">${escHtml(platforms.join(' · '))}</span>`);

  let html = badges.length ? `<div class="rawg-badges">${badges.join('')}</div>` : '';
  if (developer)   html += `<div class="rawg-developer">${escHtml(developer)}</div>`;
  if (description) html += `<p class="rawg-description">${escHtml(description)}</p>`;
  detailRawgInfo.innerHTML = html;
}

function markPlayingCard() {
  detailEpisodes.querySelectorAll('.episode-card').forEach(card => {
    const playing = audioEl.src && card.dataset.url === audioEl.src;
    card.classList.toggle('playing', playing);
    const icon = card.querySelector('.ep-icon');
    if (icon) icon.textContent = playing ? '⏸' : (card.classList.contains('has-audio') ? '▶' : '🔇');
  });
  const playingCard = detailEpisodes.querySelector('.episode-card.playing');
  if (playingCard && audioEl.src) {
    detailNpTitle.textContent = playingCard.dataset.episode || '';
    detailNowPlaying.style.display = 'flex';
  } else {
    detailNowPlaying.style.display = 'none';
  }
}

function openDetail(game) {
  detailTitle.textContent  = game.name;
  detailEpCount.textContent = `${game.episodes.length} épisode${game.episodes.length > 1 ? 's' : ''}`;
  detailImg.style.display  = 'none';
  detailImgPh.style.display = 'flex';
  detailRawgInfo.innerHTML = '';

  const cached = imageCache.get(game.name.toLowerCase());
  if (cached) renderRawgInfo(cached);

  fetchImage(game.name).then(url => {
    renderRawgInfo(imageCache.get(game.name.toLowerCase()));
    if (!url) return;
    detailImg.src = url;
    detailImg.alt = game.name;
    detailImg.style.display = 'block';
    detailImgPh.style.display = 'none';
    detailImg.onerror = () => { detailImg.style.display = 'none'; detailImgPh.style.display = 'flex'; };
  });

  detailEpisodes.innerHTML = game.episodes.map(ep => {
    const hasAudio = !!ep.audioUrl;
    return `<div class="episode-card ${hasAudio ? 'has-audio' : ''}"
      role="${hasAudio ? 'button' : 'listitem'}"
      tabindex="${hasAudio ? '0' : '-1'}"
      ${hasAudio ? `data-url="${escHtml(ep.audioUrl)}" data-ts="${ep.timestampSeconds || 0}" data-label="${escHtml(ep.timestamp || '')}" data-game="${escHtml(game.name)}" data-episode="${escHtml(ep.title)}"` : ''}>
      <div class="ep-icon">${hasAudio ? '▶' : '🔇'}</div>
      <div class="episode-info">
        <div class="episode-title">${escHtml(ep.title)}</div>
        <div class="episode-meta">
          <span>${formatDate(ep.pubDate)}</span>
          ${ep.timestamp ? `<span class="episode-ts">⏱ ${escHtml(ep.timestamp)}</span>` : ''}
        </div>
      </div>
      ${hasAudio ? '<div class="ep-audio-wrap"></div>' : ''}
    </div>`;
  }).join('');

  markPlayingCard();
  detailView.style.display = 'flex';
  detailSheet.scrollTop = 0;
  document.body.style.overflow = 'hidden';
  detailBack.focus();
}

function closeDetail() {
  // If audio is playing from a card, restore it to the bottom bar
  if (audioEl.src) {
    restoreAudioToBar();
    if (!audioEl.paused) {
      audioPlayer.classList.add('active');
      document.body.classList.add('player-open');
    }
  }
  detailView.classList.add('exiting');
  detailView.addEventListener('animationend', () => {
    detailView.style.display = 'none';
    detailView.classList.remove('exiting');
    document.body.style.overflow = '';
  }, { once: true });
}

detailBack.addEventListener('click', closeDetail);
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && detailView.style.display !== 'none') closeDetail();
});

detailEpisodes.addEventListener('click', e => {
  const card = e.target.closest('.episode-card.has-audio');
  if (!card) return;
  e.stopPropagation();

  if (card.classList.contains('playing')) {
    // Toggle pause / resume
    if (audioEl.paused) { audioEl.play().catch(() => {}); }
    else                { audioEl.pause(); }
    const icon = card.querySelector('.ep-icon');
    if (icon) icon.textContent = audioEl.paused ? '▶' : '⏸';
    return;
  }

  const tsSeconds = parseInt(card.dataset.ts, 10) || 0;
  playEpisode(card.dataset.game, card.dataset.episode, card.dataset.url, tsSeconds, card.dataset.label);
  markPlayingCard();
});

detailEpisodes.addEventListener('keydown', e => {
  if (e.key !== 'Enter' && e.key !== ' ') return;
  const card = e.target.closest('.episode-card.has-audio');
  if (!card) return;
  e.preventDefault();
  card.click();
});

// ─── Audio player ─────────────────────────────────────────────────────────────
function injectAudioIntoCard(audioUrl) {
  // Remove from any previous card
  detailEpisodes.querySelectorAll('.ep-audio-wrap').forEach(w => {
    if (w.contains(audioEl)) w.removeChild(audioEl);
  });
  const card = [...detailEpisodes.querySelectorAll('.episode-card.has-audio')]
    .find(c => c.dataset.url === audioUrl);
  if (card) card.querySelector('.ep-audio-wrap').appendChild(audioEl);
}

function restoreAudioToBar() {
  if (!audioWrap.contains(audioEl)) audioWrap.appendChild(audioEl);
}

function playEpisode(gameName, episodeTitle, audioUrl, tsSeconds, timestamp) {
  const inDetail = detailView.style.display !== 'none';

  const seek = () => {
    if (tsSeconds <= 0) return;
    if (isFinite(audioEl.duration)) { audioEl.currentTime = tsSeconds; }
    else audioEl.addEventListener('durationchange', () => { audioEl.currentTime = tsSeconds; }, { once: true });
  };

  if (inDetail) {
    audioPlayer.classList.remove('active');
    document.body.classList.remove('player-open');
    injectAudioIntoCard(audioUrl);
  } else {
    restoreAudioToBar();
    playerGame.textContent    = gameName;
    playerEpisode.textContent = episodeTitle;
    playerTs.textContent      = timestamp ? `⏱ ${timestamp}` : '';
    audioPlayer.classList.add('active');
    document.body.classList.add('player-open');
  }

  if (audioEl.src === audioUrl) { seek(); audioEl.play().catch(() => {}); return; }
  audioEl.src = audioUrl;
  audioEl.load();
  audioEl.addEventListener('canplay', () => { seek(); audioEl.play().catch(() => {}); }, { once: true });
  audioEl.play().catch(() => {});
}

playerClose.addEventListener('click', () => {
  audioEl.pause();
  audioEl.src = '';
  audioPlayer.classList.remove('active');
  document.body.classList.remove('player-open');
  markPlayingCard();
});

// ─── Data loading ─────────────────────────────────────────────────────────────
async function loadGames() {
  spinner.style.display = 'flex';
  emptyState.style.display = 'none';
  gameGrid.innerHTML = '';
  refreshBtn.disabled = true;
  refreshIcon.classList.add('spinning');
  try {
    allGames  = await parseFeed();
    lastFetch = new Date().toISOString();
    gameCountEl.textContent   = `${allGames.length} jeu${allGames.length > 1 ? 'x' : ''}`;
    lastRefreshEl.textContent = `Mis à jour ${timeAgo(lastFetch)}`;
    nextRefreshEl.textContent = '';
    applyFilter();
  } catch (err) {
    emptyState.style.display = 'flex';
    emptyMsg.textContent = `Erreur : ${err.message}`;
  } finally {
    spinner.style.display = 'none';
    refreshBtn.disabled = false;
    refreshIcon.classList.remove('spinning');
  }
}

refreshBtn.addEventListener('click', loadGames);

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}

loadGames();
