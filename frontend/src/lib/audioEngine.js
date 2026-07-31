/**
 * The playback state machine — the single owner of the <audio> element.
 *
 * Why this exists: the element lies. Android Chrome releases a paused track's
 * buffered data (and sometimes the whole resource) while the tab is
 * backgrounded; a later play() can then hang with no `playing`, no `canplay`
 * and no `error` — forever. So the engine never *predicts* whether the element
 * is healthy: it records what the user asked for (`intent`), tries the cheap
 * thing first, and lets a **watchdog** escalate (reload → reload → `failed`)
 * when playback provably didn't start. `failed` is the point of the design:
 * a bounded, visible dead end the UI can offer to retry, instead of a spinner
 * that never stops.
 *
 * Framework-free on purpose — the whole ladder is unit-testable against a fake
 * media element (see `setMediaFactory`).
 */

const MAX_RELOADS  = 2                     // then `failed`; the user retries by hand
const WATCHDOG_MS  = [6000, 10000, 14000]  // per attempt — a slow 3G load must not be failed
const NETWORK_NO_SOURCE = 3

let _mediaFactory = () => new Audio()

/** Tests inject a fake element; jsdom's <audio> implements none of the methods. */
export function setMediaFactory(fn) { _mediaFactory = fn }
export function resetMediaFactory()  { _mediaFactory = () => new Audio() }

/**
 * @param onState  called with a snapshot of `state` on every change.
 */
