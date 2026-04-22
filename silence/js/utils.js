export function stripHtml(html) {
  if (!html) return '';
  return html
    .replace(/<\/p>/gi, '\n').replace(/<br\s*\/?>/gi, '\n').replace(/<[^>]*>/g, '')
    .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&nbsp;/g, ' ')
    .replace(/[ \t]+/g, ' ').replace(/\n[ \t]+/g, '\n').trim();
}

export function timestampToSeconds(ts) {
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

export function normalizeForMatch(s) {
  return s.toLowerCase().replace(/[«»:,\.!\?'"()\[\]]/g, '').replace(/\s+/g, ' ').trim();
}

export function formatDate(str) {
  if (!str) return '';
  try { return new Date(str).toLocaleDateString('fr-FR', { year: 'numeric', month: 'long', day: 'numeric' }); }
  catch { return str; }
}

export function timeAgo(iso) {
  if (!iso) return '';
  const mins = Math.floor((Date.now() - new Date(iso)) / 60000);
  if (mins < 2)  return 'à l\'instant';
  if (mins < 60) return `il y a ${mins} min`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24)  return `il y a ${hrs}h`;
  const days = Math.floor(hrs / 24);
  return `il y a ${days} jour${days > 1 ? 's' : ''}`;
}

export function escHtml(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

export const latestDate = g => Math.max(0, ...g.episodes.map(ep => ep.pubDate ? +new Date(ep.pubDate) : 0));

export function getScoreClass(score) {
  return score >= 75 ? 'score-high' : score >= 50 ? 'score-mid' : 'score-low';
}
