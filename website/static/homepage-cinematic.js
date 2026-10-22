/* Lightweight homepage reveals. No per-frame scrolling, parallax, image
 * filters, repeated reveals, animation loops or card layout measurements.
 * All content remains visible when JavaScript or motion is disabled. */
(() => {
  'use strict';
  if (!document.querySelector('.home-cinematic-hero')) return;
  const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  if (reduceMotion || !('IntersectionObserver' in window)) return;

  const selector = [
    '.discover .section-head > *',
    '.discover .feature-card',
    '.showcase .section-head > *',
    '.showcase .gallery-card',
    // Cabin photographs remain static: animating them made Safari scroll choppy.
    '.delta-ad-secondary .section-head > *',
    '.delta-ad-secondary .delta-ad-feature-card',
    '.core-home-spotlight .core-home-copy > *',
    '.core-home-spotlight .core-home-partner',
    '.future .future-content > *',
    '.small-cta > *'
  ].join(', ');

  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      entry.target.classList.add('home-visible');
      observer.unobserve(entry.target);
    }
  }, { threshold: 0.07, rootMargin: '0px 0px -25px 0px' });

  const targets = document.querySelectorAll(selector);
  for (const node of targets) {
    node.classList.add('home-reveal');
    const bounds = node.getBoundingClientRect();
    if (bounds.bottom > 0 && bounds.top < window.innerHeight * 0.92) {
      node.classList.add('home-visible');
    } else {
      observer.observe(node);
    }
  }
  document.body.classList.add('home-cinematic-ready');
})();
