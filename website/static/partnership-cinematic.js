/* Virgin Atlantic × Delta Roblox — cinematic scroll director.
   Runs only on the partnership page. Content is fully visible without JS. */
(() => {
  'use strict';
  const page = document.querySelector('.core-page');
  if (!page) return;
  const reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduced || !('IntersectionObserver' in window)) return;

  const progress = page.querySelector('.core-scroll-meter-fill');
  const hero = page.querySelector('.core-hero');
  const visual = page.querySelector('.core-sky-visual');
  const showcase = page.querySelector('.core-connect-panel-art:not(.core-partnership-photo-frame)');

  // Fine-grained entrances reveal the story line by line instead of animating
  // one giant section. Group by parent to keep each scene's stagger short.
  const selector = [
    '.core-facts > div',
    '.core-intro > .core-section-kicker',
    '.core-intro-grid > *',
    '.core-benefits .core-section-kicker',
    '.core-section-heading > *',
    '.core-benefit',
    '.core-eligibility',
    '.core-sky-copy > *',
    '.core-sky-visual-overlay > *',
    '.core-connect-heading > *',
    '.core-connect-panel-copy > *',
    '.core-connect-panel-art:not(.core-partnership-photo-frame)',
    '.core-final > *'
  ].join(', ');
  const targets = [...page.querySelectorAll(selector)];
  const scenes = [...page.querySelectorAll(
    '.core-intro, .core-benefits, .core-sky-section, .core-connect, .core-final'
  )];

  const revealObserver = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting) entry.target.classList.add('core-visible');
    }
  }, { threshold: 0.10, rootMargin: '0px 0px -8% 0px' });

  const sceneObserver = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      entry.target.classList.toggle('core-scene-active', entry.isIntersecting);
    }
  }, { threshold: 0.10, rootMargin: '0px 0px -13% 0px' });

  targets.forEach((node, index) => {
    node.classList.add('core-reveal');
    // Alternating entrance directions make the two airlines feel connected.
    if (node.matches('.core-benefit, .core-connect-panel-art, .core-facts > div')) {
      node.classList.add(index % 2 === 0 ? 'core-from-left' : 'core-from-right');
    }
    const group = node.parentElement;
    const siblings = group ? [...group.children].filter(item => item.matches(selector)) : [];
    const order = Math.max(0, siblings.indexOf(node));
    node.style.setProperty('--core-delay', Math.min(order * 95, 380) + 'ms');

    // Prevent content already in view from flashing invisible at initialization.
    const box = node.getBoundingClientRect();
    if (box.bottom > 0 && box.top < window.innerHeight * .87) node.classList.add('core-visible');
    revealObserver.observe(node);
  });
  scenes.forEach(node => sceneObserver.observe(node));
  page.classList.add('core-motion-ready');

  let scheduled = false;
  const update = () => {
    scheduled = false;
    const height = Math.max(document.documentElement.scrollHeight - window.innerHeight, 1);
    const scroll = Math.max(window.scrollY || document.documentElement.scrollTop || 0, 0);
    if (progress) progress.style.transform = 'scaleX(' + Math.min(1, scroll / height) + ')';

    // Bounded cosmetic parallax: no movement of text or interactive elements.
    if (hero && scroll < hero.offsetTop + hero.offsetHeight + 180) {
      const passed = Math.max(0, Math.min(scroll - hero.offsetTop, hero.offsetHeight));
      hero.style.setProperty('--core-hero-drift', (passed * .10).toFixed(1) + 'px');
    }
    if (visual) {
      const bounds = visual.getBoundingClientRect();
      visual.classList.toggle('core-section-active',
        bounds.bottom > 0 && bounds.top < window.innerHeight);
    }
    if (showcase) {
      const bounds = showcase.getBoundingClientRect();
      showcase.classList.toggle('core-section-active',
        bounds.bottom > 0 && bounds.top < window.innerHeight);
    }

    // Re-arm once elements are fully outside the viewport. Scrolling back up
    // or down then plays the fade/slide again, not merely on the first pass.
    for (const node of targets) {
      if (!node.classList.contains('core-visible')) continue;
      const bounds = node.getBoundingClientRect();
      if (bounds.bottom < -window.innerHeight * .16 ||
          bounds.top > window.innerHeight * 1.16) {
        node.classList.remove('core-visible');
      }
    }
  };
  const schedule = () => {
    if (scheduled) return;
    scheduled = true;
    window.requestAnimationFrame(update);
  };
  window.addEventListener('scroll', schedule, { passive: true });
  window.addEventListener('resize', schedule, { passive: true });
  window.addEventListener('pageshow', schedule);
  schedule();
})();
