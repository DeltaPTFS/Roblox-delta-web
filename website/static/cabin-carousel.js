/* Delta Roblox cabin — native CSS scroll-snap, no autoplay or animation loop.
   Swipe works without JavaScript; this only powers arrows, dots and the counter. */
(() => {
  'use strict';
  const carousel = document.querySelector('[data-cabin-carousel]');
  if (!carousel) return;
  const track = carousel.querySelector('[data-cabin-track]');
  const slides = [...track.querySelectorAll('.cabin-carousel-slide')];
  const dots = [...carousel.querySelectorAll('[data-cabin-dot]')];
  const previous = carousel.querySelector('[data-cabin-prev]');
  const next = carousel.querySelector('[data-cabin-next]');
  const count = carousel.querySelector('[data-cabin-count]');
  if (slides.length < 2) return;

  let index = 0;
  function update(value) {
    index = Math.max(0, Math.min(slides.length - 1, value));
    dots.forEach((dot, i) => {
      dot.classList.toggle('is-active', i === index);
      dot.setAttribute('aria-pressed', String(i === index));
    });
    if (count) count.textContent =
      String(index + 1).padStart(2, '0') + ' / ' + String(slides.length).padStart(2, '0');
    if (previous) previous.disabled = index === 0;
    if (next) next.disabled = index === slides.length - 1;
  }
  function go(value) {
    const nextIndex = Math.max(0, Math.min(slides.length - 1, value));
    update(nextIndex);
    // No smooth JS animation: CSS scroll snap handles the mobile swipe.
    track.scrollTo({ left: slides[nextIndex].offsetLeft - slides[0].offsetLeft, behavior: 'instant' });
  }

  previous?.addEventListener('click', () => go(index - 1));
  next?.addEventListener('click', () => go(index + 1));
  dots.forEach((dot, i) => dot.addEventListener('click', () => go(i)));
  track.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowRight') { event.preventDefault(); go(index + 1); }
    if (event.key === 'ArrowLeft') { event.preventDefault(); go(index - 1); }
  });
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting && entry.intersectionRatio >= 0.65) {
          update(slides.indexOf(entry.target));
        }
      }
    }, { root: track, threshold: [0.65] });
    slides.forEach(slide => observer.observe(slide));
  } else {
    // Older browsers can still swipe and use arrows. Reflect native swipe
    // position only after scrolling settles, not continuously per frame.
    track.addEventListener('scrollend', () => {
      const left = track.scrollLeft;
      const slideWidth = slides[1].offsetLeft - slides[0].offsetLeft;
      update(Math.round(left / Math.max(slideWidth, 1)));
    }, { passive: true });
  }
  update(0);
  carousel.classList.add('is-ready');
})();