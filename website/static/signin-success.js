/* Play the Delta welcome audio on every successful login/return.
   Audible autoplay cannot be forced when a browser blocks it. In that case
   play on the visitor's first actual interaction, with no visible sound UI. */
(() => {
  'use strict';
  const sound = document.getElementById('signin-sound');
  const finish = document.getElementById('success-finish');
  if (!sound || !finish) return;
  sound.volume = .9;
  sound.preload = 'auto';
  let fallbackPending = false;
  let started = false;
  let attemptId = 0;
  function play() {
    if (started) return;
    const id = ++attemptId;
    try {
      const promise = sound.play();
      if (promise && typeof promise.then === 'function') {
        promise.then(() => { if (id === attemptId) { started = true; fallbackPending = false; } })
          .catch(() => { if (id === attemptId) fallbackPending = true; });
      } else { started = true; fallbackPending = false; }
    } catch (_) { fallbackPending = true; }
  }
  function handleGesture() { if (fallbackPending && !started) play(); }
  document.addEventListener('pointerdown', handleGesture, {passive:true});
  document.addEventListener('keydown', handleGesture);
  window.addEventListener('pageshow', () => {
    try { sound.pause(); sound.currentTime = 0; } catch (_) {}
    started = false;
    fallbackPending = false;
    play();
  });
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const enable = () => {
    finish.classList.add('is-ready');
    const link = finish.querySelector('a');
    if (link) link.removeAttribute('aria-disabled');
  };
  if (reduced) enable(); else window.setTimeout(enable, 3900);
})();