/* Reliable Discord account display with profile-photo fallback and live refresh. */
(() => {
  "use strict";

  const hydrateAvatar = frame => {
    if (!frame) return;
    const img = frame.querySelector('[data-account-avatar-image]');
    if (!img) {
      frame.classList.remove('has-photo');
      return;
    }
    const check = () => {
      const good = img.complete && img.naturalWidth > 0;
      frame.classList.toggle('has-photo', good);
      if (img.complete && !good) img.remove(); // Keep the initials instead of a broken image.
    };
    img.addEventListener('load', check, {once: true});
    img.addEventListener('error', check, {once: true});
    if (img.complete) check();
  };

  document.querySelectorAll('[data-account-avatar-frame]').forEach(hydrateAvatar);
  const menus = [...document.querySelectorAll('.delta-account-menu')];
  if (!menus.length) return;

  function position(menu) {
    if (!menu.open) return;
    const panel = menu.querySelector('.delta-account-panel');
    if (!panel) return;
    const viewport = window.visualViewport;
    const left = viewport?.offsetLeft || 0;
    const top = viewport?.offsetTop || 0;
    const width = viewport?.width || document.documentElement.clientWidth;
    const height = viewport?.height || window.innerHeight;
    panel.style.setProperty('--account-right', '0px');
    panel.style.setProperty('width', `${Math.min(440, Math.max(260, width - 20))}px`, 'important');
    const rect = panel.getBoundingClientRect();
    const desiredLeft = Math.max(left + 10, Math.min(rect.left, left + width - rect.width - 10));
    panel.style.setProperty('--account-right', `${rect.left - desiredLeft}px`);
    panel.style.setProperty('--account-height', `${Math.max(100, top + height - rect.top - 12)}px`);
  }

  function close(menu) {
    menu.open = false;
    menu.querySelector('summary')?.focus();
  }

  menus.forEach(menu => {
    let loadedAt = 0;
    let pending = false;

    async function refresh() {
      if (pending || Date.now() - loadedAt < 60000) return;
      pending = true;
      const status = menu.querySelector('.delta-account-sync');
      if (status && menu.open) status.textContent = 'Refreshing your account…';
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 15000);
      try {
        const response = await fetch('/account/panel', {
          credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
        });
        if (!response.ok) throw new Error('Account refresh unavailable');
        const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
        const fresh = doc.querySelector('.delta-account-panel');
        const sourceSummary = doc.querySelector('.delta-account-trigger');
        const summary = menu.querySelector('.delta-account-trigger');
        if (!fresh || !sourceSummary || !summary) throw new Error('Missing account data');

        // Refresh the visible top-bar identity as well as the dropdown.
        // The details element and summary stay in place so keyboard focus is preserved.
        const freshFrame = sourceSummary.querySelector('[data-account-avatar-frame]');
        const oldFrame = summary.querySelector('[data-account-avatar-frame]');
        if (freshFrame && oldFrame) {
          const replacement = freshFrame.cloneNode(true);
          oldFrame.replaceWith(replacement);
          hydrateAvatar(replacement);
        }
        const label = sourceSummary.querySelector('.delta-account-trigger-label');
        const oldLabel = summary.querySelector('.delta-account-trigger-label');
        if (label && oldLabel) oldLabel.replaceWith(label.cloneNode(true));
        const oldPanel = menu.querySelector('.delta-account-panel');
        if (oldPanel) oldPanel.replaceWith(fresh);
        fresh.querySelectorAll('[data-account-avatar-frame]').forEach(hydrateAvatar);
        loadedAt = Date.now();
        position(menu);
      } catch (_) {
        if (status && menu.open) {
          status.textContent = 'Profile refresh is unavailable. Your account is still signed in.';
        }
      } finally {
        clearTimeout(timeout);
        pending = false;
      }
    }

    menu.addEventListener('toggle', () => {
      if (!menu.open) return;
      menus.forEach(other => { if (other !== menu) other.open = false; });
      position(menu);
      void refresh();
    });

    menu.addEventListener('click', event => {
      if (event.target.closest('.delta-account-close')) close(menu);
      else if (event.target.closest('a')) menu.open = false;
    });

    // Refresh the visible profile in the background without delaying page render.
    // The cached identity appears immediately; live data replaces it when available.
    if ('requestIdleCallback' in window) {
      window.requestIdleCallback(() => { void refresh(); }, {timeout: 2000});
    } else {
      window.setTimeout(() => { void refresh(); }, 700);
    }
  });

  document.addEventListener('pointerdown', event => {
    menus.forEach(menu => { if (menu.open && !menu.contains(event.target)) menu.open = false; });
  }, {passive: true});
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') menus.forEach(menu => { if (menu.open) close(menu); });
  });
  const reposition = () => menus.forEach(position);
  window.addEventListener('resize', reposition, {passive: true});
  window.addEventListener('scroll', reposition, {passive: true});
  window.visualViewport?.addEventListener('resize', reposition, {passive: true});
  window.visualViewport?.addEventListener('scroll', reposition, {passive: true});
})();