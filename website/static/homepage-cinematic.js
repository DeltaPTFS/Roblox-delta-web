/* Scroll-triggered homepage sequences: replay as visitors return to each section. */
(() => {
  'use strict';
  const hero = document.querySelector('.home-cinematic-hero');
  if (!hero) return;
  const reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduced || !('IntersectionObserver' in window)) return;

  // Headings and copy reveal separately, followed by staggered flight / gallery cards.
  // Generic community-motion.js skips these targets so there is one animation director.
  const selectors = [
    '.discover .section-head > *',
    '.discover .feature-card',
    '.showcase .section-head > *',
    '.showcase .gallery-card',
    '.delta-ad-secondary .section-head > *',
    '.delta-ad-secondary .delta-ad-feature-card',
    '.core-home-spotlight .core-home-copy > *',
    '.core-home-spotlight .core-home-partner',
    '.future .future-content > *',
    '.small-cta > *'
  ];

  const targets = [...document.querySelectorAll(selectors.join(', '))];
  const meter = document.querySelector('.home-scroll-meter-fill');
  const picture = hero.querySelector('.hero-photo img');
  let ticking = false;

  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting) entry.target.classList.add('home-visible');
    }
  }, {
    // Fire while content is actually coming into view, not all at initial load.
    threshold: 0.12,
    rootMargin: '0px 0px -9% 0px'
  });

  targets.forEach((node, index) => {
    node.classList.add('home-reveal');
    if (node.matches('.gallery-card, .delta-ad-feature-card, .core-home-partner')) {
      node.classList.add(index % 2 === 0 ? 'home-from-left' : 'home-from-right');
    }
    node.style.setProperty('--home-stagger', (index % 3) * 90 + 'ms');

    // Show anything already in the viewport rather than flashing it invisible.
    const box = node.getBoundingClientRect();
    if (box.bottom > 0 && box.top < innerHeight * 0.86) {
      node.classList.add('home-visible');
    }
    observer.observe(node);
  });

  document.body.classList.add('home-cinematic-ready');

  const drawScroll = () => {
    ticking = false;
    const scroll = Math.max(window.scrollY || document.documentElement.scrollTop || 0, 0);
    const total = Math.max(document.documentElement.scrollHeight - window.innerHeight, 1);
    if (meter) meter.style.transform = 'scaleX(' + Math.min(1, scroll / total) + ')';

    // A subtle aircraft-photo parallax while the hero is passing the viewport.
    // The value is bounded to prevent large motion or horizontal scrollbars.
    if (picture && scroll < hero.offsetTop + hero.offsetHeight + 150) {
      const position = Math.max(0, Math.min(scroll - hero.offsetTop, hero.offsetHeight));
      picture.style.setProperty('--home-parallax', (position * 0.12).toFixed(1) + 'px');
    }

    // Re-arm sections once well outside the viewport. Scrolling back up or
    // down now triggers their slide/fade again instead of only playing once.
    for (const node of targets) {
      if (!node.classList.contains('home-visible')) continue;
      const rect = node.getBoundingClientRect();
      if (rect.bottom < -window.innerHeight * 0.13 ||
          rect.top > window.innerHeight * 1.13) {
        node.classList.remove('home-visible');
      }
    }
  };

  const requestDraw = () => {
    if (!ticking) {
      ticking = true;
      window.requestAnimationFrame(drawScroll);
    }
  };
  window.addEventListener('scroll', requestDraw, { passive: true });
  window.addEventListener('resize', requestDraw, { passive: true });
  window.addEventListener('pageshow', requestDraw);
  requestDraw();
})();
