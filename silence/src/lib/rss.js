import { getToken } from './auth.js';
import { stripHtml, timestampToSeconds, normalizeForMatch } from './utils.js';

const RSS_URL = 'https://feeds.acast.com/public/shows/silence-on-joue';

export function extractGameNamesFromTitle(title) {
  if (!title) return [];
  return [...title.matchAll(/«([^»]+)»/g)].map(m => m[1].trim()).filter(n => n.length > 1);
}

export function extractChapters(text) {
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

export function isNonGameChapter(title) { return NON_GAME_CHAPTERS.some(re => re.test(title)); }

export function findTimestampForGame(gameName, chapters) {
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
  const url = `${import.meta.env.VITE_PROXY_URL}?url=${RSS_URL}`;
  const r = await fetch(url, { headers: { 'Authorization': `Bearer ${getToken()}` } });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.text();
}

export async function parseFeed() {
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
