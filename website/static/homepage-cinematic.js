/* High-performance cinematic section reveals, only on the public homepage. */
(() => {
  'use strict';
  if (!document.querySelector('.home-cinematic-hero')) return;
  const reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduced || !('IntersectionObserver' in window)) return;

  const selector = [
    '.discover .section-head', '.discover .feature-card',
    '.showcase .section-head', '.showcase .gallery-card',
    '.delta-ad-secondary .section-head', '.delta-ad-secondary .delta-ad-feature-card',
    '.core-home-spotlight .core-home-card',
    '.future-content', '.small-cta',
  ].join(', ');
  const targets = Array.from(document.querySelectorAll(selector));
  if (!targets.length) return;

  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        entry.target.classList.add('home-visible');
        observer.unobserve(entry.target);
      }
    }
  }, { threshold: 0.08, rootMargin: '0px 0px -38px 0px' });

  for (const [index, node] of targets.entries()) {
    node.classList.add('home-reveal');
    if (node.matches('.gallery-card') && index % 2 === 0) node.classList.add('home-from-left');
    if (node.matches('.gallery-card') && index % 2 !== 0) node.classList.add('home-from-right');
    // Keep already visible content stable, even when scripts load after the page paints.
    const bounds = node.getBoundingClientRect();
    if (bounds.top < window.innerHeight * .86 && bounds.bottom > 0) {
      node.classList.add('home-visible');
    } else {
      observer.observe(node);
    }
  }
  document.body.classList.add('home-cinematic-ready');
  // Restore all content if the page is restored after browser back/forward navigation.
  window.addEventListener('pageshow', (event) => {
    if (event.persisted) for (const node of targets) node.classList.add('home-visible');
  });
})();
