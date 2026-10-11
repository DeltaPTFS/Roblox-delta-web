/* Delta Air Lines · one-time OAuth success experience (4 seconds). */
(() => {
  'use strict';

  const eventNode = document.getElementById('signin-event');
  const progress = document.getElementById('success-progress');
  const fill = document.getElementById('progress-fill');
  const seconds = document.getElementById('progress-seconds');
  const copy = document.getElementById('loading-copy');
  const sound = document.getElementById('signin-sound');
  const soundButton = document.getElementById('sound-button');
  const soundNote = document.getElementById('autoplay-note');
  const link = document.getElementById('continue-link');
  if (!eventNode || !progress || !fill || !seconds || !copy || !sound || !soundButton || !link) return;

  let payload;
  try { payload = JSON.parse(eventNode.textContent); }
  catch { window.location.replace('/'); return; }
  const destination = String(payload.destination || '/forms');
  if (!destination.startsWith('/') || destination.startsWith('//') || destination.includes('\\')) {
    window.location.replace('/');
    return;
  }

  link.href = destination;
  const durationMs = 4000;
  const startedAt = performance.now();
  let finished = false;
  let blocked = false;
  let hearingSound = false;
  let navigating = false;

  const moveToAccount = () => {
    if (navigating) return;
    navigating = true;
    window.location.replace(destination);
  };

  // Browser autoplay policy is enforced by the browser, not by the website.
  // Safari and Chrome may require a real click before audio can begin.
  sound.volume = 0.82;
  sound.load();
  let playAttempt;
  try { playAttempt = sound.play(); }
  catch { blocked = true; }
  if (playAttempt && typeof playAttempt.catch === 'function') {
    playAttempt.catch(() => {
      blocked = true;
      soundButton.hidden = false;
      soundNote.hidden = false;
      if (finished) {
        copy.textContent = 'Verification complete';
        seconds.textContent = 'READY';
      }
    });
  }
  if (blocked) {
    soundButton.hidden = false;
    soundNote.hidden = false;
  }

  const timeRemaining = () => Math.max(0, durationMs - (performance.now() - startedAt));
  const updateProgress = () => {
    if (finished) return;
    const elapsed = Math.min(durationMs, performance.now() - startedAt);
    const percent = Math.min(100, Math.round((elapsed / durationMs) * 100));
    fill.style.width = percent + '%';
    progress.setAttribute('aria-valuenow', String(percent));
    seconds.textContent = '00:0' + Math.ceil(timeRemaining() / 1000);
    if (elapsed >= durationMs) {
      finished = true;
      fill.style.width = '100%';
      progress.setAttribute('aria-valuenow', '100');
      seconds.textContent = 'READY';
      copy.textContent = 'Welcome aboard · Your account is ready';
      if (!blocked && !hearingSound) moveToAccount();
      return;
    }
    window.setTimeout(updateProgress, 90);
  };
  window.setTimeout(updateProgress, 70);

  soundButton.addEventListener('click', () => {
    if (hearingSound || navigating) return;
    hearingSound = true;
    soundButton.disabled = true;
    soundButton.textContent = 'Playing welcome sound…';
    soundNote.hidden = true;
    try {
      sound.currentTime = 0;
      const attempt = sound.play();
      if (attempt && typeof attempt.then === 'function') {
        attempt.then(() => {
          blocked = false;
        }).catch(() => {
          hearingSound = false;
          soundButton.disabled = false;
          soundButton.textContent = 'Play Welcome Sound';
          soundNote.hidden = false;
        });
      }
    } catch {
      hearingSound = false;
      soundButton.disabled = false;
      soundButton.textContent = 'Play Welcome Sound';
      soundNote.hidden = false;
    }
  });
  sound.addEventListener('ended', () => {
    if (hearingSound && finished) moveToAccount();
    else if (hearingSound) hearingSound = false;
  });
  // If the browser blocks autoplay or the audio decoder rejects the MP3,
  // the visitor can always use the visible Continue link (no login loop).
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') moveToAccount();
  });
})();