export function createAudioEngine({ onState = () => {} } = {}) {
  let el    = null      // created lazily: constructing one costs nothing until a track loads
  let track = null      // { url }

  const state = {
    status:   'idle',   // idle | loading | ready | playing | stalled | paused | failed
    intent:   'pause',  // what the *user* asked for — never inferred from the element
    position: 0,
    duration: 0,
    volume:   1,
    anchor:   0,        // last trusted position; the only thing a reload seeks back to
    attempts: 0,        // consecutive recovery reloads
  }

  let _pendingSeek = 0
  let _watchdog    = null
  let _watchMark   = 0
  let _playPromise = null

  const emit = () => onState({ ...state })

  // ── Element ────────────────────────────────────────────────────────────────
  const LISTENERS = {
    loadedmetadata: whileLoaded(onLoadedMeta),
    durationchange: whileLoaded(onDurationChange),
    timeupdate:     whileLoaded(onTimeUpdate),
    seeked:         whileLoaded(onSeeked),
    playing:        whileLoaded(onPlaying),
    pause:          whileLoaded(onPauseEvent),
    ended:          whileLoaded(onEnded),
    waiting:        whileLoaded(onWaiting),
    stalled:        whileLoaded(onWaiting),
    canplay:        whileLoaded(onCanPlay),
    error:          whileLoaded(onErrorEvent),
    volumechange:   onVolumeChange,
  }

  // Tearing a track down makes the element emit (`pause`, `timeupdate` at 0…).
  // Those events describe a track we no longer have, so they must not touch state.
  function whileLoaded(fn) {
    return ev => { if (track) fn(ev) }
  }

  function ensureEl() {
    if (el) return el
    el = _mediaFactory()
    try {
      el.preload = 'metadata'
      el.volume  = state.volume
      el.setAttribute?.('playsinline', '')
      // Keep it in the document: some engines only keep background playback
      // alive for connected elements.
      if (el.nodeType === 1 && typeof document !== 'undefined' && document.body && !el.isConnected) {
        el.style.display = 'none'
        document.body.appendChild(el)
      }
    } catch (_) {}
    for (const [type, fn] of Object.entries(LISTENERS)) el.addEventListener(type, fn)
    return el
  }

  // A resource we know play() cannot fix on its own.
  function isBroken(e) {
    return !!e.error || (!e.currentSrc && !e.src) || e.networkState === NETWORK_NO_SOURCE
  }

  // One ranged GET straight at the offset (`#t=`) instead of load-then-seek —
  // the second round trip is where a flaky mobile connection tends to hang.
  function attach(at) {
    const e = ensureEl()
    _pendingSeek  = at > 0 ? at : 0
    state.status  = 'loading'
    try {
      e.src = _pendingSeek > 0 ? `${track.url}#t=${Math.floor(_pendingSeek)}` : track.url
      e.load()
    } catch (_) {}
  }

  function tryPlay() {
    const e = el
    if (!e) return
    let p
    try { p = e.play() } catch (err) { onPlayRejected(err); return }
    if (p && typeof p.then === 'function') {
      _playPromise = p
      p.then(() => { _playPromise = null },
             err => { _playPromise = null; onPlayRejected(err) })
    }
  }

  function onPlayRejected(err) {
    if (!err || err.name === 'AbortError') return   // superseded by a newer load/pause
    if (err.name === 'NotAllowedError') {
      // Autoplay refused: no amount of reloading fixes a missing user gesture,
      // so fall back to paused and let the next tap carry one.
      state.intent = 'pause'
      state.status = 'paused'
      clearWatchdog()
      emit()
      return
    }
    escalate()
  }

  // ── Watchdog: the timeout the old implementation never had ─────────────────
  function clearWatchdog() {
    if (_watchdog) { clearTimeout(_watchdog); _watchdog = null }
  }

  function armWatchdog() {
    clearWatchdog()
    if (state.intent !== 'play' || !track) return
    _watchMark = el?.currentTime ?? 0
    _watchdog  = setTimeout(onWatchdog, WATCHDOG_MS[Math.min(state.attempts, WATCHDOG_MS.length - 1)])
  }

  function onWatchdog() {
    _watchdog = null
    const e = el
    if (state.intent !== 'play' || !e) return
    const progressing = !e.paused && e.currentTime > _watchMark + 0.1
    if (progressing) {
      // Moving, just not confirmed yet (or a `playing` event we missed) — keep watching.
      if (state.status !== 'playing') armWatchdog()
      return
    }
    escalate()
  }

  function escalate() {
    if (state.attempts >= MAX_RELOADS) return fail()
    state.attempts++
    reload(state.anchor)
  }

  function reload(at) {
    if (!track) return
    attach(at)
    if (state.intent === 'play') tryPlay()
    armWatchdog()
    emit()
  }

  function fail() {
    clearWatchdog()
    state.status = 'failed'
    state.intent = 'pause'
    emit()
  }

  // ── Element events ─────────────────────────────────────────────────────────
  function onLoadedMeta() {
    const e = el
    if (!e) return
    state.duration = Number.isFinite(e.duration) ? e.duration : 0
    // `#t=` normally lands us there already; this is the fallback when it didn't.
    if (_pendingSeek > 0 && Math.abs((e.currentTime || 0) - _pendingSeek) > 1) {
      try { e.currentTime = _pendingSeek } catch (_) {}
    }
    if (state.intent === 'play') tryPlay()
    emit()
  }

  function onDurationChange() {
    state.duration = Number.isFinite(el?.duration) ? el.duration : 0
    emit()
  }

  // The anchor guard: a reload resets currentTime to 0 and the element happily
  // reports it. Accepting that would send the next retry back to the start.
  function onTimeUpdate() {
    const e = el
    if (!e || e.seeking) return
    const t = e.currentTime || 0
    if (_pendingSeek > 0) {
      if (t >= _pendingSeek - 1) _pendingSeek = 0
      else if (t < 1) return
    }
    state.position = t
    state.anchor   = t
    emit()
  }

  function onSeeked() {
    const t = el?.currentTime ?? 0
    _pendingSeek   = 0
    state.position = t
    state.anchor   = t
    emit()
  }

  function onPlaying() {
    state.status   = 'playing'
    state.attempts = 0
    clearWatchdog()
    emit()
  }

  function onPauseEvent() {
    // A pause we didn't ask for means the element gave up — start the ladder.
    if (state.intent === 'play') { state.status = 'stalled'; armWatchdog() }
    else if (state.status !== 'failed') state.status = 'paused'
    emit()
  }

  function onEnded() {
    clearWatchdog()
    state.intent = 'pause'
    state.status = 'paused'
    emit()
  }

  function onWaiting() {
    if (state.intent === 'play') { state.status = 'stalled'; armWatchdog() }
    emit()
  }

  function onCanPlay() {
    // Data is ready but nothing is playing yet: if playback was intended, stay
    // under the watchdog — this is exactly the silent desync it exists to catch.
    if (state.intent !== 'play') state.status = 'ready'
    emit()
  }

  function onErrorEvent() {
    if (state.intent === 'play') escalate()
    else emit()   // paused: `play()` will see isBroken() and reload then
  }

  function onVolumeChange() {
    state.volume = el?.volume ?? state.volume
    emit()
  }

  // ── Ambient recovery: the wedge usually resolves itself off-screen ─────────
  function recoverIfNeeded() {
    const e = el
    if (!track || !e || state.intent !== 'play') return
    if (state.status === 'playing' && !e.paused) return
    state.attempts = 0            // a fresh external signal earns a fresh ladder
    if (isBroken(e) || e.paused) reload(state.anchor)
    else armWatchdog()
  }

  function onVisibility() { if (document.visibilityState === 'visible') recoverIfNeeded() }
  function onOnline()     { recoverIfNeeded() }
  function onPageShow()   { recoverIfNeeded() }   // bfcache restore

  if (typeof window !== 'undefined') {
    document.addEventListener('visibilitychange', onVisibility)
    window.addEventListener('online',   onOnline)
    window.addEventListener('pageshow', onPageShow)
  }

  // ── Commands ───────────────────────────────────────────────────────────────
  function load({ url, at = 0 }, { autoplay = false } = {}) {
    if (!url) return
    ensureEl()
    clearWatchdog()
    track          = { url }
    state.attempts = 0
    state.anchor   = at
    state.position = at
    state.duration = 0
    state.intent   = autoplay ? 'play' : 'pause'
    attach(at)
    // Called straight from the tap handler, so this play() still carries the
    // user gesture — deferring it to `loadedmetadata` is what used to lose it.
    if (autoplay) { tryPlay(); armWatchdog() }
    emit()
  }

  function play() {
    if (!track) return
    const e = ensureEl()
    state.intent = 'play'
    if (state.status === 'failed' || isBroken(e)) {
      state.attempts = 0
      reload(state.anchor)
      return
    }
    tryPlay()
    armWatchdog()
    emit()
  }

  function pause() {
    state.intent = 'pause'
    clearWatchdog()
    if (state.status !== 'failed') state.status = 'paused'
    const e = el
    if (e) {
      const doPause = () => { try { e.pause() } catch (_) {} }
      _playPromise ? _playPromise.then(doPause, () => {}) : doPause()
    }
    emit()
  }

  function toggle() { state.intent === 'play' ? pause() : play() }

  function seek(t) {
    const at = Math.max(0, t || 0)
    state.anchor   = at
    state.position = at
    const e = el
    if (!e || !track) { emit(); return }
    if (isBroken(e)) { state.attempts = 0; reload(at); return }
    _pendingSeek = at
    try { e.currentTime = at } catch (_) { state.attempts = 0; reload(at); return }
    if (state.intent === 'play') armWatchdog()
    emit()
  }

  function retry() {
    if (!track) return
    state.attempts = 0
    state.intent   = 'play'
    reload(state.anchor)
  }

  function setVolume(v) {
    state.volume = Math.min(1, Math.max(0, v))
    if (el) { try { el.volume = state.volume } catch (_) {} }
    emit()
  }

  /** Drop the current track but keep the element for the next one. */
  function stop() {
    clearWatchdog()
    track          = null   // before touching the element: its teardown events are noise now
    _pendingSeek   = 0
    state.intent   = 'pause'
    state.status   = 'idle'
    state.position = 0
    state.duration = 0
    state.anchor   = 0
    state.attempts = 0
    const e = el
    if (e) {
      try {
        e.pause()
        // removeAttribute + load(), never `src = ''` — an empty src resolves to
        // the page URL and sends the element off to fetch the document.
        e.removeAttribute?.('src')
        e.load()
      } catch (_) {}
    }
    emit()
  }

  function destroy() {
    stop()
    if (typeof window !== 'undefined') {
      document.removeEventListener('visibilitychange', onVisibility)
      window.removeEventListener('online',   onOnline)
      window.removeEventListener('pageshow', onPageShow)
    }
    if (el) {
      for (const [type, fn] of Object.entries(LISTENERS)) el.removeEventListener(type, fn)
      if (el.nodeType === 1 && el.isConnected) el.remove()
      el = null
    }
  }

  return {
    state,
    load, play, pause, toggle, seek, retry, setVolume, stop, destroy,
    get element() { return el },
  }
}
