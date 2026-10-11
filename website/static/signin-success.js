/* Delta OAuth welcome. The browser may prohibit autoplay after a redirect. */
(() => {
  'use strict';
  const audio = document.getElementById('signin-sound');
  const finish = document.getElementById('success-finish');
  if (!audio || !finish) return;

  // Begin the supplied audio as soon as the page loads.
  // Never loop it, autoplay on other pages, or require an extra UI control.
  audio.volume = .9;
  audio.autoplay = true;
  audio.playsInline = true;
  try {
    const attempt = audio.play();
    if (attempt && typeof attempt.catch === 'function') {
      attempt.catch(() => {
        // Safari/iPadOS may block playback without a fresh user gesture.
        // There is deliberately no sound button, by request.
      });
    }
  } catch (_) {
    // Audio is optional; verification must remain successful if blocked.
  }

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