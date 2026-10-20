/* Delta OAuth welcome. Playback may require a gesture on mobile browsers. */
(() => {
  'use strict';
  const audio = document.getElementById('signin-sound');
  const finish = document.getElementById('success-finish');
  if (!audio || !finish) return;

  audio.volume = .9;
  audio.playsInline = true;
  let awaitingGesture = false;
  let gestureConsumed = false;

  const resumeOnGesture = () => {
    if (gestureConsumed || !awaitingGesture) return;
    gestureConsumed = true;
    awaitingGesture = false;
    // Mobile Safari may only authorize sound in a direct user gesture.
    audio.play().catch(() => {});
  };

  const startWelcomeSound = () => {
    gestureConsumed = false;
    awaitingGesture = false;
    try {
      audio.pause();
      audio.currentTime = 0;
      const attempt = audio.play();
      if (attempt && typeof attempt.catch === 'function') {
        attempt.catch(() => {
          // Autoplay can be blocked after OAuth redirects. A tap or key press
          // on this success page supplies the required gesture.
          awaitingGesture = true;
          document.addEventListener('pointerdown', resumeOnGesture, { passive: true });
          document.addEventListener('keydown', resumeOnGesture);
        });
      }
    } catch (_) {
      awaitingGesture = true;
      document.addEventListener('pointerdown', resumeOnGesture, { passive: true });
      document.addEventListener('keydown', resumeOnGesture);
    }
  };

  // pageshow fires for a fresh visit and a back-forward cache restoration.
  // Replay the confirmation on each visit, without playing across the site.
  window.addEventListener('pageshow', startWelcomeSound);
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
