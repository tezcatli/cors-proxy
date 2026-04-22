import { state } from '../state.js';

const audioEl    = document.getElementById('audioEl');
const audioPlayer = document.getElementById('audioPlayer');

const audioWrap     = document.getElementById('audioWrap');
const playerGame    = document.getElementById('playerGame');
const playerEpisode = document.getElementById('playerEpisode');
const playerTs      = document.getElementById('playerTs');
const playerClose   = document.getElementById('playerClose');

const detailEpisodes   = document.getElementById('detailEpisodes');
const detailNowPlaying = document.getElementById('detailNowPlaying');
const detailNpTitle    = document.getElementById('detailNpTitle');

export function hasActiveAudio() { return !!audioEl.src; }
export function isAudioPaused()  { return audioEl.paused; }

export function showPlayer() {
  audioPlayer.classList.add('active');
  document.body.classList.add('player-open');
}

export function togglePlayback() {
  if (audioEl.paused) audioEl.play().catch(() => {});
  else                audioEl.pause();
}

export function markPlayingCard() {
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

function injectAudioIntoCard(audioUrl) {
  const currentWrap = audioEl.closest('.ep-audio-wrap');
  if (currentWrap) currentWrap.removeChild(audioEl);
  const card = [...detailEpisodes.querySelectorAll('.episode-card.has-audio')]
    .find(c => c.dataset.url === audioUrl);
  if (card) card.querySelector('.ep-audio-wrap').appendChild(audioEl);
}

export function restoreAudioToBar() {
  if (!audioWrap.contains(audioEl)) audioWrap.appendChild(audioEl);
}

export function playEpisode(gameName, episodeTitle, audioUrl, tsSeconds, timestamp) {
  const seek = () => {
    if (tsSeconds <= 0) return;
    if (isFinite(audioEl.duration)) { audioEl.currentTime = tsSeconds; }
    else audioEl.addEventListener('durationchange', () => { audioEl.currentTime = tsSeconds; }, { once: true });
  };

  if (state.detailOpen) {
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
