import { escHtml, formatDate, getScoreClass } from '../utils.js';
import { fetchImage, getCachedData } from '../rawg.js';
import { state } from '../state.js';
import {
  playEpisode, markPlayingCard, restoreAudioToBar,
  hasActiveAudio, isAudioPaused, showPlayer, togglePlayback,
} from './player.js';

const detailView     = document.getElementById('detailView');
const detailBack     = document.getElementById('detailBack');
const detailImg      = document.getElementById('detailImg');
const detailImgPh    = document.getElementById('detailImgPh');
const detailTitle    = document.getElementById('detailTitle');
const detailRawgInfo = document.getElementById('detailRawgInfo');
const detailEpCount  = document.getElementById('detailEpCount');
const detailEpisodes = document.getElementById('detailEpisodes');
const detailSheet    = document.getElementById('detailSheet');

function renderRawgInfo(rawg) {
  if (!rawg) { detailRawgInfo.innerHTML = ''; return; }
  const { metacritic, genres, released, platforms, rating, esrb, playtime, description, developer } = rawg;

  const badges = [];
  if (metacritic) badges.push(`<span class="rawg-badge ${getScoreClass(metacritic)}">Metacritic ${metacritic}</span>`);
  if (rating)           badges.push(`<span class="rawg-badge rawg-rating">★ ${rating}/5</span>`);
  if (released)         badges.push(`<span class="rawg-badge">${released}</span>`);
  if (esrb)             badges.push(`<span class="rawg-badge">${escHtml(esrb)}</span>`);
  if (playtime)         badges.push(`<span class="rawg-badge">~${playtime}h</span>`);
  if (genres.length)    badges.push(`<span class="rawg-badge">${escHtml(genres.join(' · '))}</span>`);
  if (platforms.length) badges.push(`<span class="rawg-badge">${escHtml(platforms.join(' · '))}</span>`);

  let html = badges.length ? `<div class="rawg-badges">${badges.join('')}</div>` : '';
  if (developer)   html += `<div class="rawg-developer">${escHtml(developer)}</div>`;
  if (description) html += `<p class="rawg-description">${escHtml(description)}</p>`;
  detailRawgInfo.innerHTML = html;
}

export function openDetail(game) {
  detailTitle.textContent   = game.name;
  detailEpCount.textContent = `${game.episodes.length} épisode${game.episodes.length > 1 ? 's' : ''}`;
  detailImg.style.display   = 'none';
  detailImgPh.style.display = 'flex';
  detailRawgInfo.innerHTML  = '';

  const cached = getCachedData(game.name);
  if (cached) renderRawgInfo(cached);

  fetchImage(game.name).then(url => {
    renderRawgInfo(getCachedData(game.name));
    if (!url) return;
    detailImg.src = url;
    detailImg.alt = game.name;
    detailImg.style.display   = 'block';
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
  state.detailOpen = true;
  detailView.style.display = 'flex';
  detailSheet.scrollTop = 0;
  document.body.style.overflow = 'hidden';
  detailBack.focus();
}

function closeDetail() {
  if (hasActiveAudio()) {
    restoreAudioToBar();
    if (!isAudioPaused()) showPlayer();
  }
  detailView.classList.add('exiting');
  detailView.addEventListener('animationend', () => {
    state.detailOpen = false;
    detailView.style.display = 'none';
    detailView.classList.remove('exiting');
    document.body.style.overflow = '';
  }, { once: true });
}

detailBack.addEventListener('click', closeDetail);

document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && state.detailOpen) closeDetail();
});

detailEpisodes.addEventListener('click', e => {
  const card = e.target.closest('.episode-card.has-audio');
  if (!card) return;
  e.stopPropagation();

  if (card.classList.contains('playing')) {
    togglePlayback();
    const icon = card.querySelector('.ep-icon');
    if (icon) icon.textContent = isAudioPaused() ? '▶' : '⏸';
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
