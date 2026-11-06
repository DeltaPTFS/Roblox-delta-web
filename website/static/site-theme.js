/* Accessible two-tone appearance switch, shared by public and account pages. */
(() => {
  "use strict";
  const root = document.documentElement;
  function apply(mode, remember = false) {
    const dark = mode === 'dark' || (mode === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
    const active = dark ? 'dark' : 'light';
    root.dataset.siteTheme = active;
    root.dataset.themeChoice = mode;
    root.classList.remove('theme-light','theme-dark','theme-system');
    root.classList.add('theme-' + active);
    document.body?.classList.remove('theme-light','theme-dark','theme-system');
    document.body?.classList.add('theme-' + active);
    if (remember) {
      try { localStorage.setItem('delta-site-appearance', mode); } catch (_) {}
    }
    for (const button of document.querySelectorAll('[data-site-theme-toggle]')) {
      button.setAttribute('aria-pressed', String(dark));
      button.setAttribute('aria-label', dark ? 'Switch to light mode' : 'Switch to dark mode');
      button.title = dark ? 'Light mode' : 'Dark mode';
      const label = button.querySelector('[data-site-theme-label]');
      if (label) label.textContent = dark ? 'Light' : 'Dark';
    }
  }

  function init() {
    apply(root.dataset.themeChoice || 'light');
    document.querySelectorAll('[data-site-theme-toggle]').forEach(button => {
      button.addEventListener('click', () => {
        apply(root.dataset.siteTheme === 'dark' ? 'light' : 'dark', true);
      });
    });
    const form = document.querySelector('form[action="/settings/theme"]');
    form?.addEventListener('submit', () => {
      const selected = form.querySelector('input[name="theme"]:checked')?.value;
      if (selected === 'light' || selected === 'dark' || selected === 'system') {
        try { localStorage.setItem('delta-site-appearance', selected); } catch (_) {}
      }
    });
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener?.('change', () => {
      if (root.dataset.themeChoice === 'system') apply('system');
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once:true});
  else init();
})();