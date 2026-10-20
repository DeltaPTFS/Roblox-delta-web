/* One accessible Navigation Hub, shared across Delta public and SkyMiles pages. */
(() => {
  'use strict';
  const nav = document.getElementById('sky-nav-dropdown');
  if (!nav) return;
  const trigger = nav.querySelector('summary');
  const account = document.getElementById('delta-account-menu');
  const updateExpanded = () => trigger?.setAttribute('aria-expanded', nav.open ? 'true' : 'false');

  nav.addEventListener('toggle', () => {
    updateExpanded();
    if (nav.open && account) account.open = false;
  });
  if (account) {
    account.addEventListener('toggle', () => {
      if (account.open && nav.open) nav.open = false;
    });
  }
  document.addEventListener('pointerdown', (event) => {
    if (nav.open && !nav.contains(event.target)) nav.open = false;
  }, { passive: true });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && nav.open) {
      nav.open = false;
      trigger?.focus();
    }
  });
  nav.querySelectorAll('a').forEach(link => {
    link.addEventListener('click', () => { nav.open = false; });
  });
  updateExpanded();
})();
