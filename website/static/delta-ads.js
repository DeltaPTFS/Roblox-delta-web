/* Delta featured advertisements: 5s per slide, no scroll handlers or heavy animation libraries. */
(() => {
  'use strict';
  const root = document.querySelector('[data-ad-carousel]');
  if (!root) return;
  const slides = [...root.querySelectorAll('[data-ad-slide]')];
  const dots = [...root.querySelectorAll('[data-ad-dot]')];
  const caption = root.querySelector('[data-ad-heading]');
  const progress = root.querySelector('[data-ad-progress]');
  const toggle = root.querySelector('[data-ad-toggle]');
  const pauseIcon = root.querySelector('[data-ad-pause-icon]');
  const playIcon = root.querySelector('[data-ad-play-icon]');
  const previous = root.querySelector('[data-ad-previous]');
  const next = root.querySelector('[data-ad-next]');
  const names = [
    'New York to Los Angeles', 'New York — The World Is Yours',
    'A Century of Stories', 'Technical Operations',
    'Engines That Move the World', 'Skipping Class'
  ];
  const intervalMs = 5000;
  const media = window.matchMedia('(prefers-reduced-motion: reduce)');
  const narrowScreen = window.matchMedia('(max-width: 760px)');
  let index = 0;
  let timer = null;
  // Mobile visitors swipe or use arrows; do not force a repaint every 5s.
  let isPaused = media.matches || narrowScreen.matches;
  let isHovered = false;
  let isFocused = false;
  let isVisible = true;
  let touchStart = null;
  if (isPaused && toggle) {
    toggle.setAttribute('aria-pressed', 'true');
    toggle.setAttribute('aria-label', 'Resume advertisement rotation');
    if (pauseIcon) pauseIcon.hidden = true;
    if (playIcon) playIcon.hidden = false;
  }

  function stop() {
    if (timer !== null) { clearTimeout(timer); timer = null; }
    progress?.classList.remove('is-advancing');
  }
  function canAdvance() {
    return !isPaused && !isHovered && !isFocused && isVisible && !document.hidden && slides.length > 1;
  }
  function schedule() {
    stop();
    if (!canAdvance()) return;
    if (progress) {
      progress.style.animation = 'none';
      void progress.offsetWidth;
      progress.style.animation = '';
      progress.classList.add('is-advancing');
    }
    timer = window.setTimeout(() => go(index + 1), intervalMs);
  }
  function go(value) {
    const nextIndex = (value + slides.length) % slides.length;
    const prior = slides[index];
    if (prior) { prior.classList.remove('is-active'); prior.setAttribute('aria-hidden', 'true'); prior.querySelector('a')?.setAttribute('tabindex','-1'); }
    index = nextIndex;
    const active = slides[index];
    active.classList.add('is-active');
    active.setAttribute('aria-hidden', 'false');
    active.querySelector('a')?.removeAttribute('tabindex');
    for (let i = 0; i < dots.length; i++) dots[i].setAttribute('aria-current', String(i === index));
    if (caption) caption.textContent = names[index] || 'Delta Air Lines';
    // Preload only the next advertisement, not all six large images at once.
    const upcoming = slides[(index + 1) % slides.length]?.querySelector('img');
    if (upcoming) upcoming.loading = 'eager';
    schedule();
  }
  previous?.addEventListener('click', () => go(index - 1));
  next?.addEventListener('click', () => go(index + 1));
  dots.forEach((dot,i) => dot.addEventListener('click', () => go(i)));
  toggle?.addEventListener('click', () => {
    isPaused = !isPaused;
    toggle.setAttribute('aria-pressed', String(isPaused));
    toggle.setAttribute('aria-label', isPaused ? 'Resume advertisement rotation' : 'Pause advertisement rotation');
    if (pauseIcon) pauseIcon.hidden = isPaused;
    if (playIcon) playIcon.hidden = !isPaused;
    schedule();
  });
  root.addEventListener('mouseenter', () => { isHovered = true; stop(); });
  root.addEventListener('mouseleave', () => { isHovered = false; schedule(); });
  root.addEventListener('focusin', () => { isFocused = true; stop(); });
  root.addEventListener('focusout', (event) => {
    if (event.relatedTarget && root.contains(event.relatedTarget)) return;
    isFocused = false; schedule();
  });
  root.addEventListener('keydown', event => {
    if (event.key === 'ArrowRight') { event.preventDefault(); go(index+1); }
    else if (event.key === 'ArrowLeft') { event.preventDefault(); go(index-1); }
  });
  root.addEventListener('touchstart', e => {
    if (!e.touches || e.touches.length !== 1) return;
    touchStart = { x:e.touches[0].clientX, y:e.touches[0].clientY };
  }, {passive:true});
  root.addEventListener('touchend', e => {
    if (!touchStart || !e.changedTouches?.length) return;
    const dx = e.changedTouches[0].clientX - touchStart.x;
    const dy = e.changedTouches[0].clientY - touchStart.y;
    touchStart=null;
    if (Math.abs(dx) > 55 && Math.abs(dx)>Math.abs(dy)*1.5) go(index + (dx < 0 ? 1 : -1));
  }, {passive:true});
  document.addEventListener('visibilitychange', () => document.hidden ? stop() : schedule());
  media.addEventListener?.('change', () => {
    if (media.matches) { isPaused=true; toggle?.setAttribute('aria-pressed','true'); if(pauseIcon)pauseIcon.hidden=true; if(playIcon)playIcon.hidden=false; }
    schedule();
  });
  narrowScreen.addEventListener?.('change', () => {
    if (narrowScreen.matches) {
      isPaused = true;
      toggle?.setAttribute('aria-pressed', 'true');
      toggle?.setAttribute('aria-label', 'Resume advertisement rotation');
      if (pauseIcon) pauseIcon.hidden = true;
      if (playIcon) playIcon.hidden = false;
    }
    schedule();
  });
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => {
      isVisible=!!entries[0]?.isIntersecting;
      schedule();
    }, { threshold:.08 });
    observer.observe(root);
  }
  // Invisible slides cannot be reached through keyboard tab navigation.
  slides.forEach((slide,i)=>{if(i!==0)slide.querySelector('a')?.setAttribute('tabindex','-1')});
  schedule();
})();