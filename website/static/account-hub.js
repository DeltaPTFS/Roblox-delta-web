/* Refresh verified account assets on demand; keep the panel within the viewport. */
(() => {
  const menus = Array.from(document.querySelectorAll('.delta-account-menu'));
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
    panel.style.setProperty('width', `${Math.min(440, width - 20)}px`, 'important');
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
    menu.addEventListener('toggle', async () => {
      if (!menu.open) return;
      menus.forEach(other => { if (other !== menu) other.open = false; });
      position(menu);
      if (pending || Date.now() - loadedAt < 60000) return;
      pending = true;
      const status = menu.querySelector('.delta-account-sync');
      if (status) status.textContent = 'Connecting your profile and server roles…';
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 15000);
      try {
        const response = await fetch('/account/panel', {credentials:'same-origin', cache:'no-store', signal:controller.signal});
        if (!response.ok) throw new Error('Account refresh unavailable');
        const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
        const fresh = doc.querySelector('.delta-account-panel');
        if (!fresh) throw new Error('Missing account panel');
        // Leave the trigger and its keyboard focus intact.
        menu.querySelector('.delta-account-panel').replaceWith(fresh);
        loadedAt = Date.now();
        position(menu);
      } catch (_) {
        if (status) status.textContent = 'Could not refresh right now. Your existing account links still work. Close and reopen to retry.';
        position(menu);
      } finally { clearTimeout(timeout); pending = false; }
    });
    menu.addEventListener('click', event => {
      if (event.target.closest('.delta-account-close')) close(menu);
      else if (event.target.closest('a')) menu.open = false;
    });
  });
  document.addEventListener('pointerdown', event => {
    menus.forEach(menu => { if (menu.open && !menu.contains(event.target)) menu.open = false; });
  }, {passive:true});
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') menus.forEach(menu => { if (menu.open) close(menu); });
  });
  const reposition = () => menus.forEach(position);
  window.addEventListener('resize', reposition, {passive:true});
  window.addEventListener('scroll', reposition, {passive:true});
  window.visualViewport?.addEventListener('resize', reposition, {passive:true});
  window.visualViewport?.addEventListener('scroll', reposition, {passive:true});
})();
