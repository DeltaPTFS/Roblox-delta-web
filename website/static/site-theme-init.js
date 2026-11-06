/* Set the preferred appearance before styles render to avoid a white/blue flash. */
(() => {
  "use strict";
  const root = document.documentElement;
  let saved;
  try { saved = localStorage.getItem('delta-site-appearance'); } catch (_) {}
  const userTheme = root.classList.contains('theme-dark')
    ? 'dark'
    : root.classList.contains('theme-system') ? 'system' : 'light';
  let choice = saved === 'light' || saved === 'dark' || saved === 'system' ? saved : userTheme;
  const dark = choice === 'dark' || (choice === 'system' && window.matchMedia?.('(prefers-color-scheme: dark)').matches);
  const active = dark ? 'dark' : 'light';
  root.classList.remove('theme-light','theme-dark','theme-system');
  root.classList.add('theme-' + active);
  root.dataset.siteTheme = active;
  root.dataset.themeChoice = choice;
})();