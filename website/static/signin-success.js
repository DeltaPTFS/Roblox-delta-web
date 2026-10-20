/* Delta welcome audio — repeatable on each confirmed sign-in/sign-up. */
(() => {
  'use strict';
  const audio = document.getElementById('signin-sound');
  const finish = document.getElementById('success-finish');
  const replay = document.getElementById('play-welcome-sound');
  const label = document.getElementById('welcome-sound-label');
  const hint = document.getElementById('welcome-sound-hint');
  if (!audio || !finish || !replay || !label || !hint) return;

  audio.volume = .9;
  audio.playsInline = true;
  audio.preload = 'auto';
  const showBlocked = () => {
    // iOS Safari and some browsers forbid audible autoplay after OAuth.
    // A real button click is always an explicit playback request.
    label.textContent = 'Tap to play welcome sound';
    hint.hidden = false;
    replay.setAttribute('aria-label', 'Tap to play welcome sound');
  };
  const showPlaying = () => {
    label.textContent = 'Replay welcome sound';
    hint.hidden = true;
    replay.setAttribute('aria-label', 'Replay welcome sound');
  };
  const playWelcomeSound = () => {
    try {
      audio.pause();
      audio.currentTime = 0;
      const attempt = audio.play();
      if (attempt && typeof attempt.then === 'function') {
        attempt.then(showPlaying).catch(showBlocked);
      } else {
        showPlaying();
      }
    } catch (_) {
      showBlocked();
    }
  };

  // A user-initiated click works on browsers where automatic sound is blocked.
  replay.addEventListener('click', playWelcomeSound);

  // Fire on fresh navigation as well as back/forward-cache page restoration.
  // Only plays on the authenticated welcome page, never throughout the site.
  window.addEventListener('pageshow', playWelcomeSound);

  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const activate = () => {
    finish.classList.add('is-ready');
    const link = finish.querySelector('a');
    if (link) link.removeAttribute('aria-disabled');
  };
  if (reduced) activate();
  else window.setTimeout(activate, 3900);

  // No automatic navigation. The member chooses when to leave the page.
})();
