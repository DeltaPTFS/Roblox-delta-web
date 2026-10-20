/* Delta community motion: observe once, never animate during continuous scrolling. */
(function () {
  'use strict';
  const menu = document.querySelector('.community-mobile-menu');
  if (menu) {
    document.addEventListener('pointerdown', function (event) {
      if (menu.open && !menu.contains(event.target)) menu.open = false;
    }, { passive: true });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && menu.open) {
        menu.open = false;
        const summary = menu.querySelector('summary');
        if (summary) summary.focus();
      }
    });
    menu.querySelectorAll('a').forEach(link => link.addEventListener('click', function () {
      menu.open = false;
    }));
  }
  const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduce || !('IntersectionObserver' in window)) return;
  // The homepage and partner pages have independent scroll directors.
  // Never register a competing generic observer on those same elements.
  if (document.querySelector('.home-cinematic-hero, .core-page')) return;

  const targets = document.querySelectorAll(
    '.discover .section-head, .feature-card, .showcase .section-head, .gallery-card, .future-content, .small-cta, ' +
    '.core-intro-grid, .core-section-heading, .core-benefit, .core-eligibility, .core-sky-copy, .core-sky-visual, .core-connect-heading, .core-connect-panel, .core-final, .core-facts > div, .core-home-card'
  );
  if (!targets.length) return;
  const observer = new IntersectionObserver(function (entries) {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        entry.target.classList.add('delta-visible');
        observer.unobserve(entry.target);
      }
    }
  }, { threshold: 0.06, rootMargin: '0px 0px -20px 0px' });
  targets.forEach(node => {
    node.setAttribute('data-reveal', '');
    if (node.closest('.core-page') || node.closest('.core-home-spotlight')) {
      node.setAttribute('data-premium-reveal', '');
    }
    observer.observe(node);
  });
  document.body.classList.add('delta-motion-ready');
})();
